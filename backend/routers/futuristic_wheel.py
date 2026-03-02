"""
routers/futuristic_wheel.py
API endpoints for the Futuristic Wheel (PMCC) module.

GET  /futuristic-wheel         – all data (current leaps, short call history, series)
POST /futuristic-wheel/sync    – pull from IBKR flex report and save snapshots + calls
PUT  /futuristic-wheel/delta   – save manual per-contract delta for a symbol
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from datetime import datetime

from auth import verify_token
from database import (
    get_user_config, update_user_config,
    save_pmcc_short_calls, get_pmcc_short_calls,
    save_pmcc_leap_snapshot, get_pmcc_leap_snapshots,
)
from trade_categorizer import fetch_flex_report, parse_trades_from_xml, parse_positions_from_xml
from pmcc_analyzer import parse_leap_positions, build_pmcc_short_calls

router = APIRouter(prefix="/futuristic-wheel", tags=["futuristic-wheel"])

START_DATE = '2026-02-20'   # Daily P&L series start date


# ── Models ────────────────────────────────────────────────────────────────────

class DeltaUpdate(BaseModel):
    symbol: str
    delta: float


class AutoSyncToggle(BaseModel):
    enabled: bool


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_pmcc_deltas(config: dict) -> dict:
    """Extract per-symbol delta values stored as flat keys pmcc_delta_<SYMBOL>."""
    deltas = {}
    for key, val in config.items():
        if key.startswith('pmcc_delta_'):
            sym = key[len('pmcc_delta_'):]
            try:
                deltas[sym] = float(val)
            except (ValueError, TypeError):
                pass
    return deltas


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("")
def get_futuristic_wheel(user: dict = Depends(verify_token)):
    """Return all futuristic wheel data for the UI."""
    email = user.get('email')

    short_calls = get_pmcc_short_calls(email)
    snapshots   = get_pmcc_leap_snapshots(email)
    config      = get_user_config(email) or {}
    pmcc_deltas = _get_pmcc_deltas(config)

    # ── Current LEAP state (latest snapshot) ─────────────────────────────────
    latest_leaps = []
    if snapshots:
        latest_date  = max(s.get('snapshot_date', '') for s in snapshots)
        latest_leaps = [s for s in snapshots if s.get('snapshot_date') == latest_date]
        for leap in latest_leaps:
            sym   = leap.get('symbol', '')
            delta = pmcc_deltas.get(sym)
            if delta is not None:
                leap['delta']       = delta
                leap['total_delta'] = round(leap.get('contracts', 0) * 100.0 * delta, 2)

    total_contracts     = sum(l.get('contracts', 0) for l in latest_leaps)
    total_cost          = round(sum(
        l.get('contracts', 0) * l.get('cost_basis', 0.0) * l.get('multiplier', 100.0)
        for l in latest_leaps
    ), 2)
    total_unrealized    = round(sum(l.get('unrealized_pnl', 0.0) for l in latest_leaps), 2)
    total_delta         = None
    if latest_leaps and all(l.get('delta') is not None for l in latest_leaps):
        total_delta = round(sum(l.get('total_delta', 0.0) for l in latest_leaps), 2)

    # ── LEAP contract count time-series ──────────────────────────────────────
    date_map: dict = {}
    for s in snapshots:
        d = s.get('snapshot_date', '')
        if not d:
            continue
        if d not in date_map:
            date_map[d] = {'date': d, 'total_contracts': 0}
        date_map[d]['total_contracts'] += int(s.get('contracts', 0))
    leap_series = sorted(date_map.values(), key=lambda x: x['date'])

    # ── Extra contracts (growth since strategy inception) ─────────────────────
    baseline_contracts = leap_series[0]['total_contracts'] if leap_series else 0
    extra_contracts = total_contracts - baseline_contracts
    total_market_value = round(sum(
        l.get('contracts', 0) * l.get('mark_price', 0.0) * l.get('multiplier', 100.0)
        for l in latest_leaps
    ), 2)
    extra_contracts_value = round(
        (extra_contracts / total_contracts * total_market_value) if total_contracts > 0 else 0.0, 2
    )

    # ── Short call stats ──────────────────────────────────────────────────────
    closed_calls = [c for c in short_calls if c.get('status') in ('closed', 'expired')]
    open_calls   = [c for c in short_calls if c.get('status') == 'open']
    closed_pnls   = [c['pnl'] for c in closed_calls if c.get('pnl') is not None]
    wins          = [p for p in closed_pnls if p > 0]
    win_rate      = round(len(wins) / len(closed_pnls) * 100, 1) if closed_pnls else 0
    total_realized = round(sum(closed_pnls), 2)
    avg_pnl        = round(total_realized / len(closed_pnls), 2) if closed_pnls else 0

    # Open call unrealized P&L: premium received minus current cost-to-close
    open_current_value = round(sum(
        c.get('mark_price', 0.0) * c.get('contracts', 0) * 100.0
        for c in open_calls if c.get('mark_price') is not None
    ), 2)
    open_unrealized_pnl = round(sum(
        (c.get('open_price', 0.0) - c.get('mark_price', 0.0)) * c.get('contracts', 0) * 100.0
        for c in open_calls if c.get('mark_price') is not None
    ), 2)
    total_pnl = round(total_realized + open_unrealized_pnl, 2)

    # ── Daily P&L series (from START_DATE, gap-filled to today) ─────────────
    # Bucket realised PnL by close date
    from datetime import date as _date, timedelta
    daily_map: dict = {}
    for c in short_calls:
        if c.get('status') not in ('closed', 'expired'):
            continue
        close_dt = (c.get('close_date') or '')[:10]
        if not close_dt or close_dt < START_DATE:
            continue
        pnl = c.get('pnl') or 0.0
        daily_map[close_dt] = round(daily_map.get(close_dt, 0.0) + pnl, 2)

    # Walk every calendar day from START_DATE to today, carrying cumulative forward
    start_d = _date(int(START_DATE[:4]), int(START_DATE[5:7]), int(START_DATE[8:10]))
    today_d  = _date.today()
    daily_pnl_series = []
    cumulative = 0.0
    cursor = start_d
    while cursor <= today_d:
        ds        = cursor.strftime('%Y-%m-%d')
        day_pnl   = daily_map.get(ds, 0.0)
        cumulative = round(cumulative + day_pnl, 2)
        # On today's point, fold in open unrealized so chart tip == Total P&L tile
        displayed_cumulative = round(cumulative + open_unrealized_pnl, 2) if cursor == today_d else cumulative
        daily_pnl_series.append({
            'date':           ds,
            'daily_pnl':      round(day_pnl, 2),
            'cumulative_pnl': displayed_cumulative,
        })
        cursor += timedelta(days=1)

    return {
        'leaps': {
            'current':             latest_leaps,
            'series':              leap_series,
            'total_contracts':     total_contracts,
            'total_cost':          total_cost,
            'total_unrealized_pnl': total_unrealized,
            'total_delta':         total_delta,
            'pmcc_deltas':         pmcc_deltas,
            'baseline_contracts':  baseline_contracts,
            'extra_contracts':     extra_contracts,
            'extra_contracts_value': extra_contracts_value,
        },
        'short_calls': {
            'all':  sorted(short_calls, key=lambda x: x.get('open_date', ''), reverse=True),
            'stats': {
                'total_pnl':          total_pnl,
                'total_realized_pnl': total_realized,
                'open_unrealized_pnl': open_unrealized_pnl,
                'open_current_value': open_current_value,
                'win_rate':           win_rate,
                'avg_pnl':            avg_pnl,
                'closed_count':       len(closed_calls),
                'open_count':         len(open_calls),
            },
            'daily_pnl_series': daily_pnl_series,
        },
        'settings': {
            'auto_sync': bool(config.get('pmcc_auto_sync', False)),
        },
    }


def _do_pmcc_sync(
    email: str,
    ibkr_token: str = None,
    ibkr_query_id: str = None,
    *,
    trades=None,
    positions=None,
) -> dict:
    """Core PMCC sync logic — used by both the HTTP endpoint and the background scheduler.

    When *trades* and *positions* are provided (pre-parsed by the nightly job that
    already fetched the Flex report for another purpose) the fetch step is skipped,
    saving one IBKR API call.  If either is absent the report is fetched fresh using
    *ibkr_token* / *ibkr_query_id*.
    """
    if trades is None or positions is None:
        xml_content = fetch_flex_report(ibkr_token, ibkr_query_id)
        trades      = parse_trades_from_xml(xml_content)
        positions   = parse_positions_from_xml(xml_content)
    leap_positions = parse_leap_positions(positions)

    if not leap_positions:
        return {
            'status':          'success',
            'message':         'No long call (LEAP) positions found in the flex report.',
            'leaps_found':     0,
            'calls_processed': 0,
        }

    leap_symbols = {lp['symbol'] for lp in leap_positions}
    today        = datetime.utcnow().strftime('%Y-%m-%d')
    save_pmcc_leap_snapshot(email, today, leap_positions)

    short_calls = build_pmcc_short_calls(trades, leap_symbols)

    # Enrich open short calls with current mark price from today's positions
    short_call_marks = {
        (p['symbol'], p.get('strike')): p.get('mark_price', 0.0)
        for p in positions
        if p.get('asset_category') == 'OPT'
        and p.get('put_call') == 'C'
        and float(p.get('position', 0)) < 0
    }
    for call in short_calls:
        if call.get('status') == 'open':
            key = (call['symbol'], call.get('strike'))
            if key in short_call_marks:
                call['mark_price'] = short_call_marks[key]

    calls_saved = save_pmcc_short_calls(email, short_calls) if short_calls else 0

    return {
        'status':          'success',
        'leaps_found':     len(leap_positions),
        'leap_symbols':    sorted(leap_symbols),
        'snapshot_date':   today,
        'calls_processed': len(short_calls),
        'calls_saved':     calls_saved,
        'open_calls':      sum(1 for c in short_calls if c['status'] == 'open'),
        'closed_calls':    sum(1 for c in short_calls if c['status'] == 'closed'),
        'expired_calls':   sum(1 for c in short_calls if c['status'] == 'expired'),
    }


@router.post("/sync")
def sync_futuristic_wheel(user: dict = Depends(verify_token)):
    """Sync LEAP positions and PMCC short call history from IBKR flex report."""
    email  = user.get('email')
    config = get_user_config(email)
    if not config:
        raise HTTPException(status_code=404, detail='User configuration not found')
    ibkr_token    = config.get('ibkr_token')
    ibkr_query_id = config.get('ibkr_query_id')
    if not ibkr_token or not ibkr_query_id:
        raise HTTPException(status_code=400,
            detail='IBKR token and query_id must be configured in Account Settings')
    try:
        return _do_pmcc_sync(email, ibkr_token, ibkr_query_id)
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f'Sync failed: {str(e)}')


@router.put("/auto-sync")
def set_auto_sync(body: AutoSyncToggle, user: dict = Depends(verify_token)):
    """Toggle daily automatic PMCC sync for this user (runs at 02:00 CET)."""
    email = user.get('email')
    update_user_config(email, {'pmcc_auto_sync': body.enabled})
    return {'status': 'success', 'auto_sync': body.enabled}


@router.delete("/purge-calls")
def purge_short_calls(user: dict = Depends(verify_token)):
    """One-time purge of all stored PMCC short call records for this user."""
    from database import get_pmcc_short_calls
    from boto3.dynamodb.conditions import Key
    import boto3, os
    from botocore.exceptions import ClientError

    email = user.get('email')
    table_name = os.getenv("DYNAMODB_PMCC_SHORT_CALLS_TABLE", "pmcc_short_calls")
    dynamodb = boto3.resource('dynamodb', region_name=os.getenv("AWS_REGION", "eu-central-1"))
    table = dynamodb.Table(table_name)

    try:
        response = table.query(KeyConditionExpression=Key('username').eq(email))
        items = response.get('Items', [])
        while 'LastEvaluatedKey' in response:
            response = table.query(
                KeyConditionExpression=Key('username').eq(email),
                ExclusiveStartKey=response['LastEvaluatedKey'],
            )
            items.extend(response.get('Items', []))

        if items:
            with table.batch_writer() as batch:
                for item in items:
                    batch.delete_item(Key={'username': item['username'], 'call_id': item['call_id']})

        return {'status': 'success', 'deleted': len(items)}
    except ClientError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/delta")
def update_delta(body: DeltaUpdate, user: dict = Depends(verify_token)):
    """Save the manual per-contract delta for a LEAP symbol."""
    email = user.get('email')
    # Stored as flat key to avoid DynamoDB nested-map type issues with floats
    key     = f"pmcc_delta_{body.symbol}"
    success = update_user_config(email, {key: str(body.delta)})
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save delta")
    return {'status': 'success', 'symbol': body.symbol, 'delta': body.delta}


@router.get("/market-data")
def get_market_data(user: dict = Depends(verify_token)):
    """Fetch live underlying price and LEAP option greeks from Alpha Vantage.

    Makes two Alpha Vantage calls per symbol:
      1. GLOBAL_QUOTE  → current underlying price
      2. REALTIME_OPTIONS → full options chain with greeks; matched to held LEAP
         by strike + expiry to return delta and gamma.

    This endpoint is intentionally manual (not automatic) to stay within the
    Alpha Vantage free-tier limit of 25 requests / day.
    """
    import os, time
    import requests as req

    email   = user.get('email')
    api_key = os.getenv('ALPHA_VANTAGE_API_KEY')
    if not api_key:
        raise HTTPException(status_code=500,
            detail='Alpha Vantage API key not configured on the server')

    snapshots = get_pmcc_leap_snapshots(email)
    if not snapshots:
        return {'results': {}}

    latest_date  = max(s.get('snapshot_date', '') for s in snapshots)
    latest_leaps = [s for s in snapshots if s.get('snapshot_date') == latest_date]

    AV_BASE = 'https://www.alphavantage.co/query'

    # ── Group leaps by symbol ─────────────────────────────────────────────────
    by_symbol: dict = {}
    for leap in latest_leaps:
        sym = leap.get('symbol', '')
        if not sym:
            continue
        raw_expiry = (leap.get('expiry') or '')[:10]
        # Normalise YYYYMMDD → YYYY-MM-DD so it matches Alpha Vantage's format
        if raw_expiry and len(raw_expiry) == 8 and '-' not in raw_expiry:
            raw_expiry = f"{raw_expiry[:4]}-{raw_expiry[4:6]}-{raw_expiry[6:8]}"
        try:
            strike = float(leap.get('strike') or 0)
        except (ValueError, TypeError):
            strike = 0.0
        if sym not in by_symbol:
            by_symbol[sym] = []
        by_symbol[sym].append({'strike': strike, 'expiry': raw_expiry})

    results: dict = {}
    for symbol, leaps_for_sym in by_symbol.items():
        sym_result: dict = {'price': None, 'leaps': []}

        # ── 1. Underlying price ───────────────────────────────────────────────
        try:
            r    = req.get(AV_BASE, params={
                'function': 'GLOBAL_QUOTE', 'symbol': symbol, 'apikey': api_key,
            }, timeout=10)
            data = r.json()
            if 'Note' in data or 'Information' in data:
                sym_result['price_error'] = (
                    data.get('Note') or data.get('Information', 'API rate limit reached'))
            else:
                price_str = data.get('Global Quote', {}).get('05. price', '')
                sym_result['price'] = float(price_str) if price_str else None
        except Exception as e:
            sym_result['price_error'] = str(e)

        time.sleep(0.3)   # brief pause between consecutive AV calls

        # ── 2. Options chain with greeks ──────────────────────────────────────
        try:
            r    = req.get(AV_BASE, params={
                'function': 'REALTIME_OPTIONS', 'symbol': symbol, 'apikey': api_key,
            }, timeout=20)
            data = r.json()
            if 'Note' in data or 'Information' in data:
                sym_result['greeks_error'] = (
                    data.get('Note') or data.get('Information', 'API rate limit reached'))
                options_list = []
            else:
                options_list = data.get('data', [])

            for leap_info in leaps_for_sym:
                greek_entry: dict = {
                    'strike': leap_info['strike'],
                    'expiry': leap_info['expiry'],
                    'delta':  None,
                    'gamma':  None,
                }
                for opt in options_list:
                    if opt.get('type', '').lower() != 'call':
                        continue
                    try:
                        opt_strike = float(opt.get('strike', 0))
                    except (ValueError, TypeError):
                        continue
                    opt_expiry = (opt.get('expiration', '') or '')[:10]
                    if (abs(opt_strike - leap_info['strike']) < 0.01
                            and opt_expiry == leap_info['expiry']):
                        for greek in ('delta', 'gamma'):
                            try:
                                val = opt.get(greek, '')
                                greek_entry[greek] = (
                                    float(val) if val not in (None, '', 'None') else None)
                            except (ValueError, TypeError):
                                pass
                        break
                sym_result['leaps'].append(greek_entry)

        except Exception as e:
            sym_result['greeks_error'] = str(e)
            for leap_info in leaps_for_sym:
                sym_result['leaps'].append({
                    'strike': leap_info['strike'],
                    'expiry': leap_info['expiry'],
                    'delta':  None,
                    'gamma':  None,
                })

        results[symbol] = sym_result

    return {'results': results}
