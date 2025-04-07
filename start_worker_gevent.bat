@echo off
echo Installing gevent...
pip install gevent
echo.

echo Starting Celery worker with EXACTLY 4 concurrent tasks...
echo.

echo IMPORTANT: Make sure Redis is running before starting the worker
echo.

celery -A task_queue_project worker --loglevel=info -P gevent --concurrency=4 --prefetch-multiplier=1 --without-heartbeat --without-gossip --without-mingle
