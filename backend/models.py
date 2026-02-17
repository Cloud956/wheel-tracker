from enum import Enum
from datetime import datetime
from typing import List, Optional
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
    ib_exec_id: Optional[str] = None
    symbol: str
    asset_category: str  # 'OPT' or 'STK'
    put_call: Optional[str]  # 'P', 'C', or None
    strike: Optional[float] = None
    quantity: float
    trade_price: float
    ib_commission: float = 0.0
    datetime: datetime
    description: Optional[str] = ""

class CategorizedTrade(BaseModel):
    trade: Trade
    category: ActionType
    related_trade_id: Optional[str] = None # ID of the stock trade if assignment

class WheelPhase(Enum):
    CSP = "CSP"                    # Cash-Secured Put sold, waiting for expiry/assignment/buyback
    SHARES_HELD = "SHARES_HELD"    # Put was assigned, holding shares, waiting to sell a call
    COVERED_CALL = "COVERED_CALL"  # Covered call sold on held shares

class Holding(BaseModel):
    """Represents a currently held position within a wheel."""
    holding_type: str          # 'SHARES' or 'SHORT_CALL' or 'SHORT_PUT'
    symbol: str
    quantity: float            # e.g. 100 shares or -1 contract
    purchase_price: float      # Price at which it was acquired (cost basis per unit)
    current_price: float       # Current mark price
    unrealized_pnl: float      # Unrealized P&L on this specific holding
    strike: Optional[float] = None  # For options
    multiplier: float = 1.0    # 1 for stock, 100 for options

class Wheel(BaseModel):
    wheel_id: str
    symbol: str
    strike: Optional[float] = None
    start_date: datetime
    end_date: Optional[datetime] = None
    is_open: bool = True
    phase: str = WheelPhase.CSP.value  # Track lifecycle phase
    trades: List[CategorizedTrade] = []
    total_pnl: float = 0.0
    total_commissions: float = 0.0
    currentSoldCall: Optional[Trade] = None
    # Current position / market value fields (populated from OpenPosition data)
    market_price: Optional[float] = None      # Current mark price of the held position
    cost_basis: Optional[float] = None         # Cost basis per share/contract
    current_value: Optional[float] = None      # Total current market value of the position
    unrealized_pnl: Optional[float] = None     # FIFO unrealized P&L from IBKR
    holdings: List[Holding] = []               # Individual held positions (shares, short calls, etc.)
