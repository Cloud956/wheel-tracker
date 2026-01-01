#!/bin/bash

# Script to build and deploy both frontend and backend containers
# Backend will be accessible on port 8000
# Frontend will be accessible on port 3000

set -e  # Exit on error

echo "🚀 Starting deployment process..."

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Stop and remove existing containers if they exist
echo -e "${YELLOW}Cleaning up existing containers...${NC}"
docker stop wheel-tracker-backend wheel-tracker-frontend 2>/dev/null || true
docker rm wheel-tracker-backend wheel-tracker-frontend 2>/dev/null || true

# Build backend image
echo -e "${BLUE}Building backend Docker image...${NC}"
cd backend
docker build -t wheel-tracker-backend:latest .
cd ..

# Build frontend image
echo -e "${BLUE}Building frontend Docker image...${NC}"
cd frontend
docker build -t wheel-tracker-frontend:latest .
cd ..

# Run backend container on port 8000
echo -e "${GREEN}Starting backend container on port 8000...${NC}"
docker run -d \
  --name wheel-tracker-backend \
  -p 8000:8000 \
  wheel-tracker-backend:latest

# Run frontend container on port 3000
echo -e "${GREEN}Starting frontend container on port 3000...${NC}"
docker run -d \
  --name wheel-tracker-frontend \
  -p 3000:3000 \
  wheel-tracker-frontend:latest

echo ""
echo -e "${GREEN}✅ Deployment complete!${NC}"
echo ""
echo "Services are now running:"
echo -e "  ${BLUE}Backend:${NC}  http://localhost:8000"
echo -e "  ${BLUE}Frontend:${NC} http://localhost:3000"
echo ""
echo "To view logs:"
echo "  docker logs -f wheel-tracker-backend"
echo "  docker logs -f wheel-tracker-frontend"
echo ""
echo "To stop containers:"
echo "  docker stop wheel-tracker-backend wheel-tracker-frontend"

