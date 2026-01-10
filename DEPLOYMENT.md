# Deployment Guide

This project supports two deployment profiles: **dev** and **prod**.

## Quick Start

### Development Mode (with hot-reload)
```bash
# Bash (Linux/Mac/Git Bash)
./deploy.sh dev

# PowerShell (Windows)
.\deploy.ps1 dev
```

### Production Mode
```bash
# Bash (Linux/Mac/Git Bash)
./deploy.sh prod
# or simply
./deploy.sh

# PowerShell (Windows)
.\deploy.ps1 prod
# or simply
.\deploy.ps1
```

## Development Mode

**Features:**
- ✅ Volume mounting for hot-reload
- ✅ Automatic file watching and refresh
- ✅ Changes to code are immediately reflected
- ✅ Uses development Dockerfiles with reload enabled

**How it works:**
- Frontend: Uses Vite dev server with file watching enabled
- Backend: Uses uvicorn with `--reload` flag for automatic restarts
- Both containers mount your local source code directories
- Changes to files trigger automatic rebuilds/refreshes

**Ports:**
- Backend: http://localhost:8000
- Frontend: http://localhost:3000

## Production Mode

**Features:**
- ✅ Optimized production builds
- ✅ No volume mounting (code is baked into images)
- ✅ Smaller image sizes
- ✅ Production-ready configuration

**How it works:**
- Frontend: Builds React app and serves static files via Express
- Backend: Runs optimized FastAPI application
- All code is copied into Docker images at build time

**Ports:**
- Backend: http://localhost:8000
- Frontend: http://localhost:3000

## Managing Containers

### View Logs
```bash
# Backend logs
docker logs -f wheel-tracker-backend

# Frontend logs
docker logs -f wheel-tracker-frontend
```

### Stop Containers
```bash
docker stop wheel-tracker-backend wheel-tracker-frontend
```

### Remove Containers
```bash
docker rm wheel-tracker-backend wheel-tracker-frontend
```

### Clean Up Everything
```bash
docker stop wheel-tracker-backend wheel-tracker-frontend
docker rm wheel-tracker-backend wheel-tracker-frontend
```

## Data Persistence

The backend uses a Docker volume (`wheel-tracker-backend-data`) to persist the SQLite database. This ensures your data persists even when containers are removed and recreated.

## Troubleshooting

### Port Already in Use
If you get a port conflict error, make sure no other services are using ports 3000 or 8000:
```bash
# Check what's using the ports
netstat -ano | findstr :3000  # Windows
lsof -i :3000                 # Linux/Mac
```

### Hot-reload Not Working in Dev Mode
- Make sure you're using `dev` profile
- Check that volumes are mounted correctly: `docker inspect wheel-tracker-frontend`
- Verify file permissions on your local directories

