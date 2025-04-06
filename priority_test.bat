@echo off
echo ===== اختبار نظام الأولوية باستخدام التأخير العكسي =====
echo.

echo 1. مسح المهام القديمة...
python manage.py shell -c "from jobs.models import Job; Job.objects.all().delete()"
echo.

echo 2. إنشاء مهام اختبار بأولويات مختلفة...
python manage.py test_priority
echo.

echo 3. انتظر للمهام لتكتمل...
echo سيتم تنفيذ المهام بترتيب الأولوية بسبب التأخير العكسي
echo المهام ذات الأولوية الأعلى لها تأخير أقل
echo.

echo انتظار 15 ثانية...
timeout /t 15
echo.

echo 4. عرض حالة المهام...
python manage.py shell -c "from jobs.models import Job; print('\n'.join([f'المهمة: {j.task_name}, الحالة: {j.status}, الأولوية: {j.priority}' for j in Job.objects.filter(task_name__startswith='Priority Test').order_by('-priority')]))"
echo.

echo ===== انتهى الاختبار =====
echo تحقق من سجلات Celery Worker لمزيد من التفاصيل.
