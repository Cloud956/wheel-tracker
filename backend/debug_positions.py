"""
Debug script: Fetch Flex Query XML and inspect OpenPosition elements.
Run inside the backend container: docker exec wheel-tracker-backend python debug_positions.py
"""
import os
import sys
from dotenv import load_dotenv
load_dotenv()

from database import get_user_config
from trade_categorizer import fetch_flex_report, parse_trades_from_xml, parse_positions_from_xml
import pandas as pd
import io

def main():
    # Get the user's IBKR credentials from DynamoDB
    # Try to find the user config
    import boto3
    from botocore.exceptions import ClientError
    
    aws_region = os.getenv("AWS_REGION", "eu-central-1")
    aws_access_key = os.getenv("AWS_ACCESS_KEY_ID") or os.getenv("AWS_ACCESS_KEY")
    aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY") or os.getenv("AWS_ACCESS_TOKEN")
    
    boto3_kwargs = {'service_name': 'dynamodb', 'region_name': aws_region}
    if aws_access_key and aws_secret_key:
        boto3_kwargs['aws_access_key_id'] = aws_access_key
        boto3_kwargs['aws_secret_access_key'] = aws_secret_key
    
    dynamodb = boto3.resource(**boto3_kwargs)
    table = dynamodb.Table(os.getenv("DYNAMODB_USER_TABLE_NAME", "UserConfigs"))
    
    # Scan for any user config
    response = table.scan(Limit=5)
    items = response.get('Items', [])
    
    if not items:
        print("ERROR: No user configs found in DynamoDB")
        return
    
    for item in items:
        username = item.get('username', 'UNKNOWN')
        print(f"Found user: {username}")
    
    # Use first user's credentials
    user_config = items[0]
    ibkr_token = user_config.get('ibkr_token')
    ibkr_query_id = user_config.get('ibkr_query_id')
    
    if not ibkr_token or not ibkr_query_id:
        print("ERROR: No IBKR credentials found")
        return
    
    print(f"\nFetching Flex Report...")
    print(f"Token: {ibkr_token[:5]}...{ibkr_token[-5:]}")
    print(f"Query ID: {ibkr_query_id}")
    
    try:
        xml_content = fetch_flex_report(ibkr_token, ibkr_query_id)
    except Exception as e:
        print(f"ERROR fetching report: {e}")
        return
    
    print(f"\nXML length: {len(xml_content)} chars")
    
    # Check what elements are present
    print(f"\n=== XML STRUCTURE CHECK ===")
    print(f"Contains <Trade>: {'<Trade ' in xml_content or '<Trade>' in xml_content}")
    print(f"Contains <OpenPosition>: {'<OpenPosition ' in xml_content or '<OpenPosition>' in xml_content}")
    print(f"Contains <OpenPositions>: {'<OpenPositions>' in xml_content or '<OpenPositions ' in xml_content}")
    print(f"Contains 'position': {'position' in xml_content.lower()}")
    print(f"Contains 'markPrice': {'markPrice' in xml_content}")
    print(f"Contains 'costBasisPrice': {'costBasisPrice' in xml_content}")
    print(f"Contains 'fifoPnlUnrealized': {'fifoPnlUnrealized' in xml_content}")
    
    # Try to find the relevant XML sections  
    # Print a snippet around any "OpenPosition" occurrence
    idx = xml_content.find('OpenPosition')
    if idx >= 0:
        start = max(0, idx - 50)
        end = min(len(xml_content), idx + 500)
        print(f"\n=== XML SNIPPET (around OpenPosition) ===")
        print(xml_content[start:end])
    else:
        print("\n!!! No 'OpenPosition' found anywhere in the XML !!!")
        # Let's check what other sections exist
        import re
        tags = re.findall(r'<([A-Z][A-Za-z]+)[\s>]', xml_content)
        unique_tags = sorted(set(tags))
        print(f"\nAll unique XML tags found: {unique_tags}")
    
    # Parse positions
    print(f"\n=== PARSING POSITIONS ===")
    positions = parse_positions_from_xml(xml_content)
    print(f"Parsed {len(positions)} positions")
    
    for p in positions:
        print(f"  {p['symbol']} | {p['asset_category']} | "
              f"put_call={p['put_call']} | strike={p['strike']} | "
              f"qty={p['position']} | mark={p['mark_price']} | "
              f"cost_basis={p['cost_basis_price']} | "
              f"unrealized={p['fifo_pnl_unrealized']}")
    
    # Parse trades for reference
    print(f"\n=== PARSING TRADES ===")
    trades = parse_trades_from_xml(xml_content)
    print(f"Parsed {len(trades)} trades")
    
    for t in trades[:10]:
        print(f"  {t.symbol} | {t.asset_category} | {t.put_call} | "
              f"strike={t.strike} | qty={t.quantity} | price={t.trade_price} | "
              f"date={t.datetime}")

    # Save raw XML for inspection
    with open('/tmp/flex_report_debug.xml', 'w') as f:
        f.write(xml_content)
    print(f"\nFull XML saved to /tmp/flex_report_debug.xml")

if __name__ == '__main__':
    main()
