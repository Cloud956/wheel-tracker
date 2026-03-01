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

    # ── Short call stats ──────────────────────────────────────────────────────
    closed_calls = [c for c in short_calls if c.get('status') in ('closed', 'expired')]
    open_calls   = [c for c in short_calls if c.get('status') == 'open']
    total_premium = round(sum(c.get('premium_received', 0.0) for c in short_calls), 2)
    closed_pnls   = [c['pnl'] for c in closed_calls if c.get('pnl') is not None]
    wins          = [p for p in closed_pnls if p > 0]
    win_rate      = round(len(wins) / len(closed_pnls) * 100, 1) if closed_pnls else 0
    total_realized = round(sum(closed_pnls), 2)
    avg_pnl        = round(total_realized / len(closed_pnls), 2) if closed_pnls else 0

    # ── Daily P&L series (from START_DATE) ───────────────────────────────────
    daily_map: dict = {}
    for c in short_calls:
        if c.get('status') not in ('closed', 'expired'):
            continue
        close_dt = (c.get('close_date') or '')[:10]
        if not close_dt or close_dt < START_DATE:
            continue
        pnl = c.get('pnl') or 0.0
        daily_map[close_dt] = round(daily_map.get(close_dt, 0.0) + pnl, 2)

    daily_pnl_series = []
    cumulative = 0.0
    for d in sorted(daily_map):
        cumulative = round(cumulative + daily_map[d], 2)
        daily_pnl_series.append({
            'date':           d,
            'daily_pnl':      round(daily_map[d], 2),
            'cumulative_pnl': cumulative,
        })

    return {
        'leaps': {
            'current':             latest_leaps,
            'series':              leap_series,
            'total_contracts':     total_contracts,
            'total_cost':          total_cost,
            'total_unrealized_pnl': total_unrealized,
            'total_delta':         total_delta,
            'pmcc_deltas':         pmcc_deltas,
        },
        'short_calls': {
            'all':  sorted(short_calls, key=lambda x: x.get('open_date', ''), reverse=True),
            'stats': {
                'total_premium':     total_premium,
                'total_realized_pnl': total_realized,
                'win_rate':          win_rate,
                'avg_pnl':           avg_pnl,
                'closed_count':      len(closed_calls),
                'open_count':        len(open_calls),
            },
            'daily_pnl_series': daily_pnl_series,
        },
    }


@router.post("/sync")
def sync_futuristic_wheel(user: dict = Depends(verify_token)):
    """Sync LEAP positions and PMCC short call history from IBKR flex report."""
    email = user.get('email')

    config = get_user_config(email)
    if not config:
        raise HTTPException(status_code=404, detail="User configuration not found")

    ibkr_token    = config.get('ibkr_token')
    ibkr_query_id = config.get('ibkr_query_id')
    if not ibkr_token or not ibkr_query_id:
        raise HTTPException(
            status_code=400,
            detail="IBKR token and query_id must be configured in Account Settings"
        )

    try:
        # Fetch and parse flex report
        xml_content  = fetch_flex_report(ibkr_token, ibkr_query_id)
        trades       = parse_trades_from_xml(xml_content)
        positions    = parse_positions_from_xml(xml_content)

        # Identify LEAP (long call) positions
        leap_positions = parse_leap_positions(positions)

        if not leap_positions:
            return {
                'status':          'success',
                'message':         'No long call (LEAP) positions found in the flex report.',
                'leaps_found':     0,
                'calls_processed': 0,
            }

        leap_symbols = {lp['symbol'] for lp in leap_positions}

        # Save daily LEAP snapshot (upserts — re-syncing same day just overwrites)
        today = datetime.utcnow().strftime('%Y-%m-%d')
        save_pmcc_leap_snapshot(email, today, leap_positions)

        # Build and save short call history
        short_calls  = build_pmcc_short_calls(trades, leap_symbols)
        calls_saved  = save_pmcc_short_calls(email, short_calls) if short_calls else 0

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
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


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
