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
from database import get_user_config
from trade_categorizer import categorize_trades, Trade, ActionType

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

def fetch_flex_data(token, query_id):
    send_url = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/SendRequest"
    get_url = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/GetStatement"
    
    # Send Request
    resp = requests.get(send_url, params={'t': token, 'q': query_id, 'v': "3"})
    if "<ReferenceCode>" not in resp.text:
        error_msg = f"IBKR Flex Request Failed. Response: {resp.text[:200]}"
        print(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)
    
    ref_code = resp.text.split("<ReferenceCode>")[1].split("</ReferenceCode>")[0]
    
    # Wait for report generation
    # IBKR documentation recommends retrying with exponential backoff
    retry_count = 0
    max_retries = 20
    xml_content = None
    
    while retry_count < max_retries:
        sleep_time = 2 + (retry_count * 3) # Increases wait time
        print(f"Waiting {sleep_time}s for Flex Report (Attempt {retry_count+1}/{max_retries})...")
        time.sleep(sleep_time)
        
        report_resp = requests.get(get_url, params={'t': token, 'q': ref_code, 'v': "3"})
        
        # Check for success indicators
        if "<FlexStatement" in report_resp.text: # <FlexStatement> is standard root or child
            xml_content = report_resp.text
            break
            
        if "<ErrorCode>" in report_resp.text:
            # If it's just 'Statement generation in progress', we continue
            if "1019" in report_resp.text: # Code for 'Statement generation in progress'
                print("Report generation in progress...")
                pass
            else:
                # Real error output for debugging
                print(f"Flex Query Fatal Error: {report_resp.text}")
                break
        else:
             # Weird state or just empty
             print(f"Unexpected Response: {report_resp.text[:200]}")
        
        retry_count += 1
        
    if not xml_content:
        raise HTTPException(status_code=500, detail="Failed to retrieve Flex Report after retries")
        
    return xml_content

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
        
    # 2. Run Flex Query
    try:
        xml_content = fetch_flex_data(ibkr_token, ibkr_query_id)
    except Exception as e:
        print(f"Flex Fetch Error: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching data from IBKR: {str(e)}")

    # 3. Parse Data and Convert to Trade objects
    try:
        # Use pandas to parse XML
        df_trades = pd.read_xml(io.StringIO(xml_content), xpath=".//Trade")
        
        if df_trades.empty:
             return {"status": "success", "message": "No trades found in Flex Report", "categorized_trades": []}

        # Filter out ignored symbols
        IGNORED_SYMBOLS = ["GOOGL", "ABN"] # Add any others here
        if 'underlyingSymbol' in df_trades.columns:
            df_trades = df_trades[~df_trades['underlyingSymbol'].isin(IGNORED_SYMBOLS)]
        
        # Convert DataFrame to List[Trade]
        trades_list = []
        for _, row in df_trades.iterrows():
            try:
                d_str = str(row.get('tradeDate', ''))
                t_str = str(row.get('tradeTime', '000000')) # Default if missing
                
                date_part = datetime.strptime(d_str, "%Y%m%d")
                
                if ':' in t_str and len(t_str) >= 5:
                    time_part = datetime.strptime(t_str, "%H:%M:%S").time()
                    dt = datetime.combine(date_part.date(), time_part)
                else:
                    dt = date_part 
            except Exception:
                dt = datetime.now() 
            
            # Create Unique ID
            # Append asset type to ensure uniqueness if IBKR reuses IDs for assignment legs
            raw_id = str(row.get('transactionID', f"{row.get('tradeDate')}-{row.get('tradeTime')}-{row.get('symbol')}"))
            asset_cat = str(row.get('assetCategory', 'UNKNOWN'))
            unique_id = f"{raw_id}_{asset_cat}"

            trade = Trade(
                trade_id=unique_id, 
                symbol=str(row.get('underlyingSymbol', row.get('symbol', 'UNKNOWN'))),
                asset_category=asset_cat,
                put_call=str(row.get('putCall')) if pd.notna(row.get('putCall')) else None,
                quantity=float(row.get('quantity', 0)),
                trade_price=float(row.get('tradePrice', 0)),
                datetime=dt,
                description=str(row.get('description', ''))
            )
            trades_list.append(trade)
            
        # 4. Categorize Data
        categorized = categorize_trades(trades_list)
        
        # 5. Return Results
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
    # Fake wheel summary data
    return [
        {
            "wheelNum": 3,
            "symbol": "FAKE",
            "strike": "$150.0",
            "startDate": "2023-11-01",
            "endDate": "2023-12-01",
            "netCash": 120.50,
            "isOpen": False,
            "pnl": format_currency(120.50),
            "comm": format_currency(2.50)
        },
        {
            "wheelNum": 2,
            "symbol": "TEST",
            "strike": "$100.0",
            "startDate": "2023-10-15",
            "endDate": "2023-11-15",
            "netCash": -50.00,
            "isOpen": True,
            "pnl": format_currency(-50.00),
            "comm": format_currency(1.25)
        },
        {
            "wheelNum": 1,
            "symbol": "DEMO",
            "strike": "$25.0",
            "startDate": "2023-09-01",
            "endDate": "2023-10-01",
            "netCash": 450.00,
            "isOpen": False,
            "pnl": format_currency(450.00),
            "comm": format_currency(5.00)
        }
    ]

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
