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

echo Starting Celery worker with priority support...
celery -A task_queue_project worker --loglevel=info -P solo -Q priority_10,priority_9,priority_8,priority_7,priority_6,priority_5,priority_4,priority_3,priority_2,priority_1,priority_0 --without-heartbeat --without-gossip --without-mingle
