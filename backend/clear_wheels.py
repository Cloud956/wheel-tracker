import boto3
import os
from dotenv import load_dotenv

load_dotenv()

# Initialize DynamoDB resource
aws_region = os.getenv("AWS_REGION")
aws_access_key = os.getenv("AWS_ACCESS_KEY_ID") or os.getenv("AWS_ACCESS_KEY")
aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY") or os.getenv("AWS_ACCESS_TOKEN")

dynamodb = boto3.resource(
    'dynamodb',
    region_name=aws_region,
    aws_access_key_id=aws_access_key,
    aws_secret_access_key=aws_secret_key
)

WHEEL_TABLE_NAME = os.getenv("DYNAMODB_WHEEL_TABLE_NAME", "Wheels")

def delete_all_items():
    print(f"Scanning and deleting ALL items from table: {WHEEL_TABLE_NAME}")
    table = dynamodb.Table(WHEEL_TABLE_NAME)
    
    try:
        scan = table.scan()
        items = scan.get('Items', [])
        
        with table.batch_writer() as batch:
            count = 0
            for item in items:
                # We need the Primary Key (username) and Sort Key (sk) to delete
                batch.delete_item(
                    Key={
                        'username': item['username'],
                        'sk': item['sk']
                    }
                )
                count += 1
                
        print(f"Deleted {count} items.")
        
        # Handle pagination if more than 1MB of data
        while 'LastEvaluatedKey' in scan:
            scan = table.scan(ExclusiveStartKey=scan['LastEvaluatedKey'])
            items = scan.get('Items', [])
            with table.batch_writer() as batch:
                for item in items:
                    batch.delete_item(
                        Key={
                            'username': item['username'],
                            'sk': item['sk']
                        }
                    )
                    count += len(items)
            print(f"Deleted batch... Total so far: {count}")
            
    except Exception as e:
        print(f"Error clearing table: {e}")

if __name__ == "__main__":
    confirm = input(f"Are you sure you want to delete ALL data from {WHEEL_TABLE_NAME}? (yes/no): ")
    if confirm.lower() == 'yes':
        delete_all_items()
    else:
        print("Operation cancelled.")
