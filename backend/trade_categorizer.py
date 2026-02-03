from enum import Enum
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from pydantic import BaseModel

class ActionType(Enum):
    OPEN_WHEEL = "Put option sold"
    CLOSE_WHEEL_PUT = "Put option bought"
    ASSIGNMENT_PUT = "Put option bought with 100 shares bought"
    SELL_COVERED_CALL = "Call option sold"
    CLOSE_CALL = "Call option bought (without shares sold)"
    ASSIGNMENT_CALL = "Call option bought (with shares sold)"
    
    # Helper for stock trades or others
    STOCK_BUY = "Stock Buy"
    STOCK_SELL = "Stock Sell"
    UNCATEGORIZED = "Uncategorized"

class Trade(BaseModel):
    trade_id: str
    symbol: str
    asset_category: str  # 'OPT' or 'STK'
    put_call: Optional[str]  # 'P', 'C', or None
    quantity: float
    trade_price: float
    datetime: datetime
    description: Optional[str] = ""

class CategorizedTrade(BaseModel):
    trade: Trade
    category: ActionType
    related_trade_id: Optional[str] = None # ID of the stock trade if assignment

def categorize_trades(trades: List[Trade]) -> List[CategorizedTrade]:
    """
    Categorizes a list of trades into the 6 detected actions.
    Consumes Stock trades into Assignments where applicable, preventing duplicate display.
    """
    # Sort trades by time to ensure correct window matching
    sorted_trades = sorted(trades, key=lambda t: t.datetime)
    
    # Pre-pass: Identify Assignments and mark Stock trades as consumed
    consumed_stock_trades = set()
    pre_calculated_categories = {} # Map trade_id -> (ActionType, related_id)

    for i, trade in enumerate(sorted_trades):
        if trade.asset_category != 'OPT' or trade.quantity <= 0:
            continue
            
        # It's an Option BUY (Closing/Assignment Check)
        # We need to search for a related stock trade
        
        if trade.put_call == 'P':
            window = timedelta(minutes=15)
            target_stock_qty_sign = 1 
        else: # Call
            window = timedelta(minutes=10)
            target_stock_qty_sign = -1 
        
        matching_stock_trade = None
        
        # Check previous trades
        for j in range(i - 1, -1, -1):
            other = sorted_trades[j]
            if (trade.datetime - other.datetime) > window:
                break 
            
            if (other.asset_category == 'STK' and 
                other.symbol == trade.symbol and 
                other.trade_id not in consumed_stock_trades):
                
                if (target_stock_qty_sign > 0 and other.quantity > 0) or \
                   (target_stock_qty_sign < 0 and other.quantity < 0):
                    matching_stock_trade = other
                    break
        
        # Check future trades (if not found yet)
        if not matching_stock_trade:
            for j in range(i + 1, len(sorted_trades)):
                other = sorted_trades[j]
                if (other.datetime - trade.datetime) > window:
                    break 
                
                if (other.asset_category == 'STK' and 
                    other.symbol == trade.symbol and 
                    other.trade_id not in consumed_stock_trades):
                    
                    if (target_stock_qty_sign > 0 and other.quantity > 0) or \
                       (target_stock_qty_sign < 0 and other.quantity < 0):
                        matching_stock_trade = other
                        break
        
        if matching_stock_trade:
            related_id = matching_stock_trade.trade_id
            consumed_stock_trades.add(related_id)
            
            if trade.put_call == 'P':
                cat = ActionType.ASSIGNMENT_PUT
            else: 
                cat = ActionType.ASSIGNMENT_CALL
                
            pre_calculated_categories[trade.trade_id] = (cat, related_id)
        else:
            if trade.put_call == 'P':
                cat = ActionType.CLOSE_WHEEL_PUT
            else:
                cat = ActionType.CLOSE_CALL
            pre_calculated_categories[trade.trade_id] = (cat, None)


    # Final Pass: Generate Results
    categorized_results = []
    
    for trade in sorted_trades:
        # If it's a Stock trade that was consumed, skip it
        if trade.asset_category != 'OPT' and trade.trade_id in consumed_stock_trades:
            continue
            
        if trade.asset_category != 'OPT':
            # Standalone Stock Trade
            if trade.quantity > 0:
                cat = ActionType.STOCK_BUY
            else:
                cat = ActionType.STOCK_SELL
            categorized_results.append(CategorizedTrade(trade=trade, category=cat))
            continue

        # Opt Trade
        if trade.quantity < 0:
            # Opening Trades (Sell)
            if trade.put_call == 'P':
                category = ActionType.OPEN_WHEEL
            elif trade.put_call == 'C':
                category = ActionType.SELL_COVERED_CALL
            else:
                category = ActionType.UNCATEGORIZED
            related_id = None
        else:
            # Closing Trades (Buy) - Use pre-calculated
            if trade.trade_id in pre_calculated_categories:
                category, related_id = pre_calculated_categories[trade.trade_id]
            else:
                category = ActionType.UNCATEGORIZED
                related_id = None

        categorized_results.append(CategorizedTrade(
            trade=trade, 
            category=category, 
            related_trade_id=related_id
        ))
        
    return categorized_results
