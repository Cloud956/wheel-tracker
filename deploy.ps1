# PowerShell script to build and deploy both frontend and backend containers
# Backend will be accessible on port 8000
# Frontend will be accessible on port 3000

Write-Host "🚀 Starting deployment process..." -ForegroundColor Cyan

# Stop and remove existing containers if they exist
Write-Host "Cleaning up existing containers..." -ForegroundColor Yellow
docker stop wheel-tracker-backend wheel-tracker-frontend 2>$null
docker rm wheel-tracker-backend wheel-tracker-frontend 2>$null

# Build backend image
Write-Host "Building backend Docker image..." -ForegroundColor Blue
Set-Location backend
docker build -t wheel-tracker-backend:latest .
Set-Location ..

# Build frontend image
Write-Host "Building frontend Docker image..." -ForegroundColor Blue
Set-Location frontend
docker build -t wheel-tracker-frontend:latest .
Set-Location ..

# Run backend container on port 8000
Write-Host "Starting backend container on port 8000..." -ForegroundColor Green
docker run -d `
  --name wheel-tracker-backend `
  -p 8000:8000 `
  wheel-tracker-backend:latest

# Run frontend container on port 3000
Write-Host "Starting frontend container on port 3000..." -ForegroundColor Green
docker run -d `
  --name wheel-tracker-frontend `
  -p 3000:3000 `
  wheel-tracker-frontend:latest

Write-Host ""
Write-Host "✅ Deployment complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Services are now running:"
Write-Host "  Backend:  http://localhost:8000" -ForegroundColor Blue
Write-Host "  Frontend: http://localhost:3000" -ForegroundColor Blue
Write-Host ""
Write-Host "To view logs:"
Write-Host "  docker logs -f wheel-tracker-backend"
Write-Host "  docker logs -f wheel-tracker-frontend"
Write-Host ""
Write-Host "To stop containers:"
Write-Host "  docker stop wheel-tracker-backend wheel-tracker-frontend"

