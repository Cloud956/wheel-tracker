from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv
from auth import verify_token, format_currency
from routers import account
import requests
import time
import pandas as pd
import io
from datetime import datetime
from database import get_user_config, save_wheels, get_wheels
from trade_categorizer import categorize_trades, fetch_and_parse_trades
from models import Trade, ActionType
from wheel_analyzer import analyze_wheels, identify_new_wheels, merge_new_wheels, update_wheels

load_dotenv()
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(account.router)

@app.get("/sync")
def sync_data(user: dict = Depends(verify_token)):
    email = user.get('email')
    print(f"Syncing data for: {email}")
    
    # 1. Get User Config from DynamoDB
    user_config = get_user_config(email)
    if not user_config:
        raise HTTPException(status_code=404, detail="User configuration not found")
        
    ibkr_token = user_config.get('ibkr_token')
    ibkr_query_id = user_config.get('ibkr_query_id')
    
    if not ibkr_token or not ibkr_query_id:
        raise HTTPException(status_code=400, detail="IBKR credentials (token/query_id) not configured")
        
    # 2. Run Flex Query & Parse Data
    try:
        trades_list = fetch_and_parse_trades(ibkr_token, ibkr_query_id)
        
        if not trades_list:
             return {"status": "success", "message": "No trades found in Flex Report", "categorized_trades": []}

        # 3. Categorize Data
        categorized = categorize_trades(trades_list)
        
        # 4. Identify New Wheels
        new_wheels = identify_new_wheels(categorized, email)
        
        # 5. Merge New Wheels with Existing
        wheels = merge_new_wheels(new_wheels, get_wheels(email))
        
        # 6. Update Wheels with other trades (Close/Update actions)
        wheels = update_wheels(wheels, categorized)
        
        # 7. Save Wheels to DynamoDB
        # We convert the Pydantic models to dicts for saving
        # The database module handles type conversion (datetime->str, float->Decimal)
        wheels_data = [w.dict() for w in wheels]
        save_wheels(email, wheels_data)
        
        # 4. Return Results
        results = []
        
        # Helper to find trade by ID
        trade_lookup = {t.trade_id: t for t in trades_list}
        
        # Mapping for Action Suggestions
        action_map = {
            ActionType.OPEN_WHEEL: "Start New Wheel",
            ActionType.ASSIGNMENT_PUT: "Update Open Wheel",
            ActionType.SELL_COVERED_CALL: "Update Open Wheel",
            ActionType.CLOSE_CALL: "Update Open Wheel",
            ActionType.CLOSE_WHEEL_PUT: "Close Open Wheel",
            ActionType.ASSIGNMENT_CALL: "Close Open Wheel",
            ActionType.STOCK_BUY: "Update Open Wheel",
            ActionType.STOCK_SELL: "Close Open Wheel"
        }

        for c in categorized:
            details_str = f"{c.trade.quantity} @ {c.trade.trade_price}"
            
            # If there is a related stock assignment trade, append its details
            if c.related_trade_id and c.related_trade_id in trade_lookup:
                related = trade_lookup[c.related_trade_id]
                details_str += f" | Stock: {related.quantity} @ {related.trade_price}"
            
            results.append({
                "trade_id": c.trade.trade_id,
                "symbol": c.trade.symbol,
                "action": c.category.value,
                "suggested_action": action_map.get(c.category, "Review"),
                "date": c.trade.datetime.isoformat(),
                "details": details_str
            })
            
        return {
            "status": "success", 
            "count": len(results),
            "categorized_trades": results
        }
        
    except Exception as e:
        print(f"Processing Error: {e}")
        if "Document is empty" in str(e):
             return {"status": "success", "message": "Parsed empty document (No trades or empty XML)", "categorized_trades": []}
        raise HTTPException(status_code=500, detail=f"Error processing Flex data: {str(e)}")

@app.get("/wheel-summary")
def get_wheel_summary(user: dict = Depends(verify_token)):
    email = user.get('email')
    
    # Fetch real wheels from DynamoDB (Returns List[Wheel])
    wheels_data = get_wheels(email)
    
    summary = []
    # Sort by start date descending
    wheels_data.sort(key=lambda x: x.start_date, reverse=True)
    
    for idx, w in enumerate(wheels_data):
        total_pnl = w.total_pnl
        total_comm = w.total_commissions
        
        # Parse dates for cleaner display
        s_date = w.start_date.isoformat().split('T')[0]
        e_date = w.end_date.isoformat().split('T')[0] if w.end_date else 'Open'
        
            
        summary.append({
            "wheelNum": len(wheels_data) - idx, # Reverse count
            "symbol": w.symbol,
            "strike": w.strike,
            "startDate": s_date,
            "endDate": e_date,
            "netCash": total_pnl, # PnL is essentially net cash flow in this model
            "isOpen": w.is_open,
            "pnl": format_currency(total_pnl),
            "comm": format_currency(total_comm),
            "trades": [
                {
                    "date": t.trade.datetime.isoformat().split('T')[0],
                    "details": t.trade.description or f"{t.trade.quantity} @ {t.trade.trade_price}",
                    "action": t.category.value,
                    "price": format_currency(t.trade.trade_price),
                    "quantity": t.trade.quantity,
                    "type": t.trade.asset_category
                } for t in w.trades
            ]
        })
        
    return summary

@app.get("/history")
def get_history(user: dict = Depends(verify_token)):
    # Fake history data
    return [
        {
            "date": "2023-12-01",
            "symbol": "FAKE",
            "details": "150.0 P OPT",
            "qty": -1,
            "price": "$1.20",
            "comm": format_currency(1.25)
        },
        {
            "date": "2023-11-15",
            "symbol": "TEST",
            "details": "100.0 C OPT",
            "qty": 1,
            "price": "$0.50",
            "comm": format_currency(1.25)
        },
        {
            "date": "2023-10-01",
            "symbol": "DEMO",
            "details": "25.0 P OPT",
            "qty": -10,
            "price": "$0.45",
            "comm": format_currency(5.00)
        }
    ]
