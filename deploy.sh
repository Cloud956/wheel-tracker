#!/bin/bash

# Script to build and deploy both frontend and backend containers
set -e 

PROFILE=${1:-prod}

if [ "$PROFILE" != "dev" ] && [ "$PROFILE" != "prod" ]; then
  echo "Error: Profile must be 'dev' or 'prod'"
  exit 1
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
