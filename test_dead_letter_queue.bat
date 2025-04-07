@echo off
echo ===== اختبار آلية قائمة انتظار الرسائل الميتة (Dead Letter Queue) =====
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

echo 3. إنشاء مهمة اختبار ستفشل...
python manage.py test_dead_letter_queue
echo.

echo 4. التحقق من قائمة انتظار الرسائل الميتة...
python manage.py shell -c "from jobs.models import DeadLetterQueue; print(f'عدد المهام في قائمة انتظار الرسائل الميتة: {DeadLetterQueue.objects.count()}')"
echo.

echo ===== انتهى الاختبار =====
echo تحقق من سجلات Celery Worker وواجهة الإدارة لمزيد من التفاصيل.
