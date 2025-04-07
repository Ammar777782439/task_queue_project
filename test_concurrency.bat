@echo off
echo ===== اختبار التحكم في التزامن =====
echo.

echo 0. التحقق من حالة Redis...
docker ps | findstr redis
echo.

echo 1. مسح المهام القديمة...
python manage.py shell -c "from jobs.models import Job; Job.objects.all().delete()"
echo.

echo 2. إنشاء 20 مهمة اختبار...
python manage.py create_test_jobs 20 --max_priority 10
echo.

echo 3. مراقبة تنفيذ المهام...
echo سيتم تنفيذ عدة مهام بشكل متزامن بناءً على إعدادات التزامن
echo.

echo انتظار 5 ثواني...
timeout /t 5
echo.

echo 4. عرض حالة المهام (الجولة الأولى)...
python manage.py shell -c "from jobs.models import Job; print('\n'.join([f'المهمة: {j.task_name}, الحالة: {j.status}, الأولوية: {j.priority}' for j in Job.objects.all().order_by('-priority')]))"
echo.

echo انتظار 10 ثواني إضافية...
timeout /t 10
echo.

echo 5. عرض حالة المهام (الجولة الثانية)...
python manage.py shell -c "from jobs.models import Job; print('\n'.join([f'المهمة: {j.task_name}, الحالة: {j.status}, الأولوية: {j.priority}' for j in Job.objects.all().order_by('-priority')]))"
echo.

echo ===== انتهى الاختبار =====
echo تحقق من سجلات Celery Worker لمزيد من التفاصيل.
