from typing import List, Optional
from models import Trade, CategorizedTrade, ActionType
import requests
import time
import pandas as pd
import io
from datetime import datetime, timedelta

def fetch_and_parse_trades(token: str, query_id: str) -> List[Trade]:
    """
    Calls IBKR Flex API, gets the report, parses XML, and returns a list of Trade objects.
    """
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

    # Use pandas to parse XML
    try:
        df_trades = pd.read_xml(io.StringIO(xml_content), xpath=".//Trade")
    except ValueError:
         # Handle case where XML is valid but has no Trade elements
         return []
    
    if df_trades.empty:
            return []

    # Filter out ignored symbols
    IGNORED_SYMBOLS = [ "ABN"] # Add any others here
    if 'underlyingSymbol' in df_trades.columns:
        df_trades = df_trades[~df_trades['underlyingSymbol'].isin(IGNORED_SYMBOLS)]

    
    # Convert DataFrame to List[Trade]
    trades_list = []
    for _, row in df_trades.iterrows():
        try:
            # Handle standard IBKR attributes
            # Sometimes they provide 'dateTime' attribute directly: "20260205;094326"
            raw_dt = str(row.get('dateTime', ''))
            
            if ';' in raw_dt:
                # Format: "20260205;094326"
                dt = datetime.strptime(raw_dt, "%Y%m%d;%H%M%S")
            else:
                # Fallback to separate tradeDate and tradeTime fields
                d_str = str(row.get('tradeDate', ''))
                t_str = str(row.get('tradeTime', '000000')) # Default if missing
                
                date_part = datetime.strptime(d_str, "%Y%m%d")
                
                # Handle time with or without colons
                if ':' in t_str:
                    time_part = datetime.strptime(t_str, "%H:%M:%S").time()
                else:
                    # Assume HHMMSS format
                    # Pad with zeros if necessary (e.g. 93000 -> 093000)
                    t_str = t_str.zfill(6)
                    time_part = datetime.strptime(t_str, "%H%M%S").time()
                    
                dt = datetime.combine(date_part.date(), time_part)
        except Exception as e:
            dt = datetime.now() 
        

        ib_exec_id = str(row.get('ibExecID'))
        
        # New robust ID generation strategy:
        # Use IB Exec ID if available + Asset Category (to distinguish stock vs option leg if they share ID)
        # Fallback to composite key of attributes.
        asset_cat = str(row.get('assetCategory', 'UNKNOWN'))
        if ib_exec_id != "nan":
             unique_id = f"{ib_exec_id}_{asset_cat}"
        else:
             # Composite key: Symbol + Date + Time + Quantity + Asset
             # Format date nicely
             date_str = dt.strftime("%Y%m%d%H%M%S")
             qty_str = str(row.get('quantity', 0))
             sym_str = str(row.get('symbol', 'UNKNOWN'))
             unique_id = f"{sym_str}_{date_str}_{qty_str}_{asset_cat}"

        strike_str = row.get('strike')
        strike_val = None
        if pd.notna(strike_str) and str(strike_str).strip() != "":
            try:
                strike_val = float(strike_str)
            except (ValueError, TypeError):
                pass # Keep None if parse fails

        trade = Trade(
            trade_id=unique_id, 
            ib_exec_id=ib_exec_id,
            symbol=str(row.get('underlyingSymbol', row.get('symbol', 'UNKNOWN'))),
            asset_category=asset_cat,
            put_call=str(row.get('putCall')) if pd.notna(row.get('putCall')) else None,
            strike=strike_val,
            quantity=float(row.get('quantity', 0)),
            trade_price=float(row.get('tradePrice', 0)),
            ib_commission=float(row.get('ibCommission', 0)),
            datetime=dt,
            description=str(row.get('description', ''))
        )
        trades_list.append(trade)

    return trades_list

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
    
    window = timedelta(minutes=30)

    for i, cat_trade in enumerate(initial_results):
        if cat_trade.trade.trade_id in consumed_trade_ids:
            continue
            
        match = None
        
        # Logic for Put Assignment: Bought Put + Bought Shares
        if cat_trade.category == ActionType.CLOSE_WHEEL_PUT:
            # Search for a matching Stock Buy
            
            # Use shares_trades bucket directly for searching, as it contains the raw Trade objects for stocks
            # Filter for buys (positive quantity)
            for stock_trade in [t for t in shares_trades if t.quantity > 0]:

                # Basic self-check (unlikely to match ID but safe to keep)
                if stock_trade.trade_id == cat_trade.trade.trade_id:
                    continue
                if stock_trade.trade_id in consumed_trade_ids:
                    continue
                if stock_trade.symbol != cat_trade.trade.symbol:
                    continue
                if stock_trade.trade_price != cat_trade.trade.strike:
                    continue
                    
                time_diff = abs(stock_trade.datetime - cat_trade.trade.datetime)
                    
                # Time window check
                if time_diff <= window:
                    # Create a dummy 'other' wrapper just for the logic below or use direct object
                    # We need to add the Stock Trade ID to consumed
                    cat_trade.category = ActionType.ASSIGNMENT_PUT
                    cat_trade.related_trade_id = stock_trade.trade_id
                    consumed_trade_ids.add(stock_trade.trade_id)
                    match = stock_trade # Found it
                    break
            
            if not match:
                pass  # No matching stock trade found for this put close

        # Logic for Call Assignment: Bought Call + Sold Shares
        elif cat_trade.category == ActionType.CLOSE_CALL:
            # Search for a matching Stock Sell
            for stock_trade in [t for t in shares_trades if t.quantity < 0]:
                
                if stock_trade.trade_id == cat_trade.trade.trade_id:
                    continue
                if stock_trade.trade_id in consumed_trade_ids:
                    continue
                
                if stock_trade.symbol != cat_trade.trade.symbol:
                    continue
                if stock_trade.trade_price != cat_trade.trade.strike:
                    continue

                if abs(stock_trade.datetime - cat_trade.trade.datetime) <= window:
                    match = stock_trade
                    break
            
            if match:
                cat_trade.category = ActionType.ASSIGNMENT_CALL
                cat_trade.related_trade_id = match.trade_id
                consumed_trade_ids.add(match.trade_id)
        
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
    
    # Track trades that were "consumed" as related trades (e.g., Stock Buy used in Assignment)
    # consumed_trade_ids set already tracks this.
    
    for t in final_results:
        # If this trade was consumed as a "related trade" (the stock leg), SKIP it.
        # But we MUST include the primary trade (the Option trade) which now has the ASSIGNMENT category.
        if t.trade.trade_id in consumed_trade_ids:
             continue
             
        if t.category in allowed_categories:
            filtered_results.append(t)
            
    return filtered_results
