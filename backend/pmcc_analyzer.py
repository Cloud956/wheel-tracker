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

def build_pmcc_short_calls(trades, leap_symbols):
    """
    Build PMCC short call history using a session-based approach:
      1. Filter to calls on leap_symbols opened on/after START_DATE.
      2. Merge same-day partial fills (symbol + strike + expiry + date).
      3. Build sessions: consecutive daily-opens for the same (symbol, strike, expiry)
         are accumulated into one position until a matching close is found.
         Adding contracts on a subsequent day ("add-on") is folded into the
         existing open session; the blended cost basis is recomputed.
      4. Unmatched sessions past their expiry → 'expired'; future → 'open'.

    Returns list of call records sorted by open_date descending.
    """
    today = date.today()

    # ── Step 1: Collect raw opens and closes ─────────────────────────────────
    raw_opens  = []
    raw_closes = []

    for t in sorted(trades, key=lambda x: x.datetime):
        if t.asset_category != 'OPT' or t.put_call != 'C':
            continue
        if t.symbol not in leap_symbols:
            continue

        expiry = _to_date(getattr(t, 'expiry', None))
        if expiry is None:
            expiry = parse_expiry_from_description(t.description or '')

        if t.quantity < 0:      # Short call open
            if t.datetime.date() < START_DATE:
                continue
            raw_opens.append({'trade': t, 'expiry': expiry})
        elif t.quantity > 0:    # Buy-back / close
            raw_closes.append({'trade': t, 'expiry': expiry})

    print(f"[PMCC] raw_opens: {len(raw_opens)}, raw_closes: {len(raw_closes)}")
    for item in raw_opens:
        t = item['trade']
        print(f"  OPEN  {t.symbol} strike={t.strike} qty={t.quantity} "
              f"date={t.datetime.date()} expiry={item['expiry']}")
    for item in raw_closes:
        t = item['trade']
        print(f"  CLOSE {t.symbol} strike={t.strike} qty={t.quantity} "
              f"date={t.datetime.date()} expiry={item['expiry']}")

    # ── Step 2: Merge same-day partial fills ──────────────────────────────────
    def fill_key(item):
        """Group by (symbol, strike, expiry, trading-date) to merge intraday fills."""
        t         = item['trade']
        exp_id    = item['expiry'].strftime('%Y%m%d') if item['expiry'] else 'NOEXP'
        strike_id = str(t.strike) if t.strike is not None else 'NOSTRIKE'
        return (t.symbol, strike_id, exp_id, t.datetime.date().isoformat())

    opens_by_day  = defaultdict(list)
    closes_by_day = defaultdict(list)

    for item in raw_opens:
        opens_by_day[fill_key(item)].append(item)
    for item in raw_closes:
        closes_by_day[fill_key(item)].append(item)

    def merge_day_fills(items):
        """Aggregate same-day partial fills into a single daily record."""
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

    # Sorted list of (day_key, merged_record) for opens and closes
    daily_opens = sorted(
        [(k, merge_day_fills(v)) for k, v in opens_by_day.items()],
        key=lambda x: x[0][3],   # sort by date string
    )
    daily_closes = sorted(
        [(k, merge_day_fills(v)) for k, v in closes_by_day.items()],
        key=lambda x: x[0][3],
    )

    # ── Step 3: Session-based matching ───────────────────────────────────────
    # Process opens and closes in chronological order.
    # An "active session" accumulates all consecutive daily-opens for the same
    # position key (symbol, strike, expiry) until a matching close is seen.
    # Add-ons on subsequent days are therefore folded into the same session
    # with a blended (weighted-average) cost basis.

    # Combine into one timeline; on the same date, opens are processed before closes
    events = (
        [(k[3], 0, 'open',  k, mg) for k, mg in daily_opens] +
        [(k[3], 1, 'close', k, mg) for k, mg in daily_closes]
    )
    events.sort(key=lambda x: (x[0], x[1]))

    # active_sessions: pos_key → list of (day_key, merged_record)
    active_sessions = {}
    completed_sessions = []

    for _date_str, _order, event_type, key, mg in events:
        sym, strike_id, exp_id, _day = key
        pos_key = (sym, strike_id, exp_id)

        if event_type == 'open':
            if pos_key not in active_sessions:
                active_sessions[pos_key] = []
            active_sessions[pos_key].append((key, mg))

        else:  # close
            if pos_key in active_sessions:
                session_opens = active_sessions.pop(pos_key)
                completed_sessions.append({
                    'opens':  session_opens,
                    'close':  (key, mg),
                    'expiry': mg['expiry'] or (
                        session_opens[0][1]['expiry'] if session_opens else None),
                })
            # Close with no matching open (pre-START_DATE position) → ignore

    # Remaining active sessions are still open (or expired without a close trade)
    for pos_key, session_opens in active_sessions.items():
        completed_sessions.append({
            'opens':  session_opens,
            'close':  None,
            'expiry': session_opens[0][1]['expiry'] if session_opens else None,
        })

    # ── Step 4: Build result records ─────────────────────────────────────────
    result = []

    for session in completed_sessions:
        opens = session['opens']   # list of (day_key, merged_record)
        if not opens:
            continue

        # Blended stats across all daily-open records in this session
        total_contracts = sum(mg['total_qty']  for _, mg in opens)
        total_open_comm = sum(mg['total_comm'] for _, mg in opens)
        total_open_val  = sum(mg['total_qty'] * mg['avg_price'] for _, mg in opens)
        blended_price   = round(total_open_val / total_contracts, 4) if total_contracts else 0.0

        first_key, first_mg = opens[0]
        last_key,  last_mg  = opens[-1]

        expiry     = session['expiry']
        expiry_str = expiry.strftime('%Y-%m-%d') if expiry else None
        exp_id     = first_key[2]
        strike_id  = first_key[1]
        sym        = first_key[0]

        first_open_date_str = first_key[3]   # YYYY-MM-DD of the first (earliest) open

        # Stable call_id anchored to the first open — add-ons don't change the ID
        call_id          = f"{sym}_{exp_id}_{strike_id}_{first_open_date_str.replace('-', '')}"
        premium_received = round(total_contracts * blended_price * 100.0, 2)

        close = session.get('close')
        if close:
            close_key, close_mg = close
            close_cost       = round(close_mg['total_qty'] * close_mg['avg_price'] * 100.0, 2)
            close_commission = close_mg['total_comm']
            pnl              = round(premium_received - close_cost
                                     + total_open_comm + close_commission, 2)
            status           = 'closed'
            close_date       = close_mg['rep_trade'].datetime.isoformat()
            close_price      = close_mg['avg_price']

        elif expiry and expiry < today:
            close_commission = 0.0
            pnl              = round(premium_received + total_open_comm, 2)
            status           = 'expired'
            close_date       = expiry_str
            close_price      = 0.0

        else:
            close_commission = 0.0
            pnl              = None
            status           = 'open'
            close_date       = None
            close_price      = None

        result.append({
            'call_id':          call_id,
            'symbol':           sym,
            'strike':           first_mg['rep_trade'].strike,
            'expiry':           expiry_str,
            'contracts':        total_contracts,
            'open_date':        first_mg['rep_trade'].datetime.isoformat(),
            'open_price':       blended_price,   # weighted-average across all add-ons
            'open_commission':  total_open_comm,
            'close_date':       close_date,
            'close_price':      close_price,
            'close_commission': close_commission,
            'status':           status,
            'pnl':              pnl,
            'premium_received': premium_received,
        })

    result.sort(key=lambda x: x['open_date'], reverse=True)
    return result
