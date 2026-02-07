import boto3
import os
from botocore.exceptions import ClientError
from typing import Optional, Dict, Any, List, Union
from dotenv import load_dotenv
from datetime import datetime
from decimal import Decimal
from enum import Enum
from models import Wheel, CategorizedTrade
import requests

load_dotenv()

# Initialize DynamoDB resource with explicit credentials
# We check for standard AWS env vars first, then fallback to the ones provided by the user
aws_region = os.getenv("AWS_REGION")
aws_access_key = os.getenv("AWS_ACCESS_KEY_ID") or os.getenv("AWS_ACCESS_KEY")
aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY") or os.getenv("AWS_ACCESS_TOKEN")

dynamodb = boto3.resource(
    'dynamodb',
    region_name=aws_region,
    aws_access_key_id=aws_access_key,
    aws_secret_access_key=aws_secret_key
)

# Tables
USER_TABLE_NAME = os.getenv("DYNAMODB_USER_TABLE_NAME", "UserConfigs")
WHEEL_TABLE_NAME = os.getenv("DYNAMODB_WHEEL_TABLE_NAME", "Wheels")

def get_user_config(email: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve user configuration from DynamoDB by email.
    """
    table = dynamodb.Table(USER_TABLE_NAME)
    try:
        response = table.get_item(Key={'username': email})
        return response.get('Item')
    except ClientError as e:
        print(f"Error fetching config for {email}: {e}")
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
        print(f"Error updating config for {email}: {e}")
        return False

def _convert_for_dynamodb(obj: Any) -> Any:
    """
    Recursively converts types for DynamoDB compatibility:
    - float -> Decimal
    - datetime -> ISO string
    - Enum -> value (string/int)
    """
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, list):
        return [_convert_for_dynamodb(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _convert_for_dynamodb(v) for k, v in obj.items()}
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
            
            print(f"Saving item to DynamoDB: {item}")
            
            batch.put_item(Item=item)
            count += 1
            
    return count

def get_wheels(username: str) -> List[Wheel]:
    """
    Retrieve all wheels for a user as Wheel objects.
    """
    table = dynamodb.Table(WHEEL_TABLE_NAME)
    try:
        from boto3.dynamodb.conditions import Key
        response = table.query(
            KeyConditionExpression=Key('username').eq(username)
        )
        items = response.get('Items', [])
        
        wheels = []
        for item in items:
            try:
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

                wheel = Wheel(
                    wheel_id=item['wheel_id'],
                    symbol=item['symbol'],
                    strike=item.get('strike'),
                    start_date=start_dt,
                    end_date=end_dt,
                    is_open=item.get('is_open', True),
                    trades=trades,
                    total_pnl=float(item.get('total_pnl', 0)),
                    total_commissions=float(item.get('total_commissions', 0))
                )
                wheels.append(wheel)
            except Exception as e:
                print(f"Error parsing wheel {item.get('wheel_id')}: {e}")
                continue
                
        return wheels
    except ClientError as e:
        print(f"Error fetching wheels for {username}: {e}")
        return []
