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
docker stop wheel-tracker-backend wheel-tracker-frontend 2>/dev/null || true
docker rm wheel-tracker-backend wheel-tracker-frontend 2>/dev/null || true

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
  echo -e "${BLUE}Building images (PROD mode)...${NC}"
  docker build -t wheel-tracker-backend:latest ./backend
  docker build -t wheel-tracker-frontend:latest ./frontend

  echo -e "${GREEN}Starting backend (PROD)...${NC}"
  docker run -d \
    --name wheel-tracker-backend \
    --network wheel-tracker-network \
    -p 8000:8000 \
    -v wheel-tracker-backend-data:/data \
    wheel-tracker-backend:latest

  echo -e "${GREEN}Starting frontend (PROD)...${NC}"
  docker run -d \
    --name wheel-tracker-frontend \
    --network wheel-tracker-network \
    -p 3000:3000 \
    wheel-tracker-frontend:latest
fi

echo -e "\n${GREEN}✅ Deployment complete!${NC}"
echo "Backend: http://localhost:8000"
echo "Frontend: http://localhost:3000"