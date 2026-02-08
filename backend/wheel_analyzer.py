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

def update_wheels(wheels: List[Wheel], categorized_trades: List[CategorizedTrade]) -> List[Wheel]:
    """
    Updates existing wheels with subsequent trades (Close/Update).
    """
    # 1. Map open wheels by symbol
    open_wheels = {}
    for w in wheels:
        if w.is_open:
            if w.symbol not in open_wheels:
                open_wheels[w.symbol] = w
            else:
                if w.start_date > open_wheels[w.symbol].start_date:
                    open_wheels[w.symbol] = w
    
    # 2. Iterate trades (Assume sorted or sort them)
    sorted_trades = sorted(categorized_trades, key=lambda x: x.trade.datetime)

    for c_trade in sorted_trades:
        # Skip OPEN_WHEEL (already handled by identify_new_wheels and merge)
        if c_trade.category == ActionType.OPEN_WHEEL:
             continue
             
        symbol = c_trade.trade.symbol
        if symbol in open_wheels:
            wheel = open_wheels[symbol]
            
            # Deduplicate by trade_id
            existing_ids = {t.trade.trade_id for t in wheel.trades}
            if c_trade.trade.trade_id in existing_ids:
                # Even if trade exists, check if it should have closed the wheel but didn't?
                # No, if it exists, assume processed. 
                # But wait, what if we just loaded it from DB and it's open, and this trade is IN the list?
                # If the trade is IN the list, it's already processed.
                continue
                
            # Add trade
            wheel.trades.append(c_trade)
            
            # Check closing conditions
            if c_trade.category in (ActionType.CLOSE_WHEEL_PUT, ActionType.ASSIGNMENT_CALL, ActionType.STOCK_SELL):
                wheel.is_open = False
                wheel.end_date = c_trade.trade.datetime
                # Remove from active map
                if open_wheels[symbol] == wheel:
                    del open_wheels[symbol]
        
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
