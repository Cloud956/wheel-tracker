from typing import List, Dict, Optional, Any
from datetime import datetime
from pydantic import BaseModel
from models import CategorizedTrade, ActionType, Wheel

def identify_new_wheels(categorized_trades: List[CategorizedTrade], username: str) -> List[Wheel]:
    """
    Scans categorized trades and identifies ONLY new wheels that should be opened.
    Returns a list of newly created Wheel objects.
    
    This function looks for ActionType.OPEN_WHEEL (Sell Put) that marks the start of a cycle.
    """
    new_wheels: List[Wheel] = []
    
    # We might want to track active symbols if we want to support multiple concurrent wheels
    # per symbol, but for now assuming one active wheel per symbol strategy is handled elsewhere
    # or simple scan.
    
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
                trades=[c_trade]
            )
            
            # Calculate initial PnL (Premium received)
            multiplier = 100.0
            # Cash flow: premium received - commission paid (commission is usually negative in IBKR reports, but we use abs value in some contexts. 
            # In IBKR Flex, ibCommission is typically negative (cost).
            # Net Cash = -(Quantity * Price * 100) + Commission
            # Quantity < 0 (Sell) -> Positive premium
            
            # Using the parsed positive commission value if we parsed abs, or raw.
            # Assuming ib_commission parsed from 'ibCommission' is negative (cost).
            
            raw_commission = c_trade.trade.ib_commission 
            # If IBKR reports it as negative (e.g. -1.05), we add it. 
            # If we parsed it as positive magnitude, we subtract it.
            # Standard Flex XML usually has negative for cost. Let's assume negative.
            
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
            multiplier = 1.0 # Price is per share, quantity is shares.
            
        trade_cash = -(ct.trade.quantity * ct.trade.trade_price * multiplier) + ct.trade.ib_commission
        cash += trade_cash
        comm += ct.trade.ib_commission
        
    wheel.total_pnl = cash
    wheel.total_commissions = comm

def check_wheel_close_condition(wheel: Wheel, new_trade: CategorizedTrade) -> bool:
    """
    Checks if the wheel should be closed based on the new trade.
    
    Conditions for closing:
    1. It is an open wheel with one trade only (the initial sold put), and that put was bought back.
    2. There was a call being sold, which was now bought back.
    
    Returns:
        bool: True if the wheel should be closed, False otherwise.
    """
    
    print(f"DEBUG: Checking close condition for Wheel {wheel.wheel_id} (Symbol: {wheel.symbol})")
    print(f"DEBUG: New Trade: {new_trade.category} | Qty: {new_trade.trade.quantity} | Strike: {new_trade.trade.strike}")
    
    # Condition 1: Initial Put Bought Back
    # If the wheel has only 2 trades (including the new one), and the new one is CLOSE_WHEEL_PUT
    # We check if the total quantity of the put is now 0.
    if len(wheel.trades) == 1 and new_trade.category == ActionType.CLOSE_WHEEL_PUT:
        # Check if the initial trade was an OPEN_WHEEL put
        first_trade = wheel.trades[0]
        if first_trade.category == ActionType.OPEN_WHEEL:
             # Check if symbol, strike, expiration match for the closing trade
             # We assume matching symbol is guaranteed by calling logic
             # Check strike and expiration if possible (though expiration is date, maybe just strike and type?)
             
             t1 = first_trade.trade
             t2 = new_trade.trade
             
             print(f"DEBUG: Cond 1 Check - Strike match? {t1.strike} vs {t2.strike}")
             
             # Match strike
             if t1.strike == t2.strike and t1.put_call == t2.put_call:
                 # Sum quantities (Sold is negative, Bought is positive). Should be close to 0.
                 return True

    # Condition 2: Sold Call Bought Back (or Assigned)
    
    if new_trade.category in (ActionType.CLOSE_CALL, ActionType.ASSIGNMENT_CALL):
        print(f"DEBUG: Cond 2 Check - Current Sold Call: {wheel.currentSoldCall}")
        # We need to verify if the strike matches the current sold call's strike.
        if wheel.currentSoldCall:
            print(f"DEBUG: Cond 2 Check - Strike match? New: {new_trade.trade.strike} vs Current: {wheel.currentSoldCall.strike}")
            if new_trade.trade.strike == wheel.currentSoldCall.strike:
                return True
        else:
             print("DEBUG: Condition 2 FAILED - No currentSoldCall found to match against")
             return False

    return False

def close_wheels(wheels: List[Wheel], categorized_trades: List[CategorizedTrade]) -> List[Wheel]:
    """
    Updates existing wheels with subsequent trades (Close/Update).
    """
    # 1. Map open wheels by symbol
    # Store list of wheels per symbol to handle multiples if needed, 
    # but for now we look for the most relevant open wheel.
    open_wheels_map: Dict[str, List[Wheel]] = {}
    
    # Track consumed trade IDs to prevent adding the same trade to multiple wheels
    # (or re-adding if logic gets complex, though simple loop helps).
    # Initialize with trade IDs already in wheels
    consumed_trade_ids = set()
    
    for w in wheels:
        for t in w.trades:
            consumed_trade_ids.add(t.trade.trade_id)
            
        if w.is_open:
            if w.symbol not in open_wheels_map:
                open_wheels_map[w.symbol] = []
            open_wheels_map[w.symbol].append(w)
    
    # 2. Iterate trades (Assume sorted or sort them)
    sorted_trades = sorted(categorized_trades, key=lambda x: x.trade.datetime)

    for c_trade in sorted_trades:
        # Check if already consumed
        if c_trade.trade.trade_id in consumed_trade_ids:
            continue
            
        # Skip OPEN_WHEEL (already handled by identify_new_wheels and merge)
        if c_trade.category not in (ActionType.CLOSE_WHEEL_PUT, ActionType.CLOSE_CALL, ActionType.ASSIGNMENT_CALL):
             continue
             
        symbol = c_trade.trade.symbol
        if symbol in open_wheels_map:

            candidate_wheels = open_wheels_map[symbol]
            
            # We sort candidates by start_date desc (newest first)
            candidate_wheels.sort(key=lambda w: w.start_date)
            
            for wheel in candidate_wheels:
                if not wheel.is_open:
                    continue
                
                # Double check existence (redundant if we use consumed_trade_ids correctly but safe)
                existing_ids = {t.trade.trade_id for t in wheel.trades}
                if c_trade.trade.trade_id in existing_ids:
                    continue
                    
                # Check closing conditions using the NEW method
                if check_wheel_close_condition(wheel, c_trade):
                    # Add trade
                    wheel.trades.append(c_trade)
                    wheel.is_open = False
                    wheel.end_date = c_trade.trade.datetime
                    # Mark as consumed
                    consumed_trade_ids.add(c_trade.trade.trade_id)
                    
                    # Break loop since this trade closed THIS wheel.
                    # A single closing trade (e.g. Buy 1 Put) can only close one open wheel (e.g. Sell 1 Put).
                    # If we don't break, this same trade will be applied to ALL matching open wheels.
                    break 
                
        
    # 3. Recalculate Stats for ALL wheels
    for w in wheels:
        recalculate_wheel_pnl(w)
        
    return wheels

def analyze_wheels(categorized_trades: List[CategorizedTrade], username: str) -> List[Wheel]:
    """
    Groups categorized trades into Wheel objects.
    Tracks active wheels per symbol.
    """
    wheels: List[Wheel] = []
    active_wheels: Dict[str, Wheel] = {}
    
    for c_trade in categorized_trades:
        symbol = c_trade.trade.symbol
        
        # Start new wheel
        if c_trade.category == ActionType.OPEN_WHEEL:
            if symbol not in active_wheels:
                exec_suffix = c_trade.trade.ib_exec_id if c_trade.trade.ib_exec_id else c_trade.trade.datetime.strftime('%H%M%S')
                new_wheel = Wheel(
                    wheel_id=f"WHEEL_{username}_{symbol}_{c_trade.trade.datetime.strftime('%Y%m%d')}_{exec_suffix}",
                    symbol=symbol,
                    strike=c_trade.trade.strike,
                    start_date=c_trade.trade.datetime,
                    is_open=True,
                    trades=[c_trade]
                )
                active_wheels[symbol] = new_wheel
                wheels.append(new_wheel)
            else:
                # Append to existing (scaling in) or maybe error? 
                # For now, append to active wheel
                active_wheels[symbol].trades.append(c_trade)
                
        # Close/Update Wheel events
        elif symbol in active_wheels:
            wheel = active_wheels[symbol]
            wheel.trades.append(c_trade)
            
            if c_trade.category in (ActionType.CLOSE_WHEEL_PUT, ActionType.ASSIGNMENT_CALL):
                # These actions typically close the wheel cycle
                # CLOSE_WHEEL_PUT: You bought back the put (profit or loss), no shares.
                # ASSIGNMENT_CALL: You sold the shares.
                wheel.is_open = False
                wheel.end_date = c_trade.trade.datetime
                del active_wheels[symbol]
                
            # ASSIGNMENT_PUT, SELL_COVERED_CALL, CLOSE_CALL keep wheel open
            
        # Ignore orphan closing trades if no wheel open (e.g. historical data cut off)
        
    # Calculate PnL for all wheels
    for wheel in wheels:
        cash = 0.0
        comm = 0.0
        for ct in wheel.trades:
            # Cash flow: -quantity * price * 100 (for options)
            # Quantity < 0 (Sell) -> Cash Positive
            # Quantity > 0 (Buy) -> Cash Negative
            
            # Multiplier usually 100 for standard options
            multiplier = 100.0
            
            # Assuming ib_commission is negative (expense)
            trade_cash = -(ct.trade.quantity * ct.trade.trade_price * multiplier) + ct.trade.ib_commission
            
            cash += trade_cash
            comm += ct.trade.ib_commission
            
        wheel.total_pnl = cash
        wheel.total_commissions = comm
        
    return wheels
