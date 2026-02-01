import boto3
import os
from botocore.exceptions import ClientError
from typing import Optional, Dict, Any
from dotenv import load_dotenv

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

TABLE_NAME = os.getenv("DYNAMODB_USER_TABLE_NAME", "UserConfigs")

def get_user_config(email: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve user configuration from DynamoDB by email.
    """
    table = dynamodb.Table(TABLE_NAME)
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
    table = dynamodb.Table(TABLE_NAME)
    
    # Construct UpdateExpression and ExpressionAttributeValues dynamically
    # We want to update only the fields provided in `config`
    update_parts = []
    expr_values = {}
    expr_names = {} # To handle reserved words if any
    
    for key, value in config.items():
        if key == 'email': continue # Don't update the key
        
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
