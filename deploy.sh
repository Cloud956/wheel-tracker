#!/bin/bash

# Script to build and deploy both frontend and backend containers
# Usage: ./deploy.sh [dev|prod]
#   dev  - Development mode with volume mounting and hot-reload
#   prod - Production mode (default)

set -e  # Exit on error

# Default to prod if no argument provided
PROFILE=${1:-prod}

if [ "$PROFILE" != "dev" ] && [ "$PROFILE" != "prod" ]; then
  echo "Error: Profile must be 'dev' or 'prod'"
  echo "Usage: ./deploy.sh [dev|prod]"
  exit 1
fi

echo "🚀 Starting deployment process (Profile: $PROFILE)..."

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Stop and remove existing containers if they exist
echo -e "${YELLOW}Cleaning up existing containers...${NC}"
docker stop wheel-tracker-backend wheel-tracker-frontend 2>/dev/null || true
docker rm wheel-tracker-backend wheel-tracker-frontend 2>/dev/null || true

if [ "$PROFILE" = "dev" ]; then
  # Development mode - build dev images and mount volumes
  echo -e "${CYAN}Building backend Docker image (DEV mode)...${NC}"
  cd backend
  docker build -f Dockerfile.dev -t wheel-tracker-backend:dev .
  cd ..

  echo -e "${CYAN}Building frontend Docker image (DEV mode)...${NC}"
  cd frontend
  docker build -f Dockerfile.dev -t wheel-tracker-frontend:dev .
  cd ..

  # Run backend container with volume mounting for hot-reload
  echo -e "${GREEN}Starting backend container on port 8000 (DEV mode with volumes)...${NC}"
  docker run -d \
    --name wheel-tracker-backend \
    -p 8000:8000 \
    -v "$(pwd)/backend:/app" \
    -v wheel-tracker-backend-data:/data \
    wheel-tracker-backend:dev

  # Run frontend container with volume mounting for hot-reload
  echo -e "${GREEN}Starting frontend container on port 3000 (DEV mode with volumes)...${NC}"
  docker run -d \
    --name wheel-tracker-frontend \
    -p 3000:3000 \
    -v "$(pwd)/frontend:/app" \
    -v /app/node_modules \
    -v /app/dist \
    -e NODE_ENV=development \
    wheel-tracker-frontend:dev

else
  # Production mode - build production images
  echo -e "${BLUE}Building backend Docker image (PROD mode)...${NC}"
  cd backend
  docker build -t wheel-tracker-backend:latest .
  cd ..

  echo -e "${BLUE}Building frontend Docker image (PROD mode)...${NC}"
  cd frontend
  docker build -t wheel-tracker-frontend:latest .
  cd ..

  # Run backend container on port 8000
  echo -e "${GREEN}Starting backend container on port 8000 (PROD mode)...${NC}"
  docker run -d \
    --name wheel-tracker-backend \
    -p 8000:8000 \
    -v wheel-tracker-backend-data:/data \
    wheel-tracker-backend:latest

  # Run frontend container on port 3000
  echo -e "${GREEN}Starting frontend container on port 3000 (PROD mode)...${NC}"
  docker run -d \
    --name wheel-tracker-frontend \
    -p 3000:3000 \
    wheel-tracker-frontend:latest
fi

echo ""
echo -e "${GREEN}✅ Deployment complete!${NC}"
echo ""
echo "Services are now running:"
echo -e "  ${BLUE}Backend:${NC}  http://localhost:8000"
echo -e "  ${BLUE}Frontend:${NC} http://localhost:3000"
echo ""
if [ "$PROFILE" = "dev" ]; then
  echo -e "${CYAN}Development mode:${NC}"
  echo "  - Volumes are mounted for hot-reload"
  echo "  - Changes to files will automatically refresh"
fi
echo ""
echo "To view logs:"
echo "  docker logs -f wheel-tracker-backend"
echo "  docker logs -f wheel-tracker-frontend"
echo ""
echo "To stop containers:"
echo "  docker stop wheel-tracker-backend wheel-tracker-frontend"
