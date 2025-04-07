@echo off
echo Starting Celery worker with priority support and concurrency control...
echo Concurrency: 4 workers, 4 tasks per worker (total: 16 concurrent tasks)
echo.

echo IMPORTANT: Make sure Redis is running before starting the worker
echo.

celery -A task_queue_project worker --loglevel=debug -P solo --concurrency=4 --prefetch-multiplier=4
