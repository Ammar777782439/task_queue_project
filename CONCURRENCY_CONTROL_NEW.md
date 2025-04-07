# التحكم في التزامن (Concurrency Control)

هذا الملف يشرح كيفية التحكم في عدد المهام التي يتم تنفيذها بشكل متزامن في مشروع قائمة المهام.

## نظرة عامة

التحكم في التزامن يسمح لك بتحديد عدد المهام التي يمكن معالجتها في وقت واحد. هذا مفيد لعدة أسباب:

1. **تحسين الأداء**: منع تحميل النظام بعدد كبير من المهام المتزامنة
2. **إدارة الموارد**: التحكم في استهلاك موارد النظام (CPU، الذاكرة، اتصالات قاعدة البيانات)
3. **تجنب الاختناقات**: منع حدوث اختناقات في الخدمات الخارجية أو قاعدة البيانات

## الإعدادات الحالية

حالياً، تم تكوين النظام للسماح بـ:

- **بالضبط 4 مهام متزامنة**: يمكن للنظام معالجة 4 مهام في وقت واحد بالضبط

لضمان معالجة بالضبط 4 مهام متزامنة، قمنا بتنفيذ عدة حلول:

## الحلول المتاحة لضمان 4 مهام متزامنة بالضبط

### 1. استخدام gevent (الحل الموصى به)

gevent هو مكتبة تسمح بالتزامن في Python باستخدام greenlets، وهي أخف وزناً من العمليات الكاملة.

```bash
# تثبيت gevent
pip install gevent

# تشغيل Celery Worker مع gevent
celery -A task_queue_project worker --loglevel=info -P gevent --concurrency=4 --prefetch-multiplier=1
```

يمكنك استخدام الملف النصي المرفق:
```
start_worker_gevent.bat
```

### 2. استخدام eventlet (حل بديل)

eventlet هو مكتبة أخرى للتزامن في Python.

```bash
# تثبيت eventlet
pip install eventlet

# تشغيل Celery Worker مع eventlet
celery -A task_queue_project worker --loglevel=info -P eventlet --concurrency=4 --prefetch-multiplier=1
```

يمكنك استخدام الملف النصي المرفق:
```
start_worker_eventlet.bat
```

### 3. تشغيل 4 عمال Celery منفصلين (حل بديل آخر)

يمكنك تشغيل 4 عمال Celery منفصلين، كل منهم يعالج مهمة واحدة في كل مرة.

```bash
# تشغيل 4 عمال Celery منفصلين
start cmd /k "celery -A task_queue_project worker --loglevel=info -P solo --concurrency=1 --prefetch-multiplier=1 -n worker1@%COMPUTERNAME%"
start cmd /k "celery -A task_queue_project worker --loglevel=info -P solo --concurrency=1 --prefetch-multiplier=1 -n worker2@%COMPUTERNAME%"
start cmd /k "celery -A task_queue_project worker --loglevel=info -P solo --concurrency=1 --prefetch-multiplier=1 -n worker3@%COMPUTERNAME%"
start cmd /k "celery -A task_queue_project worker --loglevel=info -P solo --concurrency=1 --prefetch-multiplier=1 -n worker4@%COMPUTERNAME%"
```

يمكنك استخدام الملف النصي المرفق:
```
start_4_workers.bat
```

## إعدادات التكوين المهمة

لضمان معالجة بالضبط 4 مهام متزامنة، قمنا بتكوين الإعدادات التالية:

### في ملف settings.py:

```python
# Concurrency control settings
CELERY_WORKER_CONCURRENCY = 4  # Exactly 4 concurrent tasks
CELERY_WORKER_PREFETCH_MULTIPLIER = 1  # Only prefetch one task at a time
CELERY_TASK_ACKS_LATE = True  # Acknowledge tasks after they are executed
```

### في ملف celery.py:

```python
# Configure concurrency settings for exactly 4 concurrent tasks
app.conf.worker_concurrency = 4  # Exactly 4 concurrent tasks
app.conf.worker_prefetch_multiplier = 1  # Only prefetch one task at a time
app.conf.task_acks_late = True  # Acknowledge tasks after they are executed
app.conf.worker_disable_rate_limits = True
```

## اختبار إعدادات التزامن

يمكنك اختبار إعدادات التزامن من خلال إنشاء عدة مهام وملاحظة كيف يتم تنفيذها:

1. **تشغيل Redis**:
   ```
   start_redis.bat
   ```

2. **تشغيل Celery Worker**:
   ```
   start_worker_gevent.bat
   ```
   أو
   ```
   start_worker_eventlet.bat
   ```
   أو
   ```
   start_4_workers.bat
   ```

3. **إنشاء مهام اختبار**:
   ```
   create_jobs.bat
   ```

4. **مراقبة تنفيذ المهام**:
   - راقب سجلات العامل لمعرفة كيف يتم تنفيذ المهام
   - تحقق من حالة المهام في واجهة الإدارة

## ملاحظات هامة

1. **prefetch_multiplier=1**: هذا الإعداد مهم جداً لضمان أن كل عامل يسحب مهمة واحدة فقط في كل مرة.

2. **task_acks_late=True**: هذا الإعداد يضمن أن المهام يتم الاعتراف بها فقط بعد تنفيذها، وليس عند استلامها.

3. **gevent أو eventlet**: استخدام gevent أو eventlet يسمح بالتزامن في عملية واحدة، وهو أكثر كفاءة من استخدام عمليات متعددة.

4. **4 عمال منفصلين**: هذا الحل يضمن بالضبط 4 مهام متزامنة، ولكنه يستهلك المزيد من الموارد.
