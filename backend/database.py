import boto3
import os
from botocore.exceptions import ClientError
from typing import Optional, Dict, Any, List, Union
from dotenv import load_dotenv
from datetime import datetime
from decimal import Decimal
from enum import Enum
from models import Wheel, CategorizedTrade, Trade
import requests

load_dotenv()

# Initialize DynamoDB resource with explicit credentials
# We check for standard AWS env vars first, then fallback to the ones provided by the user
aws_region = os.getenv("AWS_REGION")
aws_access_key = os.getenv("AWS_ACCESS_KEY_ID") or os.getenv("AWS_ACCESS_KEY")
aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY") or os.getenv("AWS_ACCESS_TOKEN")

# Filter out empty strings if they are passed as ""
if not aws_access_key:
    aws_access_key = None
if not aws_secret_key:
    aws_secret_key = None
if not aws_region:
    aws_region = "us-east-1" # Default to us-east-1 if no region is found

# Only pass credentials if explicitly provided (and not empty)
# Otherwise boto3 will look for credentials in environment variables, ~/.aws/credentials, or IAM Role.
boto3_kwargs = {'service_name': 'dynamodb'}
if aws_region:
    boto3_kwargs['region_name'] = aws_region
if aws_access_key and aws_secret_key:
    boto3_kwargs['aws_access_key_id'] = aws_access_key
    boto3_kwargs['aws_secret_access_key'] = aws_secret_key

dynamodb = boto3.resource(**boto3_kwargs)

# Tables
USER_TABLE_NAME = os.getenv("DYNAMODB_USER_TABLE_NAME", "UserConfigs")
WHEEL_TABLE_NAME = os.getenv("DYNAMODB_WHEEL_TABLE_NAME", "Wheels")
SNAKE_TABLE_NAME = os.getenv("DYNAMODB_SNAKE_TABLE_NAME", "snake_highscores")
DAILY_PNL_TABLE_NAME        = os.getenv("DYNAMODB_DAILY_PNL_TABLE_NAME",         "daily_pnl")
PMCC_SHORT_CALLS_TABLE      = os.getenv("DYNAMODB_PMCC_SHORT_CALLS_TABLE",    "pmcc_short_calls")
PMCC_LEAP_SNAPSHOTS_TABLE   = os.getenv("DYNAMODB_PMCC_LEAP_SNAPSHOTS_TABLE", "pmcc_leap_snapshots")

def get_user_config(email: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve user configuration from DynamoDB by email.
    """
    table = dynamodb.Table(USER_TABLE_NAME)
    try:
        response = table.get_item(Key={'username': email})
        return response.get('Item')
    except ClientError as e:
        return None

def update_user_config(email: str, config: Dict[str, Any]) -> bool:
    """
    Update user configuration in DynamoDB.
    Expected config dict should contain keys to update.
    """
    table = dynamodb.Table(USER_TABLE_NAME)
    
    # Construct UpdateExpression and ExpressionAttributeValues dynamically
    # We want to update only the fields provided in `config`
    update_parts = []
    expr_values = {}
    expr_names = {} # To handle reserved words if any
    
    for key, value in config.items():
        if key == 'username': continue # Don't update the key
        
        # Use placeholders for keys and values
        attr_name = f"#{key}"
        attr_val = f":{key}"
        
        update_parts.append(f"{attr_name} = {attr_val}")
        expr_values[attr_val] = value
        expr_names[attr_name] = key
        
    if not update_parts:
        return True # Nothing to update
        
    update_expression = "SET " + ", ".join(update_parts)
    
    try:
        table.update_item(
            Key={'username': email},
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expr_names,
            ExpressionAttributeValues=expr_values
        )
        return True
    except ClientError as e:
        return False

def _convert_for_dynamodb(obj: Any) -> Any:
    """
    Recursively converts types for DynamoDB compatibility:
    - float -> Decimal (NaN/Inf clamped to 0)
    - datetime -> ISO string
    - Enum -> value (string/int)
    """
    if isinstance(obj, float):
        return _safe_decimal(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, list):
        return [_convert_for_dynamodb(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _convert_for_dynamodb(v) for k, v in obj.items() if v is not None}
    return obj

def _convert_from_dynamodb(obj: Any) -> Any:
    """
    Recursively converts DynamoDB types back to Python native types:
    - Decimal -> float
    - Leaves other types (str, bool, list, dict, None) unchanged.
    """
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, list):
        return [_convert_from_dynamodb(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _convert_from_dynamodb(v) for k, v in obj.items()}
    return obj

def save_wheels(username: str, wheels: List[Dict[str, Any]]) -> int:
    """
    Save a list of wheels to DynamoDB.
    Uses 'username' as PK and 'start_date#symbol' as SK.
    Handles type conversion (float->Decimal, datetime->str, Enum->val) internally.
    """
    table = dynamodb.Table(WHEEL_TABLE_NAME)
    count = 0
    
    with table.batch_writer() as batch:
        for wheel in wheels:
            # Convert the entire wheel dict to be DynamoDB compatible
            clean_wheel = _convert_for_dynamodb(wheel)
            
            # Create composite sort key from the CLEANED values (which are strings now)
            start_date_str = str(clean_wheel.get('start_date', ''))
            wheel_id = clean_wheel.get('wheel_id', 'UNKNOWN')
            sort_key = f"{start_date_str}#{wheel_id}"
            
            item = {
                'username': username,
                'sk': sort_key, # Sort Key
                **clean_wheel
            }
            
            
            batch.put_item(Item=item)
            count += 1
            
    return count

def delete_user_wheels(username: str) -> int:
    """
    Deletes ALL wheels for a specific user.
    """
    table = dynamodb.Table(WHEEL_TABLE_NAME)
    count = 0
    try:
        from boto3.dynamodb.conditions import Key
        
        # Query all items for the user (Partition Key only query)
        response = table.query(
            KeyConditionExpression=Key('username').eq(username)
        )
        items = response.get('Items', [])
        
        with table.batch_writer() as batch:
            for item in items:
                batch.delete_item(
                    Key={
                        'username': item['username'],
                        'sk': item['sk']
                    }
                )
                count += 1
                
        # Handle pagination if user has many items
        while 'LastEvaluatedKey' in response:
            response = table.query(
                KeyConditionExpression=Key('username').eq(username),
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            items = response.get('Items', [])
            with table.batch_writer() as batch:
                for item in items:
                    batch.delete_item(
                        Key={
                            'username': item['username'],
                            'sk': item['sk']
                        }
                    )
                    count += 1
                    
        return count
    except ClientError as e:
        return 0

def get_wheels(username: str) -> List[Wheel]:
    """
    Retrieve all wheels for a user as Wheel objects.
    Handles pagination and converts DynamoDB types (Decimal→float).
    """
    table = dynamodb.Table(WHEEL_TABLE_NAME)
    try:
        from boto3.dynamodb.conditions import Key

        # Paginated query to retrieve ALL wheel items
        items = []
        response = table.query(
            KeyConditionExpression=Key('username').eq(username)
        )
        items.extend(response.get('Items', []))

        while 'LastEvaluatedKey' in response:
            response = table.query(
                KeyConditionExpression=Key('username').eq(username),
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            items.extend(response.get('Items', []))
        
        wheels = []
        for item in items:
            try:
                # Convert DynamoDB Decimal types to Python float
                item = _convert_from_dynamodb(item)

                # Handle string dates if coming from DB
                start_dt = item['start_date']
                if isinstance(start_dt, str):
                    start_dt = datetime.fromisoformat(start_dt)
                    
                end_dt = item.get('end_date')
                if isinstance(end_dt, str) and end_dt:
                    end_dt = datetime.fromisoformat(end_dt)
                
                # Reconstruct trades if present
                trades = []
                if 'trades' in item:
                    for t_data in item['trades']:
                        trades.append(CategorizedTrade(**t_data))

                # Reconstruct currentSoldCall if present
                current_sold_call = None
                if item.get('currentSoldCall'):
                    current_sold_call = Trade(**item['currentSoldCall'])

                # Reconstruct holdings if present
                holdings = []
                if 'holdings' in item:
                    from models import Holding
                    for h_data in item['holdings']:
                        holdings.append(Holding(**h_data))

                wheel = Wheel(
                    wheel_id=item['wheel_id'],
                    symbol=item['symbol'],
                    strike=item.get('strike'),
                    start_date=start_dt,
                    end_date=end_dt,
                    is_open=item.get('is_open', True),
                    phase=item.get('phase', 'CSP'),
                    trades=trades,
                    total_pnl=float(item.get('total_pnl', 0)),
                    premium_collected=float(item.get('premium_collected', 0)),
                    total_commissions=float(item.get('total_commissions', 0)),
                    currentSoldCall=current_sold_call,
                    market_price=float(item['market_price']) if item.get('market_price') is not None else None,
                    cost_basis=float(item['cost_basis']) if item.get('cost_basis') is not None else None,
                    unrealized_pnl=float(item['unrealized_pnl']) if item.get('unrealized_pnl') is not None else None,
                    holdings=holdings,
                )
                wheels.append(wheel)
            except Exception as e:
                import traceback
                print(f"ERROR deserializing wheel '{item.get('wheel_id', 'UNKNOWN')}': {e}")
                traceback.print_exc()
                continue
                
        return wheels
    except ClientError as e:
        print(f"ERROR querying wheels for {username}: {e}")
        return []


# ── Daily PnL ────────────────────────────────────────────────────

def get_daily_pnl(username: str) -> List[Dict[str, Any]]:
    """
    Retrieve all daily PnL records for a user, sorted by date ascending.
    Each item has: date (str, YYYY-MM-DD), daily_pnl (float), cumulative_pnl (float).
    """
    table = dynamodb.Table(DAILY_PNL_TABLE_NAME)
    try:
        from boto3.dynamodb.conditions import Key
        items = []
        response = table.query(
            KeyConditionExpression=Key('username').eq(username)
        )
        items.extend(response.get('Items', []))
        while 'LastEvaluatedKey' in response:
            response = table.query(
                KeyConditionExpression=Key('username').eq(username),
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            items.extend(response.get('Items', []))

        # Convert Decimals and sort by date
        result = []
        for item in items:
            item = _convert_from_dynamodb(item)
            result.append({
                'date': item['date'],
                'daily_pnl': float(item.get('daily_pnl', 0)),
                'cumulative_pnl': float(item.get('cumulative_pnl', 0)),
            })
        result.sort(key=lambda x: x['date'])
        return result
    except ClientError as e:
        print(f"ERROR querying daily_pnl for {username}: {e}")
        return []


def save_daily_pnl(username: str, date: str, daily_pnl: float, cumulative_pnl: float) -> bool:
    """
    Upsert a single daily PnL record.
    PK: username, SK: date (YYYY-MM-DD).
    """
    table = dynamodb.Table(DAILY_PNL_TABLE_NAME)
    try:
        table.put_item(Item={
            'username': username,
            'date': date,
            'daily_pnl': Decimal(str(daily_pnl)),
            'cumulative_pnl': Decimal(str(cumulative_pnl)),
        })
        return True
    except ClientError as e:
        print(f"ERROR saving daily_pnl for {username} on {date}: {e}")
        return False


# ── PMCC / Futuristic Wheel ──────────────────────────────────────────────

def _safe_decimal(val) -> Decimal:
    """Convert a float to Decimal, replacing NaN/Inf with 0 to avoid DynamoDB validation errors."""
    try:
        d = Decimal(str(val))
        if not d.is_finite():
            return Decimal('0')
        return d
    except Exception:
        return Decimal('0')


def delete_pmcc_short_calls(username: str) -> int:
    """Delete ALL PMCC short call records for a user. Returns count deleted."""
    table = dynamodb.Table(PMCC_SHORT_CALLS_TABLE)
    try:
        from boto3.dynamodb.conditions import Key
        response = table.query(KeyConditionExpression=Key('username').eq(username))
        items = response.get('Items', [])
        while 'LastEvaluatedKey' in response:
            response = table.query(
                KeyConditionExpression=Key('username').eq(username),
                ExclusiveStartKey=response['LastEvaluatedKey'],
            )
            items.extend(response.get('Items', []))
        if items:
            with table.batch_writer() as batch:
                for item in items:
                    batch.delete_item(Key={'username': item['username'], 'call_id': item['call_id']})
        return len(items)
    except ClientError as e:
        print(f"ERROR deleting pmcc_short_calls for {username}: {e}")
        return 0


def save_pmcc_short_calls(username: str, calls: List[Dict[str, Any]]) -> int:
    """
    Full-replace all PMCC short call records for a user.
    Deletes all existing records first, then writes the new batch.
    PK: username  |  SK: call_id
    """
    table = dynamodb.Table(PMCC_SHORT_CALLS_TABLE)

    # 1. Delete all existing records for this user
    try:
        from boto3.dynamodb.conditions import Key
        response = table.query(KeyConditionExpression=Key('username').eq(username))
        existing = response.get('Items', [])
        while 'LastEvaluatedKey' in response:
            response = table.query(
                KeyConditionExpression=Key('username').eq(username),
                ExclusiveStartKey=response['LastEvaluatedKey'],
            )
            existing.extend(response.get('Items', []))

        if existing:
            with table.batch_writer() as batch:
                for item in existing:
                    batch.delete_item(Key={'username': item['username'], 'call_id': item['call_id']})
    except ClientError as e:
        print(f"WARN: could not purge old pmcc_short_calls for {username}: {e}")

    # 2. Write the new batch
    count = 0
    with table.batch_writer() as batch:
        for call in calls:
            clean = _convert_for_dynamodb(call)
            item  = {'username': username, 'call_id': clean.get('call_id', ''), **clean}
            batch.put_item(Item=item)
            count += 1
    return count


def get_pmcc_short_calls(username: str) -> List[Dict[str, Any]]:
    """Get all PMCC short call records for a user."""
    table = dynamodb.Table(PMCC_SHORT_CALLS_TABLE)
    try:
        from boto3.dynamodb.conditions import Key
        items = []
        response = table.query(KeyConditionExpression=Key('username').eq(username))
        items.extend(response.get('Items', []))
        while 'LastEvaluatedKey' in response:
            response = table.query(
                KeyConditionExpression=Key('username').eq(username),
                ExclusiveStartKey=response['LastEvaluatedKey'],
            )
            items.extend(response.get('Items', []))
        return [_convert_from_dynamodb(item) for item in items]
    except ClientError as e:
        print(f"ERROR fetching pmcc_short_calls for {username}: {e}")
        return []


def save_pmcc_leap_snapshot(username: str, snapshot_date: str, leaps: List[Dict[str, Any]]) -> int:
    """
    Save daily LEAP position snapshots.
    PK: username  |  SK: date#symbol  (e.g. "2026-02-27#GOOGL")
    Re-syncing on the same date simply overwrites.
    """
    table = dynamodb.Table(PMCC_LEAP_SNAPSHOTS_TABLE)
    count = 0
    with table.batch_writer() as batch:
        for leap in leaps:
            symbol = leap.get('symbol', 'UNKNOWN')
            sk     = f"{snapshot_date}#{symbol}"
            clean  = _convert_for_dynamodb(leap)
            item   = {'username': username, 'sk': sk, 'snapshot_date': snapshot_date, **clean}
            batch.put_item(Item=item)
            count += 1
    return count


def get_pmcc_leap_snapshots(username: str) -> List[Dict[str, Any]]:
    """Get all LEAP snapshots for a user, sorted ascending by SK (date#symbol)."""
    table = dynamodb.Table(PMCC_LEAP_SNAPSHOTS_TABLE)
    try:
        from boto3.dynamodb.conditions import Key
        items = []
        response = table.query(KeyConditionExpression=Key('username').eq(username))
        items.extend(response.get('Items', []))
        while 'LastEvaluatedKey' in response:
            response = table.query(
                KeyConditionExpression=Key('username').eq(username),
                ExclusiveStartKey=response['LastEvaluatedKey'],
            )
            items.extend(response.get('Items', []))
        result = [_convert_from_dynamodb(item) for item in items]
        result.sort(key=lambda x: x.get('sk', ''))
        return result
    except ClientError as e:
        print(f"ERROR fetching pmcc_leap_snapshots for {username}: {e}")
        return []


# ── Snake Highscores ──────────────────────────────────────────────

def save_highscore(name: str, score: int, collected: dict) -> bool:
    """Save a snake highscore to DynamoDB."""
    table = dynamodb.Table(SNAKE_TABLE_NAME)
    try:
        # Sort key: zero-padded score (descending) + timestamp for uniqueness
        # We pad to 10 digits so DynamoDB string sort gives numeric order
        ts = datetime.utcnow().isoformat()
        # Use inverted score for descending sort (higher scores first)
        inverted = 9999999999 - score
        sk = f"{str(inverted).zfill(10)}#{ts}"
        
        item = {
            'pk': 'GLOBAL',
            'sk': sk,
            'name': name[:20],  # Cap name length
            'score': score,
            'collected': _convert_for_dynamodb(collected),
            'timestamp': ts,
        }
        table.put_item(Item=item)
        return True
    except ClientError as e:
        print(f"Error saving highscore: {e}")
        return False


def get_highscores(limit: int = 10) -> list:
    """Retrieve top highscores from DynamoDB, sorted by score descending."""
    table = dynamodb.Table(SNAKE_TABLE_NAME)
    try:
        from boto3.dynamodb.conditions import Key
        response = table.query(
            KeyConditionExpression=Key('pk').eq('GLOBAL'),
            Limit=limit,
            ScanIndexForward=True,  # ascending on sk, which has inverted score = descending by real score
        )
        items = response.get('Items', [])
        results = []
        for item in items:
            results.append({
                'name': item.get('name', '???'),
                'score': int(item.get('score', 0)),
                'collected': item.get('collected', {}),
                'timestamp': item.get('timestamp', ''),
            })
        return results
    except ClientError as e:
        print(f"Error fetching highscores: {e}")
        return []
