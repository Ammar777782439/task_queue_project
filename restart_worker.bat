@echo off
echo Stopping any running Celery workers...
taskkill /f /im celery.exe 2>nul
echo.

echo Restarting Redis (if using Docker)...
docker-compose restart redis
echo.

echo Installing/updating dependencies...
pip install -r requirements.txt
echo.

echo Stopping any running Redis containers...
docker-compose stop redis
echo Starting Redis...
docker-compose up -d redis
echo Waiting for Redis to start...
timeout /t 5

echo Starting Celery worker with priority support and concurrency control...
echo Concurrency: 4 workers, 4 tasks per worker (total: 16 concurrent tasks)
echo.
echo IMPORTANT: Make sure Redis is running before starting the worker
echo.
celery -A task_queue_project worker --loglevel=debug -P solo --concurrency=4 --prefetch-multiplier=4
