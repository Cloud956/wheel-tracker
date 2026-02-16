# Deploying Wheel Tracker to AWS EC2

This guide outlines the steps to deploy the Wheel Tracker application to an AWS EC2 instance using Docker Compose.

## Prerequisites
- An AWS Account
- A domain name (optional, but recommended for SSL)

## Step 1: Launch an EC2 Instance
1. **Login to AWS Console** and navigate to EC2.
2. **Launch Instance**:
   - **Name**: `WheelTracker-Prod`
   - **AMI**: Amazon Linux 2023 or Ubuntu 22.04 LTS.
   - **Instance Type**: `t3.small` (Recommended minimum for two containers + build operations). `t2.micro` might be too small for memory during builds.
   - **Key Pair**: 
     - This is your "password" file.
     - Select **"Create new key pair"**.
     - Give it a name (e.g., `wheel-key`).
     - Select **RSA** and **.pem**.
     - **Download it immediately** and save it somewhere safe (e.g., `~/.ssh/wheel-key.pem`).
     - *Note*: If you lose this file, you cannot SSH into the server later.
3. **Network Settings (Security Groups) - RESTRICTED ACCESS**:
   - Instead of default settings, create a new **Security Group**.
   - Add **Inbound Rules** to restrict access to only specific IP addresses:
     - **Type**: SSH | **Port**: 22 | **Source**: `My IP` (AWS will auto-fill yours).
     - **Type**: Custom TCP | **Port**: 3000 (Frontend) | **Source**: `My IP` AND `[Other IP]/32`.
     - **Type**: Custom TCP | **Port**: 8000 (Backend) | **Source**: `My IP` AND `[Other IP]/32`.
     - **Type**: HTTP | **Port**: 80 (Web) | **Source**: `0.0.0.0/0` (Anywhere).
   - *Important*: Open port 80 for normal web access via your domain. Port 3000 and 8000 are now behind Nginx and don't need to be publicly exposed unless for debugging.
4. **IAM Role** (Crucial for DynamoDB):
   This defines permissions for your server without needing API keys.
   1. Go to the **IAM Dashboard** in AWS Console.
   2. Click **Roles** -> **Create role**.
   3. Select **AWS service** -> **EC2** from the options.
   4. Click **Next** and search for `AmazonDynamoDBFullAccess`. Check the box correctly.
   5. Click **Next**, name it `WheelTracker-EC2-Role`, and create it.
   6. **Back in EC2 Launch Wizard**: Look for "Advanced details" -> "IAM instance profile" and select the role you just created.

## Step 2: Set up the Server
SSH into your instance:
```bash
ssh -i "your-key.pem" ec2-user@your-instance-ip
```

Install Docker and Git:
```bash
# For Amazon Linux 2023
sudo dnf update -y
sudo dnf install -y docker git
sudo service docker start
sudo usermod -a -G docker ec2-user
# Logout and log back in to apply group changes
exit
```

Install Docker Compose:
```bash
# Log back in
ssh -i "your-key.pem" ec2-user@your-instance-ip

mkdir -p ~/.docker/cli-plugins/
curl -SL https://github.com/docker/compose/releases/download/v2.24.5/docker-compose-linux-x86_64 -o ~/.docker/cli-plugins/docker-compose
chmod +x ~/.docker/cli-plugins/docker-compose
docker compose version
```

## Step 3: Deployment
1. **Clone the Repo**:
   ```bash
   git clone https://github.com/Cloud956/wheel-tracker.git
   cd wheel-tracker
   ```

2. **Configuration**:
   Create a `.env` file with your config. explicitly:
   ```bash
   touch .env
   nano .env
   ```
   Content:
   ```ini
   AWS_REGION=us-east-1
   # Credentials are handled by IAM Role, so typically you don't need access keys here if you did Step 1.4.
   # If not using IAM Role, uncomment below:
   # AWS_ACCESS_KEY_ID=your_key
   # AWS_SECRET_ACCESS_KEY=your_secret
   ```

3. **Start the Stack**:
   Use the production compose file created for this deployment:
   ```bash
   docker compose -f docker-compose.prod.yml up -d --build
   ```

## Step 4: DynamoDB Setup (One Time)
Ensure your DynamoDB tables exist in the region defined.
- Tables needed: `UserConfigs`, `Wheels`
- Partition Keys: Check your code/local setup (likely `email` or `wheel_id`).

## Step 5: Access
- Open browser to: `http://your-domain.com` or `http://your-instance-ip`
- The application now runs on port 80 via Nginx.
