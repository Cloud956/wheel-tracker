from typing import List, Dict, Optional, Any
from datetime import datetime
from pydantic import BaseModel
from models import CategorizedTrade, ActionType, Wheel, WheelPhase

def identify_new_wheels(categorized_trades: List[CategorizedTrade], username: str) -> List[Wheel]:
    """
    Scans categorized trades and identifies ONLY new wheels that should be opened.
    Returns a list of newly created Wheel objects.
    
    This function looks for ActionType.OPEN_WHEEL (Sell Put) that marks the start of a cycle.
    """
    new_wheels: List[Wheel] = []
    
    for c_trade in categorized_trades:
        # Check if this trade initiates a wheel
        if c_trade.category == ActionType.OPEN_WHEEL:
            symbol = c_trade.trade.symbol
            
            # Create the new wheel object
            # Using IB Exec ID in wheel ID to ensure uniqueness
            exec_suffix = c_trade.trade.ib_exec_id if c_trade.trade.ib_exec_id else c_trade.trade.datetime.strftime('%H%M%S')
            
            new_wheel = Wheel(
                wheel_id=f"WHEEL_{username}_{symbol}_{c_trade.trade.datetime.strftime('%Y%m%d')}_{exec_suffix}",
                symbol=symbol,
                strike=c_trade.trade.strike,
                start_date=c_trade.trade.datetime,
                is_open=True,
                phase=WheelPhase.CSP.value,
                trades=[c_trade]
            )
            
            # Calculate initial PnL (Premium received)
            multiplier = 100.0
            raw_commission = c_trade.trade.ib_commission 
            cash = -(c_trade.trade.quantity * c_trade.trade.trade_price * multiplier) + raw_commission
            new_wheel.total_pnl = cash
            new_wheel.total_commissions = raw_commission
            
            new_wheels.append(new_wheel)
            
    return new_wheels

def merge_new_wheels(new_wheels: List[Wheel], existing_wheels: List[Wheel]) -> List[Wheel]:
    """
    Merges newly identified wheels with the existing list.
    1. Filters out duplicates (wheels that already exist).
    2. Returns the COMBINED list of all wheels.
    """
    combined_wheels: List[Wheel] = list(existing_wheels)
    existing_ids = {w.wheel_id for w in existing_wheels}

    # Add ONLY unique new wheels
    for wheel in new_wheels:
        if wheel.wheel_id not in existing_ids:
            combined_wheels.append(wheel)
            
    return combined_wheels

def recalculate_wheel_pnl(wheel: Wheel):
    """Recalculates PnL and commissions for a wheel based on its trades."""
    cash = 0.0
    comm = 0.0
    for ct in wheel.trades:
        multiplier = 100.0
        if ct.trade.asset_category == 'STK':
            multiplier = 1.0  # Price is per share, quantity is shares.
            
        trade_cash = -(ct.trade.quantity * ct.trade.trade_price * multiplier) + ct.trade.ib_commission
        cash += trade_cash
        comm += ct.trade.ib_commission
        
    wheel.total_pnl = cash
    wheel.total_commissions = comm


def _find_open_wheel_for_trade(open_wheels_map: Dict[str, List[Wheel]], c_trade: CategorizedTrade) -> Optional[Wheel]:
    """
    Finds the best matching open wheel for a given trade based on symbol and phase.
    
    Matching rules by trade category:
    - CLOSE_WHEEL_PUT:    wheel must be in CSP phase, strike must match initial put strike
    - ASSIGNMENT_PUT:     wheel must be in CSP phase, symbol match is sufficient (strike is on option)
    - SELL_COVERED_CALL:  wheel must be in SHARES_HELD phase (shares are held, selling a call against them)
    - CLOSE_CALL:         wheel must be in COVERED_CALL phase, strike must match currentSoldCall
    - ASSIGNMENT_CALL:    wheel must be in COVERED_CALL phase, strike must match currentSoldCall
    """
    symbol = c_trade.trade.symbol
    if symbol not in open_wheels_map:
        return None
    
    candidate_wheels = open_wheels_map[symbol]
    # Sort by start_date (oldest first) to process wheels in chronological order
    candidate_wheels.sort(key=lambda w: w.start_date)
    
    for wheel in candidate_wheels:
        if not wheel.is_open:
            continue
        
        # Check existing trade IDs to avoid duplicates
        existing_ids = {t.trade.trade_id for t in wheel.trades}
        if c_trade.trade.trade_id in existing_ids:
            continue
            
        phase = wheel.phase
        
        if c_trade.category == ActionType.CLOSE_WHEEL_PUT:
            # Must be in CSP phase; strike must match the initial sold put
            if phase == WheelPhase.CSP.value:
                if wheel.strike == c_trade.trade.strike:
                    return wheel
                    
        elif c_trade.category == ActionType.ASSIGNMENT_PUT:
            # Must be in CSP phase; symbol match + strike match to the initial put
            if phase == WheelPhase.CSP.value:
                if wheel.strike == c_trade.trade.strike:
                    return wheel
                    
        elif c_trade.category == ActionType.SELL_COVERED_CALL:
            # Must be in SHARES_HELD phase (holding shares from put assignment)
            if phase == WheelPhase.SHARES_HELD.value:
                return wheel
                
        elif c_trade.category in (ActionType.CLOSE_CALL, ActionType.ASSIGNMENT_CALL):
            # Must be in COVERED_CALL phase; strike must match the active sold call
            if phase == WheelPhase.COVERED_CALL.value and wheel.currentSoldCall:
                if wheel.currentSoldCall.strike == c_trade.trade.strike:
                    return wheel
    
    return None


def process_wheels(wheels: List[Wheel], categorized_trades: List[CategorizedTrade]) -> List[Wheel]:
    """
    Updates existing wheels with subsequent trades across the full wheel lifecycle.
    
    Wheel lifecycle:
      1. OPEN_WHEEL (Sell Put)       → creates wheel in CSP phase     [handled by identify_new_wheels]
      2a. CLOSE_WHEEL_PUT (Buy Put)  → closes wheel (put bought back, no assignment)
      2b. ASSIGNMENT_PUT             → transitions to SHARES_HELD phase
      3.  SELL_COVERED_CALL          → transitions to COVERED_CALL phase, sets currentSoldCall
      4a. CLOSE_CALL (Buy Call back) → clears currentSoldCall, transitions back to SHARES_HELD
      4b. ASSIGNMENT_CALL            → closes wheel (shares sold at strike)
    
    Steps 3→4a can repeat (sell another call, buy it back, sell another...).
    """
    # 1. Build map of open wheels by symbol
    open_wheels_map: Dict[str, List[Wheel]] = {}
    consumed_trade_ids = set()
    
    for w in wheels:
        for t in w.trades:
            consumed_trade_ids.add(t.trade.trade_id)
        if w.is_open:
            if w.symbol not in open_wheels_map:
                open_wheels_map[w.symbol] = []
            open_wheels_map[w.symbol].append(w)
    
    # 2. Process trades in chronological order
    sorted_trades = sorted(categorized_trades, key=lambda x: x.trade.datetime)

    for c_trade in sorted_trades:
        if c_trade.trade.trade_id in consumed_trade_ids:
            continue
        
        # OPEN_WHEEL is already handled by identify_new_wheels
        if c_trade.category == ActionType.OPEN_WHEEL:
            continue
        
        # Find the matching open wheel for this trade
        wheel = _find_open_wheel_for_trade(open_wheels_map, c_trade)
        if not wheel:
            print(f"WARN: No matching open wheel for {c_trade.category.value} "
                  f"on {c_trade.trade.symbol} @ {c_trade.trade.datetime}")
            continue
        
        # Attach the trade to the wheel
        wheel.trades.append(c_trade)
        consumed_trade_ids.add(c_trade.trade.trade_id)
        
        # --- State transitions ---
        
        if c_trade.category == ActionType.CLOSE_WHEEL_PUT:
            # Put bought back in CSP phase → wheel is done (no shares ever held)
            wheel.is_open = False
            wheel.end_date = c_trade.trade.datetime
            wheel.phase = WheelPhase.CSP.value  # stays CSP, just closed
            print(f"WHEEL CLOSED (put buyback): {wheel.wheel_id}")
            
        elif c_trade.category == ActionType.ASSIGNMENT_PUT:
            # Put assigned → now holding 100 shares, transition to SHARES_HELD
            wheel.phase = WheelPhase.SHARES_HELD.value
            # Update strike to the assignment price (should be same as put strike)
            print(f"WHEEL ASSIGNED (put): {wheel.wheel_id} → SHARES_HELD")
            
        elif c_trade.category == ActionType.SELL_COVERED_CALL:
            # Sold a covered call against held shares
            wheel.phase = WheelPhase.COVERED_CALL.value
            wheel.currentSoldCall = c_trade.trade
            print(f"WHEEL COVERED CALL SOLD: {wheel.wheel_id} "
                  f"strike={c_trade.trade.strike} → COVERED_CALL")
            
        elif c_trade.category == ActionType.CLOSE_CALL:
            # Bought back the covered call (no assignment) → still holding shares
            wheel.phase = WheelPhase.SHARES_HELD.value
            wheel.currentSoldCall = None
            print(f"WHEEL CALL CLOSED (buyback): {wheel.wheel_id} → SHARES_HELD")
            
        elif c_trade.category == ActionType.ASSIGNMENT_CALL:
            # Call assigned → shares sold, wheel is complete
            wheel.is_open = False
            wheel.end_date = c_trade.trade.datetime
            wheel.currentSoldCall = None
            print(f"WHEEL CLOSED (call assignment): {wheel.wheel_id}")
    
    # 3. Recalculate PnL for ALL wheels
    for w in wheels:
        recalculate_wheel_pnl(w)
        
    return wheels
