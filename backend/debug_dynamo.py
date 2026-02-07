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

def inspect_tables():
    print("--- DynamoDB Tables Inspection ---")
    try:
        for table in dynamodb.tables.all():
            print(f"\nTable: {table.name}")
            print(f"  KeySchema: {table.key_schema}")
            print(f"  AttributeDefinitions: {table.attribute_definitions}")
            print(f"  Item Count: {table.item_count}")
    except Exception as e:
        print(f"Error inspecting tables: {e}")

if __name__ == "__main__":
    inspect_tables()
