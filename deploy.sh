#!/bin/bash

# Script to build and deploy both frontend and backend containers
set -e 

# Load .env file if it exists (automatically export variables)
if [ -f .env ]; then
  # export $(grep -v '^#' .env | xargs)
  # Safer way to load .env in bash without xargs weirdness affecting strings with spaces
  set -a
  source .env
  set +a
  echo "✅ Loaded environment variables from .env"
fi

PROFILE=${1:-prod}

if [ "$PROFILE" = "dev" ] && [ "$PROFILE" != "prod" ]; then
  echo "Error: Profile must be 'dev' or 'prod'"
  exit 1
fi

# Ensure certs directory exists
mkdir -p certs

# Check if certificates exist, if not generate self-signed
if [ ! -f certs/fullchain.pem ] || [ ! -f certs/privkey.pem ]; then
    echo -e "${YELLOW}Generating self-signed SSL certificates...${NC}"
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout certs/privkey.pem \
        -out certs/fullchain.pem \
        -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost"
    echo -e "${GREEN}Self-signed certificates generated.${NC}"
fi

echo "🚀 Starting deployment process (Profile: $PROFILE)..."

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# NEW: Create a shared network if it doesn't exist
docker network create wheel-tracker-network 2>/dev/null || true

echo -e "${YELLOW}Cleaning up existing containers...${NC}"
docker stop wheel-tracker-backend wheel-tracker-frontend wheel-tracker-nginx 2>/dev/null || true
docker rm wheel-tracker-backend wheel-tracker-frontend wheel-tracker-nginx 2>/dev/null || true

if [ "$PROFILE" = "dev" ]; then
  echo -e "${CYAN}Building images (DEV mode)...${NC}"
  docker build -f backend/Dockerfile.dev -t wheel-tracker-backend:dev ./backend
  docker build -f frontend/Dockerfile.dev -t wheel-tracker-frontend:dev ./frontend

  echo -e "${GREEN}Starting backend (DEV)...${NC}"
  docker run -d \
    --name wheel-tracker-backend \
    --network wheel-tracker-network \
    -p 8000:8000 \
    -v "$(pwd)/backend:/app" \
    -v wheel-tracker-backend-data:/data \
    wheel-tracker-backend:dev

  echo -e "${GREEN}Starting frontend (DEV)...${NC}"
  docker run -d \
    --name wheel-tracker-frontend \
    --network wheel-tracker-network \
    -p 3000:3000 \
    -v "$(pwd)/frontend:/app" \
    -v /app/node_modules \
    wheel-tracker-frontend:dev

else
  echo -e "${BLUE}Building and Starting containers (PROD mode) with Docker Compose...${NC}"
  # Check if docker-compose is available, if not try 'docker compose' (v2)
  if command -v docker-compose &> /dev/null; then
    docker-compose -f docker-compose.prod.yml up -d --build
  else
    docker compose -f docker-compose.prod.yml up -d --build
  fi

  echo -e "\n${GREEN}✅ Deployment complete!${NC}"
  echo "Application available at http://localhost (port 80)"
  echo "Ensure your EC2 Security Group allows inbound traffic on port 80."
fi
