@echo off
echo Stopping any running Redis containers...
docker-compose stop redis
echo.

echo Starting Redis...
docker-compose up -d redis
echo.

echo Waiting for Redis to start...
timeout /t 5
echo.

echo Redis should now be running. Check with:
echo docker ps | findstr redis
