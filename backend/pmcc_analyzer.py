"""
pmcc_analyzer.py
Parses IBKR flex report data for the Futuristic Wheel / PMCC module.

- parse_leap_positions  : filter open positions to find held LEAP (long call) positions
- build_pmcc_short_calls: group partial fills, match opens→closes, apply START_DATE filter
"""
from typing import List, Dict, Optional, Set
from datetime import datetime, date
from collections import defaultdict
import re
from models import Trade


# Only track short calls opened on or after this date
START_DATE = date(2026, 2, 20)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _to_date(val: Optional[str]) -> Optional[date]:
    """Convert a YYYYMMDD[...] string to a date, ignoring trailing chars/decimals."""
    if not val:
        return None
    try:
        return datetime.strptime(str(val)[:8], "%Y%m%d").date()
    except (ValueError, TypeError):
        return None


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
    Build PMCC short call history by:
      1. Filtering to calls on leap_symbols opened on/after START_DATE
      2. Grouping partial fills (same symbol + strike + expiry + trading date)
      3. Matching grouped opens to grouped closes chronologically
      4. Marking unmatched past-expiry opens as 'expired', future as 'open'

    Returns list of call records sorted by open_date descending.
    """
    today = date.today()

    # ── Step 1: Collect raw opens and closes ─────────────────────────────────
    raw_opens: List[Dict] = []
    raw_closes: List[Dict] = []

    for t in sorted(trades, key=lambda x: x.datetime):
        if t.asset_category != 'OPT' or t.put_call != 'C':
            continue
        if t.symbol not in leap_symbols:
            continue

        # Prefer expiry from Trade.expiry (from XML), fall back to description parsing
        expiry: Optional[date] = _to_date(getattr(t, 'expiry', None))
        if expiry is None:
            expiry = parse_expiry_from_description(t.description or '')

        if t.quantity < 0:    # Short call open
            if t.datetime.date() < START_DATE:
                continue      # Ignore pre-start trades
            raw_opens.append({'trade': t, 'expiry': expiry})
        elif t.quantity > 0:  # Buy-back / close
            raw_closes.append({'trade': t, 'expiry': expiry})

    # ── Step 2: Group partial fills ───────────────────────────────────────────
    print(f"[PMCC] raw_opens: {len(raw_opens)}, raw_closes: {len(raw_closes)}")
    for item in raw_opens:
        t = item['trade']
        print(f"  OPEN  {t.symbol} strike={t.strike} qty={t.quantity} date={t.datetime.date()} expiry={item['expiry']} trade_expiry={t.expiry}")
    for item in raw_closes:
        t = item['trade']
        print(f"  CLOSE {t.symbol} strike={t.strike} qty={t.quantity} date={t.datetime.date()} expiry={item['expiry']} trade_expiry={t.expiry}")
    def fill_key(item: Dict) -> tuple:
        t         = item['trade']
        exp_id    = item['expiry'].strftime('%Y%m%d') if item['expiry'] else 'NOEXP'
        # Use the raw strike float as string (e.g. "317.5" not "317")
        strike_id = str(t.strike) if t.strike is not None else 'NOSTRIKE'
        return (t.symbol, strike_id, exp_id, t.datetime.date().isoformat())

    opens_by_key:  Dict[tuple, List] = defaultdict(list)
    closes_by_key: Dict[tuple, List] = defaultdict(list)

    for item in raw_opens:
        opens_by_key[fill_key(item)].append(item)
    for item in raw_closes:
        closes_by_key[fill_key(item)].append(item)

    def merge_fills(items: List[Dict]) -> Dict:
        """Aggregate partial fills of the same group into one combined entry."""
        total_qty  = sum(abs(i['trade'].quantity) for i in items)
        total_comm = sum(i['trade'].ib_commission for i in items)
        total_val  = sum(abs(i['trade'].quantity) * i['trade'].trade_price for i in items)
        avg_price  = total_val / total_qty if total_qty > 0 else 0.0
        return {
            'rep_trade':  items[0]['trade'],
            'expiry':     items[0]['expiry'],
            'total_qty':  int(total_qty),
            'avg_price':  round(avg_price, 4),
            'total_comm': total_comm,
        }

    # Sort merged opens chronologically
    merged_opens = sorted(
        [(k, merge_fills(v)) for k, v in opens_by_key.items()],
        key=lambda x: x[1]['rep_trade'].datetime,
    )
    # Build merged closes lookup
    merged_closes: Dict[tuple, Dict] = {k: merge_fills(v) for k, v in closes_by_key.items()}

    # ── Step 3: Match each open group to a close group ────────────────────────
    consumed_close_keys: Set[tuple] = set()
    result: List[Dict] = []

    for open_key, open_mg in merged_opens:
        sym, strike_id, expiry_id, open_date_str = open_key
        ot          = open_mg['rep_trade']
        open_expiry = open_mg['expiry']

        contracts        = open_mg['total_qty']
        premium_received = round(contracts * open_mg['avg_price'] * 100.0, 2)
        open_commission  = open_mg['total_comm']

        # Stable call_id based on group key (not per-fill trade_id)
        call_id    = f"{sym}_{expiry_id}_{strike_id}_{open_date_str.replace('-', '')}"
        expiry_str = open_expiry.strftime('%Y-%m-%d') if open_expiry else None

        # Find earliest close matching symbol+strike, strictly after open date.
        # Expiry must match when BOTH sides have it; if either is NOEXP, match on symbol+strike alone.
        matched_close = None
        for close_key in sorted(merged_closes.keys(), key=lambda k: k[3]):
            if close_key in consumed_close_keys:
                continue
            c_sym, c_strike_id, c_expiry_id, c_date_str = close_key
            if c_sym != sym or c_strike_id != strike_id:
                continue
            if c_expiry_id != expiry_id and c_expiry_id != 'NOEXP' and expiry_id != 'NOEXP':
                continue
            if c_date_str <= open_date_str:
                continue
            matched_close = (close_key, merged_closes[close_key])
            consumed_close_keys.add(close_key)
            break

        if matched_close:
            _, close_mg          = matched_close
            close_cost           = round(close_mg['total_qty'] * close_mg['avg_price'] * 100.0, 2)
            close_commission     = close_mg['total_comm']
            pnl                  = round(premium_received - close_cost + open_commission + close_commission, 2)
            status               = 'closed'
            close_date           = close_mg['rep_trade'].datetime.isoformat()
            close_price          = close_mg['avg_price']
            close_commission_val = close_commission

        elif open_expiry and open_expiry < today:
            # No close found and expiry is in the past → expired worthless
            close_cost           = 0.0
            close_commission_val = 0.0
            pnl                  = round(premium_received + open_commission, 2)
            status               = 'expired'
            close_date           = expiry_str
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
            'open_price':       open_mg['avg_price'],
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
