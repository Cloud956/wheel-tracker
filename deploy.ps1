# PowerShell script to build and deploy both frontend and backend containers
# Usage: .\deploy.ps1 [dev|prod]
#   dev  - Development mode with volume mounting and hot-reload
#   prod - Production mode (default)

param(
    [Parameter(Position=0)]
    [ValidateSet("dev", "prod")]
    [string]$Profile = "prod"
)

Write-Host "🚀 Starting deployment process (Profile: $Profile)..." -ForegroundColor Cyan

# Stop and remove existing containers if they exist
Write-Host "Cleaning up existing containers..." -ForegroundColor Yellow
docker stop wheel-tracker-backend wheel-tracker-frontend 2>$null
docker rm wheel-tracker-backend wheel-tracker-frontend 2>$null

if ($Profile -eq "dev") {
    # Development mode - build dev images and mount volumes
    Write-Host "Building backend Docker image (DEV mode)..." -ForegroundColor Cyan
    Set-Location backend
    docker build -f Dockerfile.dev -t wheel-tracker-backend:dev .
    Set-Location ..

    Write-Host "Building frontend Docker image (DEV mode)..." -ForegroundColor Cyan
    Set-Location frontend
    docker build -f Dockerfile.dev -t wheel-tracker-frontend:dev .
    Set-Location ..

    # Run backend container with volume mounting for hot-reload
    Write-Host "Starting backend container on port 8000 (DEV mode with volumes)..." -ForegroundColor Green
    $backendPath = (Resolve-Path "backend").Path
    docker run -d `
        --name wheel-tracker-backend `
        -p 8000:8000 `
        -v "${backendPath}:/app" `
        -v wheel-tracker-backend-data:/data `
        wheel-tracker-backend:dev

    # Run frontend container with volume mounting for hot-reload
    Write-Host "Starting frontend container on port 3000 (DEV mode with volumes)..." -ForegroundColor Green
    $frontendPath = (Resolve-Path "frontend").Path
    docker run -d `
        --name wheel-tracker-frontend `
        -p 3000:3000 `
        -v "${frontendPath}:/app" `
        -v /app/node_modules `
        -v /app/dist `
        -e NODE_ENV=development `
        wheel-tracker-frontend:dev
}
else {
    # Production mode - build production images
    Write-Host "Building backend Docker image (PROD mode)..." -ForegroundColor Blue
    Set-Location backend
    docker build -t wheel-tracker-backend:latest .
    Set-Location ..

    Write-Host "Building frontend Docker image (PROD mode)..." -ForegroundColor Blue
    Set-Location frontend
    docker build -t wheel-tracker-frontend:latest .
    Set-Location ..

    # Run backend container on port 8000
    Write-Host "Starting backend container on port 8000 (PROD mode)..." -ForegroundColor Green
    docker run -d `
        --name wheel-tracker-backend `
        -p 8000:8000 `
        -v wheel-tracker-backend-data:/data `
        wheel-tracker-backend:latest

    # Run frontend container on port 3000
    Write-Host "Starting frontend container on port 3000 (PROD mode)..." -ForegroundColor Green
    docker run -d `
        --name wheel-tracker-frontend `
        -p 3000:3000 `
        wheel-tracker-frontend:latest
}

Write-Host ""
Write-Host "✅ Deployment complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Services are now running:"
Write-Host "  Backend:  http://localhost:8000" -ForegroundColor Blue
Write-Host "  Frontend: http://localhost:3000" -ForegroundColor Blue
Write-Host ""
if ($Profile -eq "dev") {
    Write-Host "Development mode:" -ForegroundColor Cyan
    Write-Host "  - Volumes are mounted for hot-reload"
    Write-Host "  - Changes to files will automatically refresh"
}
Write-Host ""
Write-Host "To view logs:"
Write-Host "  docker logs -f wheel-tracker-backend"
Write-Host "  docker logs -f wheel-tracker-frontend"
Write-Host ""
Write-Host "To stop containers:"
Write-Host "  docker stop wheel-tracker-backend wheel-tracker-frontend"
