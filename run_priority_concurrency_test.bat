@echo off
echo ===== اختبار الأولوية والتزامن =====
echo.

echo 1. التأكد من تشغيل Redis...
docker ps | findstr redis
if %ERRORLEVEL% NEQ 0 (
    echo Redis غير مشغل. جاري تشغيل Redis...
    docker-compose up -d redis
    timeout /t 5
)
echo.

echo 2. التأكد من تشغيل Celery Worker...
tasklist | findstr celery
if %ERRORLEVEL% NEQ 0 (
    echo Celery Worker غير مشغل. جاري تشغيل Celery Worker...
    start cmd /k "celery -A task_queue_project worker --loglevel=info -P gevent --concurrency=4 --prefetch-multiplier=1"
    timeout /t 5
)
echo.

echo 3. مسح المهام القديمة وإنشاء مهام اختبار جديدة...
python manage.py test_priority_concurrency --count=12 --sleep=15 --clear
echo.

echo 4. مراقبة حالة المهام...
echo سيتم عرض حالة المهام كل 5 ثوانٍ...
echo.

for /l %%i in (1, 1, 10) do (
    echo --- تحديث %%i ---
    python manage.py shell -c "from jobs.models import Job; print('\n'.join([f'المهمة: {j.task_name}, الحالة: {j.status}, الأولوية: {j.priority}' for j in Job.objects.all().order_by('-priority')]))"
    echo.
    timeout /t 5 > nul
)

echo ===== انتهى الاختبار =====
echo تحقق من سجلات Celery Worker لمزيد من التفاصيل.
