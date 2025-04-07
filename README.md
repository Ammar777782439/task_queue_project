# نظام قائمة المهام المتزامنة (Asynchronous Task Queue)

هذا المشروع يقدم نظام قائمة مهام متزامنة باستخدام Django وCelery وRedis وPostgreSQL.

## الميزات الرئيسية

* **حفظ المهام**: يتم تخزين المهام في قاعدة بيانات PostgreSQL.
* **آلية إعادة المحاولة**: يتم إعادة محاولة المهام الفاشلة تلقائيًا مع تأخير تصاعدي.
* **أولوية المهام**: يمكن تعيين أولويات للمهام (القيمة الأعلى = أولوية أعلى).
* **التحكم في التزامن**: يمكن تكوين عدد المهام المتزامنة (بالضبط 4 مهام متزامنة).
* **تتبع حالة المهام**: يتم تتبع حالة المهام (قيد الانتظار، قيد التنفيذ، مكتملة، فاشلة) في قاعدة البيانات.
* **معالجة الفشل**: المهام الفاشلة تنتقل إلى قائمة انتظار الرسائل الميتة (Dead Letter Queue) بعد استنفاد محاولات إعادة التنفيذ.
* **واجهة ويب**: واجهة بسيطة لإنشاء وجدولة مهام جديدة.

## متطلبات التشغيل

* Python 3.x
* PostgreSQL
* Redis (يمكن تشغيله باستخدام Docker)
* بيئة Python افتراضية (مثل `venv`)

## خطوات الإعداد

### 1. إنشاء وتفعيل بيئة Python افتراضية:

```bash
# إنشاء بيئة افتراضية
python -m venv venv

# تفعيل البيئة الافتراضية (Windows)
venv\Scripts\activate

# تفعيل البيئة الافتراضية (macOS/Linux)
# source venv/bin/activate
```

### 2. تثبيت المتطلبات:

```bash
pip install -r requirements.txt
```

### 3. تكوين قاعدة البيانات:

* تأكد من تشغيل خادم PostgreSQL.
* قم بإنشاء قاعدة بيانات باسم `task_queue_db` (أو قم بتحديث إعدادات قاعدة البيانات في `task_queue_project/settings.py`).

### 4. تطبيق ترحيلات قاعدة البيانات:

```bash
python manage.py migrate
```

### 5. إنشاء مستخدم مشرف (للوصول إلى واجهة الإدارة):

```bash
python manage.py createsuperuser
```

## تشغيل النظام

يجب تشغيل المكونات التالية، يفضل في نوافذ طرفية منفصلة:

### 1. تشغيل Redis:

```bash
# باستخدام Docker
docker-compose up -d redis
```

### 2. تشغيل Celery Worker:

```bash
# تشغيل Celery Worker مع دعم التزامن (بالضبط 4 مهام متزامنة)
celery -A task_queue_project worker --loglevel=info -P gevent --concurrency=4 --prefetch-multiplier=1
```

> **ملاحظة هامة**: يجب تثبيت gevent أولاً: `pip install gevent`

### 3. تشغيل خادم Django:

```bash
python manage.py runserver
```

## الوصول إلى التطبيق

* **واجهة الويب (إنشاء مهمة)**: `http://127.0.0.1:8000/jobs/create/`
* **واجهة الإدارة**: `http://127.0.0.1:8000/admin/` (قم بتسجيل الدخول باستخدام بيانات المستخدم المشرف)

## إنشاء المهام

### عبر واجهة الويب:

1. انتقل إلى `http://127.0.0.1:8000/jobs/create/`
2. املأ النموذج (يمكنك تعيين أولوية وعدد محاولات إعادة التنفيذ)
3. انقر على "إنشاء مهمة"

### عبر أمر الإدارة:

```bash
# إنشاء مهمة للتنفيذ الفوري
python manage.py test_priority_concurrency.py "مهمة فورية" --priority 5 --max_retries 2

### عبر واجهة الإدارة:

1. انتقل إلى `http://127.0.0.1:8000/admin/jobs/job/add/`
2. املأ النموذج وانقر على "حفظ"

## اختبار الميزات

### 1. اختبار الأولوية والتزامن:

```bash
# تشغيل اختبار الأولوية والتزامن
run_priority_concurrency_test.bat
```

أو يدويًا:

```bash
python manage.py test_priority_concurrency --count=12 --sleep=15 --clear
```

### 2. اختبار معالجة الفشل وقائمة انتظار الرسائل الميتة:

```bash
# تشغيل اختبار معالجة الفشل
test_dead_letter_queue.bat
```

أو يدويًا:

```bash
python manage.py test_dead_letter_queue
```

## معالجة الفشل وقائمة انتظار الرسائل الميتة

عندما تفشل مهمة بعد استنفاد جميع محاولات إعادة التنفيذ (الافتراضي: 3 محاولات)، يحدث ما يلي:

1. يتم تحديث حالة المهمة إلى "فاشلة" وتعيين علامة `permanently_failed` إلى `True`.
2. يتم إرسال المهمة إلى قائمة انتظار الرسائل الميتة (Dead Letter Queue).
3. يتم إرسال إشعار (سجل نقدي وبريد إلكتروني إذا تم تكوينه).

### إدارة المهام الفاشلة:

1. انتقل إلى `http://127.0.0.1:8000/admin/jobs/deadletterqueue/`
2. يمكنك:
   - عرض تفاصيل الخطأ
   - إعادة معالجة المهام الفاشلة
   - تمييز المهام كمحلولة
   - إرسال إشعارات يدويًا

## تجربة فشل المهام يدويًا:

1. انتقل إلى `http://127.0.0.1:8000/admin/jobs/job/`
2. حدد مهمة مكتملة
3. اختر "تحويل المهام المكتملة إلى فاشلة لاختبار Dead Letter Queue" من قائمة الإجراءات
4. انتظر بضع ثوانٍ
5. تحقق من قائمة انتظار الرسائل الميتة: `http://127.0.0.1:8000/admin/jobs/deadletterqueue/`

## المراقبة

* راقب سجلات Celery Worker للاطلاع على تفاصيل معالجة المهام.
* راقب حالة المهام عبر واجهة الإدارة (`/admin/jobs/job/`).
* راقب المهام الفاشلة عبر واجهة إدارة قائمة انتظار الرسائل الميتة (`/admin/jobs/deadletterqueue/`).

## ملفات توثيق إضافية

* **CONCURRENCY_CONTROL.md**: يشرح كيفية التحكم في التزامن وضمان معالجة بالضبط 4 مهام متزامنة.
* **FAILURE_HANDLING.md**: يشرح آليات معالجة المهام الفاشلة وقائمة انتظار الرسائل الميتة.
* **TESTING.md**: يشرح كيفية اختبار ميزات النظام المختلفة.

## استكشاف الأخطاء وإصلاحها

### مشكلة: المهام لا تنفذ بالتزامن

**الحل**: تأكد من تشغيل Celery Worker باستخدام gevent:

```bash
pip install gevent
celery -A task_queue_project worker --loglevel=info -P gevent --concurrency=4 --prefetch-multiplier=1
```

### مشكلة: المهام الفاشلة لا تضاف إلى قائمة انتظار الرسائل الميتة

**الحل**: تأكد من تطبيق آخر الترحيلات:

```bash
python manage.py migrate
```

### مشكلة: الإشعارات لا تُرسل

**الحل**: تحقق من إعدادات البريد الإلكتروني في `settings.py`:

```python
# Email settings for failure notifications
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.example.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'your-email@example.com'
EMAIL_HOST_PASSWORD = 'your-password'
DEFAULT_FROM_EMAIL = 'noreply@example.com'
ADMIN_EMAILS = ['admin@example.com']
```
