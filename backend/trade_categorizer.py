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
    Logic:
    1. Collect trades into buckets.
    2. Create initial categorizations (Basic types).
    3. Run logic pass to detect assignments and link trades.
    """
    # Sort trades by time to ensure correct processing order if needed later
    sorted_trades = sorted(trades, key=lambda t: t.datetime)
    
    puts_sold: List[Trade] = []
    puts_bought: List[Trade] = []
    calls_sold: List[Trade] = []
    calls_bought: List[Trade] = []
    shares_trades: List[Trade] = [] # Only multiples of 100
    others: List[Trade] = []
    
    # 1. Bucket Trades
    for trade in sorted_trades:
        if trade.asset_category == 'OPT':
            if trade.put_call == 'P':
                if trade.quantity < 0:
                    puts_sold.append(trade)
                else:
                    puts_bought.append(trade)
            elif trade.put_call == 'C':
                if trade.quantity < 0:
                    calls_sold.append(trade)
                else:
                    calls_bought.append(trade)
            else:
                others.append(trade)
        elif trade.asset_category == 'STK':
            if abs(trade.quantity) >= 100 and abs(trade.quantity) % 100 == 0:
                shares_trades.append(trade)
            else:
                others.append(trade)
        else:
            others.append(trade)

    initial_results: List[CategorizedTrade] = []
    
    # 2. Initial Basic Categorization
    for t in puts_sold:
        initial_results.append(CategorizedTrade(trade=t, category=ActionType.OPEN_WHEEL))
    for t in puts_bought:
        initial_results.append(CategorizedTrade(trade=t, category=ActionType.CLOSE_WHEEL_PUT))
    for t in calls_sold:
        initial_results.append(CategorizedTrade(trade=t, category=ActionType.SELL_COVERED_CALL))
    for t in calls_bought:
        initial_results.append(CategorizedTrade(trade=t, category=ActionType.CLOSE_CALL))
    for t in shares_trades:
        cat = ActionType.STOCK_BUY if t.quantity > 0 else ActionType.STOCK_SELL
        initial_results.append(CategorizedTrade(trade=t, category=cat))
    for t in others:
        initial_results.append(CategorizedTrade(trade=t, category=ActionType.UNCATEGORIZED))

    # 3. Logic Pass: Detect Assignments
    final_results: List[CategorizedTrade] = []
    consumed_trade_ids = set()
    
    # Sort initial results by time to help window matching
    initial_results.sort(key=lambda x: x.trade.datetime)
    
    window = timedelta(minutes=10)

    for i, cat_trade in enumerate(initial_results):
        if cat_trade.trade.trade_id in consumed_trade_ids:
            continue
            
        match = None
        
        # Logic for Put Assignment: Bought Put + Bought Shares
        if cat_trade.category == ActionType.CLOSE_WHEEL_PUT:
            # Search for a matching Stock Buy
            for other in initial_results:
                if other.trade.trade_id == cat_trade.trade.trade_id:
                    continue
                if other.trade.trade_id in consumed_trade_ids:
                    continue
                
                if other.category == ActionType.STOCK_BUY:
                    if other.trade.symbol == cat_trade.trade.symbol:
                        if abs(other.trade.datetime - cat_trade.trade.datetime) <= window:
                            match = other
                            break
            
            if match:
                cat_trade.category = ActionType.ASSIGNMENT_PUT
                cat_trade.related_trade_id = match.trade.trade_id
                consumed_trade_ids.add(match.trade.trade_id)

        # Logic for Call Assignment: Bought Call + Sold Shares
        elif cat_trade.category == ActionType.CLOSE_CALL:
            # Search for a matching Stock Sell
            for other in initial_results:
                if other.trade.trade_id == cat_trade.trade.trade_id:
                    continue
                if other.trade.trade_id in consumed_trade_ids:
                    continue
                
                if other.category == ActionType.STOCK_SELL:
                    if other.trade.symbol == cat_trade.trade.symbol:
                        if abs(other.trade.datetime - cat_trade.trade.datetime) <= window:
                            match = other
                            break
            
            if match:
                cat_trade.category = ActionType.ASSIGNMENT_CALL
                cat_trade.related_trade_id = match.trade.trade_id
                consumed_trade_ids.add(match.trade.trade_id)
        
        final_results.append(cat_trade)
    
    # Filter out consumed trades AND unwanted categories from final results
    # Exclude UNCATEGORIZED and standalone STOCK_BUY/STOCK_SELL
    allowed_categories = {
        ActionType.OPEN_WHEEL,
        ActionType.CLOSE_WHEEL_PUT,
        ActionType.ASSIGNMENT_PUT,
        ActionType.SELL_COVERED_CALL,
        ActionType.CLOSE_CALL,
        ActionType.ASSIGNMENT_CALL
    }
    
    filtered_results = []
    for t in final_results:
        if t.trade.trade_id in consumed_trade_ids:
            continue
        if t.category in allowed_categories:
            filtered_results.append(t)
            
    return filtered_results
