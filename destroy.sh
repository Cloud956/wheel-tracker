#!/bin/bash

# Shell script to stop and remove Docker containers and optionally images
# This will destroy the wheel-tracker deployment

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${RED}🗑️  Destroying wheel-tracker deployment...${NC}"

# Stop containers
echo -e "${YELLOW}Stopping containers...${NC}"
if docker stop wheel-tracker-backend wheel-tracker-frontend 2>/dev/null; then
    echo -e "  ${GREEN}✓ Stopped wheel-tracker-backend${NC}"
    echo -e "  ${GREEN}✓ Stopped wheel-tracker-frontend${NC}"
else
    echo -e "  ${YELLOW}⚠ Some containers may not have been running${NC}"
fi

# Remove containers
echo -e "${YELLOW}Removing containers...${NC}"
if docker rm wheel-tracker-backend wheel-tracker-frontend 2>/dev/null; then
    echo -e "  ${GREEN}✓ Removed wheel-tracker-backend${NC}"
    echo -e "  ${GREEN}✓ Removed wheel-tracker-frontend${NC}"
else
    echo -e "  ${YELLOW}⚠ Some containers may not have existed${NC}"
fi

# Ask if user wants to remove images
echo ""
read -p "Do you want to remove Docker images as well? (y/N): " remove_images
if [[ $remove_images == "y" || $remove_images == "Y" ]]; then
    echo -e "${YELLOW}Removing images...${NC}"
    if docker rmi wheel-tracker-backend:latest wheel-tracker-frontend:latest 2>/dev/null; then
        echo -e "  ${GREEN}✓ Removed wheel-tracker-backend:latest${NC}"
        echo -e "  ${GREEN}✓ Removed wheel-tracker-frontend:latest${NC}"
    else
        echo -e "  ${YELLOW}⚠ Some images may not have existed${NC}"
    fi
fi

echo ""
echo -e "${GREEN}✅ Destruction complete!${NC}"
echo ""
echo "Containers have been stopped and removed."
if [[ $remove_images == "y" || $remove_images == "Y" ]]; then
    echo "Images have been removed."
else
    echo "Images were preserved. Run deploy.sh again to rebuild."
fi
