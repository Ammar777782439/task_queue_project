from __future__ import absolute_import, unicode_literals
import os
from celery import Celery
from kombu import Exchange, Queue

# هنا بحدد إعدادات Django عشان يعرف من وين يجيب الإعدادات
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'task_queue_project.settings')

# هنا بإنشئ كائن celery جديد وسميته task_queue_project
app = Celery('task_queue_project')

# بقول له يستخدم الإعدادات من ملف settings حق Django، وبحدد namespace عشان كل الإعدادات اللي تخص celery تبدأ بـ CELERY_
app.config_from_object('django.conf:settings', namespace='CELERY')

# الحين بضبط عدد المهام اللي تشتغل بنفس الوقت، هنا خليتها ٤ بالضبط
app.conf.worker_concurrency = 4  # يعني يشغل ٤ مهام مع بعض
app.conf.worker_prefetch_multiplier = 4  # هنا خليته ياخذ ٤ مهام مقدماً لكل عامل
app.conf.task_acks_late = True  # بقول له لا يأكد إنه خلص المهمة إلا بعد ما ينفذها فعلياً
app.conf.worker_disable_rate_limits = True  # أشل معدلات التحديد حق المهام عشان يكون أسرع

# الحين بعرف exchange و queue بشكل افتراضي
default_exchange = Exchange('default', type='direct')
default_queue = Queue('default', default_exchange, routing_key='default')

# بحدد الطوابير (queues) اللي celery بيستخدمها
app.conf.task_queues = (default_queue,)

# إعدادات افتراضية للطوابير والمسارات
app.conf.task_default_queue = 'default'
app.conf.task_default_exchange = 'default'
app.conf.task_default_routing_key = 'default'

# أخلي celery يكتشف المهام (tasks) تلقائي من كل التطبيقات المسجلة في Django
app.autodiscover_tasks()
