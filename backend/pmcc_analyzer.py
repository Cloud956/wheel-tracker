"""
pmcc_analyzer.py
Parses IBKR flex report data for the Futuristic Wheel / PMCC module.

- parse_leap_positions : filter open positions to find held LEAP (long call) positions
- build_pmcc_short_calls : match short call opens → closes (or expired) from trade history
"""
from typing import List, Dict, Optional, Set
from datetime import datetime, date
import re
from models import Trade


# ── Helpers ───────────────────────────────────────────────────────────────────

def parse_expiry_from_description(description: str) -> Optional[date]:
    """
    Parse expiry date from IBKR option description strings.

    Handled formats
    ---------------
    "GOOGL 20APR26 180.0 C"  →  date(2026, 4, 20)
    "GOOGL 17APR26 180 C"    →  date(2026, 4, 17)
    "20260417"               →  date(2026, 4, 17)   (YYYYMMDD bare)
    """
    if not description:
        return None

    MONTH_MAP = {
        'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
        'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
    }

    # Pattern 1: DDMonYY[YY]  e.g. "20APR26" or "20APR2026"
    m = re.search(r'\b(\d{1,2})([A-Z]{3})(\d{2,4})\b', description.upper())
    if m:
        day = int(m.group(1))
        mon = MONTH_MAP.get(m.group(2))
        yr_str = m.group(3)
        if mon:
            yr = int(yr_str) + (2000 if len(yr_str) == 2 else 0)
            try:
                return date(yr, mon, day)
            except ValueError:
                pass

    # Pattern 2: YYYYMMDD bare number  e.g. "20260417"
    m2 = re.search(r'\b(20\d{6})\b', description)
    if m2:
        ds = m2.group(1)
        try:
            return date(int(ds[:4]), int(ds[4:6]), int(ds[6:8]))
        except ValueError:
            pass

    return None


# ── LEAP positions ─────────────────────────────────────────────────────────────

def parse_leap_positions(positions: List[Dict]) -> List[Dict]:
    """
    Filter open positions to find LEAP positions (long calls, position > 0).

    Returns a list of dicts suitable for snapshot saving:
        symbol, contracts, strike, expiry, cost_basis, mark_price,
        unrealized_pnl, multiplier
    """
    leaps = []
    for pos in positions:
        if (
            pos.get('put_call') == 'C'
            and float(pos.get('position', 0)) > 0
            and pos.get('asset_category') == 'OPT'
        ):
            expiry_raw = pos.get('expiry')  # from parse_positions_from_xml extension
            leaps.append({
                'symbol':        pos['symbol'],
                'contracts':     int(float(pos['position'])),
                'strike':        pos.get('strike'),
                'expiry':        str(expiry_raw) if expiry_raw else None,
                'cost_basis':    float(pos.get('cost_basis_price', 0.0)),
                'mark_price':    float(pos.get('mark_price', 0.0)),
                'unrealized_pnl': float(pos.get('fifo_pnl_unrealized', 0.0)),
                'multiplier':    float(pos.get('multiplier', 100.0)),
            })
    return leaps


# ── PMCC short call matching ──────────────────────────────────────────────────

def build_pmcc_short_calls(trades: List[Trade], leap_symbols: Set[str]) -> List[Dict]:
    """
    From full trade history, extract and match PMCC short call cycles.

    Only considers calls on symbols in `leap_symbols`.

    Logic
    -----
    - Short call OPEN  : put_call='C', quantity < 0
    - Short call CLOSE : put_call='C', quantity > 0, matching symbol+strike+expiry, after open
    - Expired worthless: no matching close found AND expiry date is in the past
      → status='expired', pnl = full premium (minus open commission)
    - Still open       : no matching close, expiry still future
      → status='open', pnl=None

    NOTE: LEAP purchases (long calls, qty>0) will NOT match any short call open
    because they have different strikes/expiries — they are silently ignored.

    Returns list sorted by open_date descending.
    """
    today = date.today()
    short_opens: List[Dict] = []
    short_closes: List[Dict] = []

    for t in sorted(trades, key=lambda x: x.datetime):
        if t.asset_category != 'OPT' or t.put_call != 'C':
            continue
        if t.symbol not in leap_symbols:
            continue
        expiry = parse_expiry_from_description(t.description or '')
        if t.quantity < 0:
            short_opens.append({'trade': t, 'expiry': expiry})
        elif t.quantity > 0:
            short_closes.append({'trade': t, 'expiry': expiry})

    result: List[Dict] = []
    consumed_close_ids: Set[str] = set()

    for open_item in short_opens:
        ot: Trade = open_item['trade']
        open_expiry: Optional[date] = open_item['expiry']

        matched_close = None
        for close_item in short_closes:
            ct: Trade = close_item['trade']
            if ct.trade_id in consumed_close_ids:
                continue
            if ct.symbol != ot.symbol:
                continue
            # Strike must match when both are known
            if ot.strike is not None and ct.strike is not None and ct.strike != ot.strike:
                continue
            # Expiry must match when both are parseable
            close_expiry: Optional[date] = close_item['expiry']
            if open_expiry and close_expiry and open_expiry != close_expiry:
                continue
            # Close must come after open
            if ct.datetime <= ot.datetime:
                continue
            # Contracts (absolute qty) must match
            if abs(ct.quantity) != abs(ot.quantity):
                continue
            matched_close = close_item
            consumed_close_ids.add(ct.trade_id)
            break

        # Build deterministic call_id
        # Use trade_id (derived from ib_exec_id) to guarantee uniqueness even with
        # partial fills at the same timestamp.
        expiry_str = open_expiry.strftime('%Y-%m-%d') if open_expiry else None
        expiry_id  = open_expiry.strftime('%Y%m%d')   if open_expiry else 'NOEXP'
        strike_id  = str(int(ot.strike)) if ot.strike else 'NOSTRIKE'
        call_id    = f"{ot.symbol}_{expiry_id}_{strike_id}_{ot.trade_id}"

        contracts        = int(abs(ot.quantity))
        premium_received = round(contracts * ot.trade_price * 100.0, 2)
        open_commission  = float(ot.ib_commission)   # negative value from IBKR

        if matched_close:
            ct              = matched_close['trade']
            close_cost      = round(int(abs(ct.quantity)) * ct.trade_price * 100.0, 2)
            close_commission = float(ct.ib_commission)
            # pnl = credit received - cost to close + commissions (all commissions are negative)
            pnl             = round(premium_received - close_cost + open_commission + close_commission, 2)
            status          = 'closed'
            close_date      = ct.datetime.isoformat()
            close_price     = ct.trade_price
            close_commission_val = close_commission

        elif open_expiry and open_expiry < today:
            # Expired worthless — full premium profit (minus open commission)
            close_cost           = 0.0
            close_commission_val = 0.0
            pnl                  = round(premium_received + open_commission, 2)
            status               = 'expired'
            close_date           = expiry_str   # expiry date acts as effective close
            close_price          = 0.0

        else:
            close_cost           = 0.0
            close_commission_val = 0.0
            pnl                  = None
            status               = 'open'
            close_date           = None
            close_price          = None

        result.append({
            'call_id':          call_id,
            'symbol':           ot.symbol,
            'strike':           ot.strike,
            'expiry':           expiry_str,
            'contracts':        contracts,
            'open_date':        ot.datetime.isoformat(),
            'open_price':       ot.trade_price,
            'open_commission':  open_commission,
            'close_date':       close_date,
            'close_price':      close_price,
            'close_commission': close_commission_val,
            'status':           status,
            'pnl':              pnl,
            'premium_received': premium_received,
        })

    result.sort(key=lambda x: x['open_date'], reverse=True)
    return result
