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
from database import get_user_config, save_wheels, get_wheels, delete_user_wheels, save_highscore, get_highscores, get_daily_pnl
from trade_categorizer import categorize_trades, fetch_flex_report, parse_trades_from_xml, parse_positions_from_xml
from models import Trade, ActionType, WheelPhase
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


@app.get("/pnl")
def get_pnl(user: dict = Depends(verify_token)):
    """Return all daily PnL records for the user, sorted by date ascending."""
    email = user.get('email')
    records = get_daily_pnl(email)
    return records


@app.post("/activate-daily-mode")
def activate_daily_mode(user: dict = Depends(verify_token)):
    """
    Activates daily mode:
    - Purges all stored wheel data for the user.
    - Sets the daily_mode flag in the user config.
    The actual 3 AM CET sync schedule is handled separately at the infrastructure level.
    """
    email = user.get('email')

    # 1. Purge all wheel data
    deleted = delete_user_wheels(email)

    # 2. Mark daily_mode active in user config
    from database import update_user_config
    update_user_config(email, {'daily_mode': True})

    return {
        "status": "success",
        "message": f"Daily mode activated. {deleted} wheels purged.",
    }


@app.get("/analytics")
def get_analytics(user: dict = Depends(verify_token)):
    """
    Compute comprehensive wheel strategy analytics from stored wheel data.
    No additional DynamoDB table required — derived entirely from the Wheels table.
    """
    email = user.get('email')
    wheels = get_wheels(email)

    if not wheels:
        return {"overview": None, "by_symbol": [], "monthly": [], "close_reasons": {}}

    closed_wheels = [w for w in wheels if not w.is_open]
    open_wheels   = [w for w in wheels if w.is_open]

    def realized_pnl(w):
        return w.premium_collected + w.total_commissions

    # ── Overview stats ─────────────────────────────────────────────
    closed_pnl_list   = [realized_pnl(w) for w in closed_wheels]
    total_realized    = sum(realized_pnl(w) for w in wheels)
    winning_closed    = [p for p in closed_pnl_list if p > 0]
    win_rate          = (len(winning_closed) / len(closed_wheels) * 100) if closed_wheels else 0
    avg_pnl           = (sum(closed_pnl_list) / len(closed_pnl_list)) if closed_pnl_list else 0
    total_premiums    = sum(w.premium_collected for w in wheels)
    total_commissions = sum(w.total_commissions for w in wheels)
    avg_premium       = total_premiums / len(wheels) if wheels else 0
    total_trades      = sum(len(w.trades) for w in wheels)
    unique_symbols    = len(set(w.symbol for w in wheels))

    # Average hold duration (closed wheels only)
    hold_days = [
        (w.end_date - w.start_date).days
        for w in closed_wheels
        if w.end_date and w.start_date and (w.end_date - w.start_date).days >= 0
    ]
    avg_hold_days = sum(hold_days) / len(hold_days) if hold_days else 0

    # Return per calendar day since first trade
    all_starts = [w.start_date for w in wheels]
    if all_starts:
        first_date  = min(all_starts)
        total_days  = max((datetime.now() - first_date).days, 1)
        return_per_day = total_realized / total_days
    else:
        return_per_day = 0

    best_pnl  = max(closed_pnl_list) if closed_pnl_list else 0
    worst_pnl = min(closed_pnl_list) if closed_pnl_list else 0

    # Largest premium collected in a single wheel
    max_premium = max((w.premium_collected for w in wheels), default=0)

    # Average number of trades per wheel
    avg_trades_per_wheel = total_trades / len(wheels) if wheels else 0

    overview = {
        "total_wheels":        len(wheels),
        "open_wheels":         len(open_wheels),
        "closed_wheels":       len(closed_wheels),
        "win_rate":            round(win_rate, 1),
        "total_realized_pnl":  round(total_realized, 2),
        "best_wheel_pnl":      round(best_pnl, 2),
        "worst_wheel_pnl":     round(worst_pnl, 2),
        "avg_pnl_per_wheel":   round(avg_pnl, 2),
        "total_premiums":      round(total_premiums, 2),
        "total_commissions":   round(total_commissions, 2),
        "avg_premium_per_wheel": round(avg_premium, 2),
        "max_single_premium":  round(max_premium, 2),
        "avg_hold_days":       round(avg_hold_days, 1),
        "return_per_day":      round(return_per_day, 2),
        "total_trades":        total_trades,
        "avg_trades_per_wheel": round(avg_trades_per_wheel, 1),
        "unique_symbols":      unique_symbols,
    }

    # ── By symbol ──────────────────────────────────────────────────
    sym_map = {}
    for w in wheels:
        s = w.symbol
        if s not in sym_map:
            sym_map[s] = {"symbol": s, "count": 0, "closed": 0,
                          "total_pnl": 0.0, "wins": 0, "premiums": 0.0,
                          "hold_days_sum": 0, "hold_days_count": 0}
        sym_map[s]["count"]    += 1
        sym_map[s]["premiums"] += w.premium_collected
        if not w.is_open:
            pnl = realized_pnl(w)
            sym_map[s]["closed"]    += 1
            sym_map[s]["total_pnl"] += pnl
            if pnl > 0:
                sym_map[s]["wins"] += 1
            if w.end_date and w.start_date:
                d = (w.end_date - w.start_date).days
                if d >= 0:
                    sym_map[s]["hold_days_sum"]   += d
                    sym_map[s]["hold_days_count"] += 1

    by_symbol = sorted([
        {
            "symbol":    d["symbol"],
            "count":     d["count"],
            "closed":    d["closed"],
            "total_pnl": round(d["total_pnl"], 2),
            "avg_pnl":   round(d["total_pnl"] / d["closed"], 2) if d["closed"] else 0,
            "win_rate":  round(d["wins"] / d["closed"] * 100, 1) if d["closed"] else 0,
            "premiums":  round(d["premiums"], 2),
            "avg_hold_days": round(d["hold_days_sum"] / d["hold_days_count"], 1)
                             if d["hold_days_count"] else 0,
        }
        for d in sym_map.values()
    ], key=lambda x: x["total_pnl"], reverse=True)

    # ── Monthly breakdown (by wheel start date) ────────────────────
    monthly_map = {}
    for w in wheels:
        mk = w.start_date.strftime('%Y-%m')
        if mk not in monthly_map:
            monthly_map[mk] = {"month": mk, "new_wheels": 0, "closed_wheels": 0,
                               "pnl": 0.0, "premiums": 0.0}
        monthly_map[mk]["new_wheels"] += 1
        monthly_map[mk]["premiums"]   += w.premium_collected
        if not w.is_open:
            monthly_map[mk]["closed_wheels"] += 1
            monthly_map[mk]["pnl"]           += realized_pnl(w)

    monthly = sorted([
        {**{"month": mk},
         **{k: round(v, 2) if isinstance(v, float) else v
            for k, v in mv.items() if k != "month"}}
        for mk, mv in monthly_map.items()
    ], key=lambda x: x["month"])

    # ── Close reasons ──────────────────────────────────────────────
    # CSP phase + closed  → put bought back (no assignment)
    # Any other phase + closed → full cycle via call assignment
    close_reasons = {"full_cycle": 0, "put_closed": 0, "open": len(open_wheels)}
    for w in closed_wheels:
        if w.phase == WheelPhase.CSP.value:
            close_reasons["put_closed"] += 1
        else:
            close_reasons["full_cycle"] += 1

    return {
        "overview":      overview,
        "by_symbol":     by_symbol,
        "monthly":       monthly,
        "close_reasons": close_reasons,
    }


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
        # Only include unrealized PnL for open wheels — closed wheels have no live position
        unrealized = (w.unrealized_pnl or 0.0) if w.is_open else 0.0
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
    email = user.get('email')
    wheels = get_wheels(email)
    
    # Flatten all trades from all wheels into a single list, deduped by trade_id
    seen_ids = set()
    history = []
    
    for w in wheels:
        for t in w.trades:
            if t.trade.trade_id in seen_ids:
                continue
            seen_ids.add(t.trade.trade_id)
            
            # Build a readable details string: "STRIKE PUT/CALL OPT" or "STK"
            if t.trade.asset_category == 'OPT':
                pc = 'Put' if t.trade.put_call == 'P' else 'Call' if t.trade.put_call == 'C' else ''
                strike_str = f"{t.trade.strike} " if t.trade.strike else ''
                details = f"{strike_str}{pc} OPT"
            else:
                details = t.trade.description or 'STK'
            
            history.append({
                "date": t.trade.datetime.isoformat().split('T')[0],
                "symbol": t.trade.symbol,
                "action": t.category.value,
                "details": details,
                "qty": t.trade.quantity,
                "price": format_currency(t.trade.trade_price),
                "comm": format_currency(t.trade.ib_commission),
            })
    
    # Sort by date descending
    history.sort(key=lambda x: x['date'], reverse=True)
    return history

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
