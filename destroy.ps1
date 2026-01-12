# PowerShell script to stop and remove Docker containers and optionally images
# This will destroy the wheel-tracker deployment

Write-Host "🗑️  Destroying wheel-tracker deployment..." -ForegroundColor Red

# Stop containers
Write-Host "Stopping containers..." -ForegroundColor Yellow
docker stop wheel-tracker-backend wheel-tracker-frontend 2>$null
if ($LASTEXITCODE -eq 0 -or $?) {
    Write-Host "  ✓ Stopped wheel-tracker-backend" -ForegroundColor Green
    Write-Host "  ✓ Stopped wheel-tracker-frontend" -ForegroundColor Green
} else {
    Write-Host "  ⚠ Some containers may not have been running" -ForegroundColor Yellow
}

# Remove containers
Write-Host "Removing containers..." -ForegroundColor Yellow
docker rm wheel-tracker-backend wheel-tracker-frontend 2>$null
if ($LASTEXITCODE -eq 0 -or $?) {
    Write-Host "  ✓ Removed wheel-tracker-backend" -ForegroundColor Green
    Write-Host "  ✓ Removed wheel-tracker-frontend" -ForegroundColor Green
} else {
    Write-Host "  ⚠ Some containers may not have existed" -ForegroundColor Yellow
}

# Ask if user wants to remove images
Write-Host ""
$removeImages = Read-Host "Do you want to remove Docker images as well? (y/N)"
if ($removeImages -eq 'y' -or $removeImages -eq 'Y') {
    Write-Host "Removing images..." -ForegroundColor Yellow
    docker rmi wheel-tracker-backend:latest wheel-tracker-frontend:latest 2>$null
    if ($LASTEXITCODE -eq 0 -or $?) {
        Write-Host "  ✓ Removed wheel-tracker-backend:latest" -ForegroundColor Green
        Write-Host "  ✓ Removed wheel-tracker-frontend:latest" -ForegroundColor Green
    } else {
        Write-Host "  ⚠ Some images may not have existed" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "✅ Destruction complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Containers have been stopped and removed."
if ($removeImages -eq 'y' -or $removeImages -eq 'Y') {
    Write-Host "Images have been removed."
} else {
    Write-Host "Images were preserved. Run deploy.ps1 again to rebuild."
}
