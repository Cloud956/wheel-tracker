from fastapi import FastAPI, HTTPException
import requests
import time
import pandas as pd
import io
import os
from dotenv import load_dotenv

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # This happens inside Docker because we pass vars directly
    pass

TOKEN = os.getenv("IBKR_TOKEN")
QUERY_ID = os.getenv("IBKR_QUERY_ID")
app = FastAPI()
VERSION = "3"
SEND_URL = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/SendRequest"
GET_URL = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/GetStatement"

def fetch_ibkr_xml():
    """Helper to handle the IBKR handshake"""
    # Step 1: Request
    resp = requests.get(SEND_URL, params={'t': TOKEN, 'q': QUERY_ID, 'v': VERSION})
    if "<ReferenceCode>" not in resp.text:
        return None
    
    ref_code = resp.text.split("<ReferenceCode>")[1].split("</ReferenceCode>")[0]
    
    # Step 2: Download (Wait for IBKR to generate)
    time.sleep(5)
    report_resp = requests.get(GET_URL, params={'t': TOKEN, 'q': ref_code, 'v': VERSION})
    return report_resp.text if report_resp.status_code == 200 else None

@app.get("/wheel")
def get_wheel():
    xml_data = fetch_ibkr_xml()
    if not xml_data:
        raise HTTPException(status_code=500, detail="Failed to fetch data from IBKR")

    exclude_symbols = ['GOOGL', 'ABN'] #I am filtering these two, but for you this will not be perfect, so other methods of filtering non-wheel related are needed
    result = {}

    # Helper function to clean dataframes for JSON
    def clean_df(df, exclude_list):
        if df is None or df.empty:
            return []
        # 1. Filter out symbols
        if 'underlyingSymbol' in df.columns:
            df = df[~df['underlyingSymbol'].isin(exclude_list)]
        
        # 2. CRITICAL: Replace NaN/Inf with None (null in JSON)
        # This handles 'strike', 'underlyingSymbol', 'price', etc. all at once
        df = df.replace({pd.NA: None, float('nan'): None, float('inf'): None, float('-inf'): None})
        
        return df.to_dict(orient="records")

    # --- Process Trades ---
    try:
        df_trades = pd.read_xml(io.StringIO(xml_data), xpath=".//Trade")
        result["trades"] = clean_df(df_trades, exclude_symbols)
    except Exception as e:
        print(f"Trades Error: {e}")
        result["trades"] = []

    # --- Process Positions ---
    try:
        df_pos = pd.read_xml(io.StringIO(xml_data), xpath=".//OpenPosition")
        result["positions"] = clean_df(df_pos, exclude_symbols)
    except Exception as e:
        print(f"Positions Error: {e}")
        result["positions"] = []

    return result