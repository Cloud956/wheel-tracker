from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
import requests
import time
import pandas as pd
import io
import os
import sqlite3
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = "/data/wheel_tracker.db"
os.makedirs("/data", exist_ok=True)

TOKEN = os.getenv("IBKR_TOKEN")
QUERY_ID = os.getenv("IBKR_QUERY_ID")
EXCLUDE_SYMBOLS = os.getenv("EXCLUDE_SYMBOLS", "GOOGL,ABN").split(",")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "992920333249-jl7q5rghgbb09g3r2mjdqgorho0bnjkb.apps.googleusercontent.com")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS trades 
        (tradeID TEXT PRIMARY KEY, symbol TEXT, tradeDate TEXT, quantity REAL, 
         price REAL, commission REAL, multiplier REAL, assetCategory TEXT, 
         strike REAL, putCall TEXT)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS positions 
        (symbol TEXT PRIMARY KEY, position REAL, markPrice REAL, multiplier REAL)''')
    conn.commit()
    conn.close()

init_db()

def verify_token(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization Header")
    
    try:
        token = authorization.split(" ")[1] if " " in authorization else authorization
        id_info = id_token.verify_oauth2_token(token, google_requests.Request(), GOOGLE_CLIENT_ID)
        return id_info
    except ValueError as e:
        raise HTTPException(status_code=401, detail=f"Invalid Token: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication Error: {str(e)}")

def format_currency(value):
    return {"value": f"${abs(value):,.2f}", "class": "text-green" if value >= 0 else "text-red", "raw": value}

def format_date_str(date_val):
    s = str(date_val)
    return f"{s[:4]}-{s[4:6]}-{s[6:]}" if len(s) == 8 else s

@app.get("/sync")
def sync_data(user: dict = Depends(verify_token)):
    send_url = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/SendRequest"
    get_url = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/GetStatement"
    
    resp = requests.get(send_url, params={'t': TOKEN, 'q': QUERY_ID, 'v': "3"})
    if "<ReferenceCode>" not in resp.text:
        raise HTTPException(status_code=500, detail="IBKR Flex Request Failed")
    
    ref_code = resp.text.split("<ReferenceCode>")[1].split("</ReferenceCode>")[0]
    time.sleep(6) 
    report_resp = requests.get(get_url, params={'t': TOKEN, 'q': ref_code, 'v': "3"})
    xml_content = report_resp.text
    
    try:
        conn = sqlite3.connect(DB_PATH)
        df_trades = pd.read_xml(io.StringIO(xml_content), xpath=".//Trade")
        df_trades = df_trades[~df_trades['underlyingSymbol'].isin(EXCLUDE_SYMBOLS)]
        
        # --- NO DELETE HERE ---
        # We rely on the PRIMARY KEY (tid) to prevent duplicates
        new_trades_count = 0
        for _, t in df_trades.iterrows():
            # Using tradeID as a unique fingerprint
            tid = f"{t['tradeDate']}_{t['underlyingSymbol']}_{t['quantity']}_{t['tradePrice']}_{t.get('strike', '0')}"
            
            cursor = conn.execute('''INSERT OR IGNORE INTO trades VALUES (?,?,?,?,?,?,?,?,?,?)''', 
                (tid, t['underlyingSymbol'], str(t['tradeDate']), t['quantity'], 
                 t['tradePrice'], t.get('ibCommission', 0), t.get('multiplier', 1), 
                 t['assetCategory'], t.get('strike'), t.get('putCall')))
            if cursor.rowcount > 0:
                new_trades_count += 1
        
        # --- POSITIONS ARE STILL WIPED ---
        # Because positions are a "snapshot" of your current portfolio
        try:
            df_pos = pd.read_xml(io.StringIO(xml_content), xpath=".//OpenPosition")
            conn.execute("DELETE FROM positions")
            for _, p in df_pos.iterrows():
                conn.execute("INSERT OR REPLACE INTO positions VALUES (?,?,?,?)",
                    (p['underlyingSymbol'], p['position'], p['markPrice'], p.get('multiplier', 1)))
        except Exception: pass

        conn.commit()
        conn.close()
        return {"status": "success", "new_trades_added": new_trades_count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/wheel-summary")
def get_wheel_summary(user: dict = Depends(verify_token)):
    conn = sqlite3.connect(DB_PATH)
    # This now queries the cumulative history in the DB
    df = pd.read_sql_query("SELECT * FROM trades ORDER BY tradeDate ASC", conn)
    df_pos = pd.read_sql_query("SELECT * FROM positions", conn)
    pos_map = {row['symbol']: row for _, row in df_pos.iterrows()}
    conn.close()
    
    if df.empty: return []

    wheel_instances = []
    last_instance_by_symbol = {} 
    counter = 1

    for _, t in df.iterrows():
        sym = t['symbol']
        if not sym or t['assetCategory'] == 'CASH': continue
            
        is_new_sold_put = (t['assetCategory'] == 'OPT' and t['putCall'] == 'P' and t['quantity'] < 0)
        
        if is_new_sold_put:
            last_instance_by_symbol[sym] = len(wheel_instances)
            wheel_instances.append({
                "wheelNum": counter,
                "symbol": sym,
                "strike": f"${t['strike']}",
                "startDate": format_date_str(t['tradeDate']),
                "endDate": format_date_str(t['tradeDate']),
                "netCash": 0,
                "commTotal": 0,
                "inventory": 0
            })
            counter += 1

        if sym in last_instance_by_symbol:
            idx = last_instance_by_symbol[sym]
            inst = wheel_instances[idx]
            m = float(t['multiplier']) if pd.notna(t['multiplier']) else 1.0
            inst["netCash"] += (-(t['quantity'] * t['price'] * m) + t['commission'])
            inst["commTotal"] += t['commission']
            inst["endDate"] = format_date_str(t['tradeDate'])
            inst["inventory"] = round(inst["inventory"] + (t['quantity'] * m), 2)

    for w in wheel_instances:
        w["isOpen"] = abs(w["inventory"]) > 0.01
        total_pnl = w["netCash"]
        
        if w["isOpen"] and w["symbol"] in pos_map:
            p_data = pos_map[w["symbol"]]
            total_pnl += (w["inventory"] * p_data['markPrice'])
            
        w["pnl"] = format_currency(total_pnl)
        w["comm"] = format_currency(w.pop("commTotal"))
        w.pop("inventory")

    return wheel_instances[::-1]

@app.get("/history")
def get_history(user: dict = Depends(verify_token)):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM trades ORDER BY tradeDate DESC", conn)
    conn.close()
    
    history = []
    for _, t in df.iterrows():
        history.append({
            "date": format_date_str(t['tradeDate']),
            "symbol": t['symbol'],
            "details": f"{t['strike'] if t['strike'] else ''} {t['putCall'] if t['putCall'] else ''} {t['assetCategory']}",
            "qty": int(t['quantity']),
            "price": f"${t['price']:.2f}",
            "comm": format_currency(t['commission'])
        })
    return history