from typing import List, Dict, Optional
from datetime import datetime
from pydantic import BaseModel
from trade_categorizer import CategorizedTrade, ActionType

class Wheel(BaseModel):
    wheel_id: str
    symbol: str
    start_date: datetime
    end_date: Optional[datetime] = None
    is_open: bool = True
    trades: List[CategorizedTrade] = []
    total_pnl: float = 0.0
    total_commissions: float = 0.0

def analyze_wheels(categorized_trades: List[CategorizedTrade]) -> List[Wheel]:
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
                new_wheel = Wheel(
                    wheel_id=f"WHEEL_{symbol}_{c_trade.trade.datetime.strftime('%Y%m%d')}",
                    symbol=symbol,
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
        # comm = 0.0 # Commission not yet tracked in Trade object
        for ct in wheel.trades:
            # Cash flow: -quantity * price * 100 (for options)
            # Quantity < 0 (Sell) -> Cash Positive
            # Quantity > 0 (Buy) -> Cash Negative
            
            # Multiplier usually 100 for standard options
            multiplier = 100.0
            
            cash += -(ct.trade.quantity * ct.trade.trade_price * multiplier)
            
        wheel.total_pnl = cash
        
    return wheels

