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
from database import get_user_config, save_wheels, get_wheels, delete_user_wheels, save_highscore, get_highscores
from trade_categorizer import categorize_trades, fetch_flex_report, parse_trades_from_xml, parse_positions_from_xml
from models import Trade, ActionType
from pydantic import BaseModel
from typing import Optional, Dict
from wheel_analyzer import identify_new_wheels, merge_new_wheels, process_wheels, enrich_wheels_with_positions

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

@app.get("/health")
def health_check():
    return {"status": "ok", "message": "Backend is running and accessible"}

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
        # Fetch XML once, parse trades AND positions from it
        xml_content = fetch_flex_report(ibkr_token, ibkr_query_id)
        trades_list = parse_trades_from_xml(xml_content)
        positions_list = parse_positions_from_xml(xml_content)
        
        if not trades_list:
             return {"status": "success", "message": "No trades found in Flex Report", "new_trades": 0, "count": 0, "categorized_trades": []}

        # 3. Categorize Data
        categorized = categorize_trades(trades_list)
        
        # 4. Load existing wheels and identify genuinely new trades
        existing_wheels = get_wheels(email)
        existing_trade_ids = set()
        for w in existing_wheels:
            for t in w.trades:
                existing_trade_ids.add(t.trade.trade_id)
        
        new_trade_ids = {c.trade.trade_id for c in categorized} - existing_trade_ids
        new_trade_count = len(new_trade_ids)
        print(f"Found {len(categorized)} total trades, {new_trade_count} are new")
        
        # 5. Process based on whether there are new trades
        if new_trade_ids:
            # New trades found — full reprocess with merge
            new_wheels = identify_new_wheels(categorized, email)
            wheels = merge_new_wheels(new_wheels, existing_wheels)
            wheels = process_wheels(wheels, categorized)
            wheels = enrich_wheels_with_positions(wheels, positions_list)
            
            wheels_data = [w.dict() for w in wheels]
            save_wheels(email, wheels_data)
            print(f"Saved {len(wheels)} wheels ({new_trade_count} new trades processed)")
        else:
            # No new trades — just refresh position/market data on existing wheels
            wheels = enrich_wheels_with_positions(existing_wheels, positions_list)
            wheels_data = [w.dict() for w in wheels]
            save_wheels(email, wheels_data)
            print("No new trades — refreshed position data only")
        
        # 6. Return Results
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
            "new_trades": new_trade_count,
            "count": len(results),
            "categorized_trades": results
        }
        
    except Exception as e:
        print(f"Processing Error: {e}")
        if "Document is empty" in str(e):
             return {"status": "success", "message": "Parsed empty document (No trades or empty XML)", "new_trades": 0, "count": 0, "categorized_trades": []}
        raise HTTPException(status_code=500, detail=f"Error processing Flex data: {str(e)}")

@app.get("/clear-data")
def clear_data(user: dict = Depends(verify_token)):
    email = user.get('email')
    count = delete_user_wheels(email)
    return {"status": "success", "message": f"Deleted {count} wheels for user {email}"}

@app.get("/wheel-summary")
def get_wheel_summary(user: dict = Depends(verify_token)):
    email = user.get('email')
    
    # Fetch real wheels from DynamoDB (Returns List[Wheel])
    wheels_data = get_wheels(email)
    
    summary = []
    # Sort by start date descending
    wheels_data.sort(key=lambda x: x.start_date, reverse=True)
    
    for idx, w in enumerate(wheels_data):
        total_comm = w.total_commissions
        premium = w.premium_collected
        unrealized = w.unrealized_pnl or 0.0
        # Current PnL = Premium + Unrealized + Commissions (comms are negative from IBKR)
        current_pnl = premium + unrealized + total_comm
        
        # Parse dates for cleaner display
        s_date = w.start_date.isoformat().split('T')[0]
        e_date = w.end_date.isoformat().split('T')[0] if w.end_date else 'Open'
        
            
        summary.append({
            "wheelNum": len(wheels_data) - idx, # Reverse count
            "symbol": w.symbol,
            "strike": w.strike,
            "startDate": s_date,
            "endDate": e_date,
            "isOpen": w.is_open,
            "phase": w.phase,
            "currentSoldCall": w.currentSoldCall.dict() if w.currentSoldCall else None,
            "premiumCollected": format_currency(premium),
            "comm": format_currency(total_comm),
            "marketPrice": w.market_price,
            "costBasis": w.cost_basis,
            "unrealizedPnl": format_currency(unrealized) if w.is_open and w.unrealized_pnl is not None else None,
            "currentPnl": format_currency(current_pnl),
            "holdings": [
                {
                    "type": h.holding_type,
                    "symbol": h.symbol,
                    "quantity": h.quantity,
                    "purchasePrice": h.purchase_price,
                    "currentPrice": h.current_price,
                    "unrealizedPnl": format_currency(h.unrealized_pnl),
                    "strike": h.strike,
                    "multiplier": h.multiplier,
                } for h in w.holdings
            ] if w.holdings else [],
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

# ── Snake Highscores ──────────────────────────────────────────────

class HighscoreSubmission(BaseModel):
    name: str
    score: int
    collected: Optional[Dict[str, int]] = {}

@app.post("/snake/highscore")
def submit_highscore(data: HighscoreSubmission):
    """Save a snake game highscore. No auth required — it's a fun leaderboard."""
    if not data.name or len(data.name.strip()) == 0:
        raise HTTPException(status_code=400, detail="Name is required")
    if data.score < 0:
        raise HTTPException(status_code=400, detail="Invalid score")
    
    success = save_highscore(data.name.strip(), data.score, data.collected or {})
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save highscore")
    return {"status": "success"}

@app.get("/snake/highscores")
def list_highscores():
    """Get top 10 snake highscores. No auth required."""
    return get_highscores(limit=10)
