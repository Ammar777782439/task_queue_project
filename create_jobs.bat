@echo off
echo Creating test jobs...
echo.

echo 1. Clearing existing jobs...
python manage.py shell -c "from jobs.models import Job; Job.objects.all().delete()"
echo.

echo 2. Creating 10 test jobs with different priorities...
python manage.py create_test_jobs 10 --max_priority 10
echo.

echo 3. Jobs created. Check the worker logs to see them being processed.
echo.

echo 4. Current job status:
python manage.py shell -c "from jobs.models import Job; print('\n'.join([f'Job: {j.task_name}, Status: {j.status}, Priority: {j.priority}' for j in Job.objects.all().order_by('-priority')]))"
