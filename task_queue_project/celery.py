# -*- coding: utf-8 -*-
# هانا نستدعي الحاجات اللي بنحتاجها
from __future__ import absolute_import, unicode_literals # عشان التوافق مع بايثون 2 و 3 (احتياط)
import os # عشان نتعامل مع نظام التشغيل، زي تحديد متغيرات البيئة
from celery import Celery # نستدعي الكلاس الرئيسي حق Celery
from kombu import Exchange, Queue # نستدعي هذي عشان نعرف الـ exchanges والـ queues حق الرسائل لو حبينا نخصصها

# هانا بنقول لـ Celery وين يلاقي ملف الإعدادات حق جانغو
# بنحط متغير بيئة اسمه 'DJANGO_SETTINGS_MODULE' ونعطيه مسار ملف الإعدادات حقنا
# هذا مهم عشان Celery يقدر يوصل للمودلز والإعدادات حق جانغو
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'task_queue_project.settings')

# هانا بننشئ نسخة (instance) من تطبيق Celery
# بنعطيه اسم للمشروع ('task_queue_project')، هذا الاسم بيظهر في اللوجات وكذا
app = Celery('task_queue_project')

# هانا بنقول لتطبيق Celery إنه ياخذ إعداداته من ملف الإعدادات حق جانغو اللي حددناه فوق
# namespace='CELERY' يعني أي إعداد في ملف settings.py يبدأ بـ 'CELERY_' يعتبر إعداد خاص بـ Celery
# مثلاً CELERY_BROKER_URL، CELERY_RESULT_BACKEND ...الخ
app.config_from_object('django.conf:settings', namespace='CELERY')

# --- هذي الإعدادات ممكن تكون موجودة كمان في settings.py، بس بنأكد عليها هنا ---
# الحين بضبط كم مهمة تشتغل بنفس الوقت للعامل الواحد (worker concurrency)
# خليناها 4 يعني العامل الواحد يقدر يشغل 4 مهام مع بعض في نفس اللحظة
# app.conf.worker_concurrency = 4 # هذا الإعداد موجود في settings.py، يمكن ما نحتاج نكرره هنا

# كم مهمة يسحبها العامل مقدماً (prefetch multiplier)
# خليته 1 في settings.py، يعني يسحب مهمة واحدة بس زيادة ويخليها جاهزة
# لو خليناه 4 هنا، بيسحب 4 مهام زيادة لكل عامل (يعني لو concurrency=4، بيسحب 4*4=16 مهمة مقدماً!)
# الأفضل نخليه 1 عشان توزيع المهام يكون أحسن لو عندنا أكثر من عامل
# app.conf.worker_prefetch_multiplier = 1 # نستخدم القيمة من settings.py

# متى العامل يأكد إنه استلم المهمة (acks_late)
# خليناها True في settings.py، يعني يأكد بعد ما يخلص تنفيذها، وهذا أضمن
# app.conf.task_acks_late = True # نستخدم القيمة من settings.py

# هل نوقف تحديد المعدل (rate limits)؟
# لو خليناها True، العامل بيشتغل بأقصى سرعة ممكنة بدون قيود على عدد المهام في الثانية
# ممكن تكون مفيدة لو عندنا ضغط شغل كبير، بس ممكن تسبب ضغط على الموارد
# app.conf.worker_disable_rate_limits = True # ممكن نخليها False لو حبينا نتحكم بالمعدل

# --- تعريف الطوابير (Queues) والـ Exchanges (اختياري لو بنستخدم الطابور الافتراضي بس) ---
# الـ Exchange هو زي مكتب البريد اللي يستقبل الرسائل (المهام) ويوزعها على الطوابير
# الـ Queue هو الطابور اللي بتوقف فيه المهام تنتظر العامل يجي ياخذها
# default_exchange = Exchange('default', type='direct') # عرفنا exchange افتراضي اسمه default ونوعه direct (بيوجه الرسالة للطابور اللي الـ routing_key حقه مطابق)
# default_queue = Queue('default', default_exchange, routing_key='default') # عرفنا طابور افتراضي اسمه default مربوط بالـ exchange الافتراضي ومفتاح التوجيه حقه default

# نحدد قائمة الطوابير اللي بيستخدمها Celery
# لو ما عرفنا طوابير مخصصة، هو بيستخدم الطابور الافتراضي 'celery' عادةً
# بس بما إننا عرفنا default_queue فوق، بنقول له يستخدمه
# app.conf.task_queues = (default_queue,) # هذا بيخليه يستخدم الطابور اللي عرفناه

# نحدد الإعدادات الافتراضية للطابور والـ exchange ومفتاح التوجيه للمهام اللي ما تحدد لها شي خاص
# app.conf.task_default_queue = 'default' # الطابور الافتراضي
# app.conf.task_default_exchange = 'default' # الـ exchange الافتراضي
# app.conf.task_default_routing_key = 'default' # مفتاح التوجيه الافتراضي
# ملاحظة: الإعدادات هذي موجودة في settings.py، يمكن ما نحتاج نكررها هنا لو اعتمدنا على settings.py

# هذي أهم خطوة:
# بنقول لـ Celery روح دور على أي ملف اسمه tasks.py داخل كل تطبيق مسجل في INSTALLED_APPS حق جانغو
# وأي دالة معرفة بـ @shared_task أو @app.task اعتبرها مهمة تقدر تنفذها
app.autodiscover_tasks()

# ممكن نضيف هنا أي إعدادات إضافية لـ Celery لو احتجنا
# مثلاً، ممكن نربط إشارات (signals) معينة بأحداث Celery
# @app.on_after_configure.connect
# def setup_periodic_tasks(sender, **kwargs):
#     # هانا ممكن نضيف مهام مجدولة تشتغل بشكل دوري
#     sender.add_periodic_task(10.0, test.s('hello'), name='add every 10')

# دالة بسيطة للتجربة (ممكن نمسحها بعدين)
@app.task(bind=True)
def debug_task(self):
    # نطبع معلومات عن الطلب حق المهمة عشان نشوف كيف شكلها
    print(f'Request: {self.request!r}')
