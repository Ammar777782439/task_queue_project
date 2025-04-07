# -*- coding: utf-8 -*-
# هانا نستدعي الحاجات اللي بنحتاجها
from django.shortcuts import render, redirect # عشان نعرض الصفحات ونوجه المستخدم لصفحات ثانية
from django.contrib import messages # عشان نعرض رسائل للمستخدم (زي رسائل النجاح أو الخطأ)
from .forms import CreateJobForm  # نستورد الفورم اللي سويناه عشان المستخدم يدخل بيانات المهمة الجديدة
from .models import Job  # نستورد الموديل (الجدول) حق المهام عشان نخزن فيه المهمة الجديدة
from .tasks import process_job_task  # نستورد المهمة حق Celery اللي بتنفذ الشغل الفعلي في الخلفية
import logging  # عشان نسجل أي شي يحصل (معلومات، أخطاء) في ملف اللوج
from django.utils import timezone  # عشان نتعامل مع الوقت والتاريخ، خصوصاً للجدولة
from django.db import models  # عشان نقدر نستخدم دوال قاعدة البيانات زي Max لحساب أعلى أولوية

# نسوي لوجر خاص بهذا الملف عشان نسجل الأحداث
logger = logging.getLogger(__name__)

# هذي الدالة (الفيو) هي اللي بتعرض صفحة إنشاء مهمة جديدة وبتستقبل البيانات من المستخدم
def create_job_view(request):
    # أول شي نشوف نوع الطلب اللي وصل للسيرفر
    # إذا كان POST، معناه المستخدم عبى الفورم وضغط زر الإرسال
    if request.method == 'POST':
        # نسوي نسخة من الفورم ونربطها بالبيانات اللي أرسلها المستخدم (request.POST)
        form = CreateJobForm(request.POST)
        # نتأكد إذا كانت البيانات اللي دخلها المستخدم صالحة حسب القواعد اللي حطيناها في الفورم
        if form.is_valid():
            # لو البيانات صالحة، ناخذها من الفورم النظيف (cleaned_data)
            task_name = form.cleaned_data['task_name'] # اسم المهمة
            priority = form.cleaned_data['priority'] # الأولوية
            max_retries = form.cleaned_data['max_retries'] # أقصى عدد محاولات
            # نحاول ناخذ وقت الجدولة، لو المستخدم ما دخله بيكون None
            scheduled_time_input = form.cleaned_data.get('scheduled_time')

            try:
                # قبل ما نضيف المهمة الجديدة، نشوف ايش أعلى أولوية موجودة حالياً للمهام اللي لسا ما خلصت
                # بنستخدم هذا عشان نحسب كم لازم تنتظر المهمة الجديدة قبل ما تبدأ (لو أولويتها أقل)
                # aggregate(max_priority=models.Max('priority')) بتجيب أعلى قيمة في حقل priority
                # ['max_priority'] ناخذ القيمة هذي
                # or 0 لو مافيش ولا مهمة، نعتبر أعلى أولوية صفر
                existing_max_priority = Job.objects.filter(status__in=['pending', 'in_progress']).aggregate(max_priority=models.Max('priority'))['max_priority'] or 0

                # دحين ننشئ سجل جديد للمهمة في قاعدة البيانات (جدول Job) بالبيانات اللي أخذناها
                job = Job.objects.create(
                    task_name=task_name,
                    priority=priority,
                    max_retries=max_retries,
                    status='pending',  # نخلي الحالة الافتراضية 'معلقة'
                    scheduled_time=scheduled_time_input # نحفظ وقت الجدولة لو المستخدم دخله
                )
                # نسجل في اللوج إننا أنشأنا المهمة بنجاح عن طريق الفورم
                logger.info(f"أنشأنا المهمة {job.id} عن طريق الفورم.")

                # نجهز الوسائط (arguments) اللي بنرسلها لمهمة Celery في الخلفية
                task_args = [job.id]  # أهم شي نرسل الـ ID حق المهمة اللي أنشأناها
                task_kwargs = {
                    # ممكن نضيف أي وسائط مفتاحية ثانية هنا لو احتجنا، مثلاً بيانات إضافية للمهمة
                    # 'extra_data': 'some value'
                }

                # نحسب كم ثانية لازم تنتظر المهمة قبل ما تبدأ (countdown)
                # الفكرة: نطرح أولوية المهمة الجديدة من أعلى أولوية موجودة
                # لو مهمتنا أولويتها عالية (نفس الأعلى أو أعلى)، الانتظار بيكون صفر
                # لو أولويتها أقل، بتنتظر الفرق بين الأولويات (بالثواني، ممكن نعدل المعادلة هذي بعدين)
                # max(0, ...) عشان نضمن إن الانتظار ما يكون بالسالب
                countdown = max(0, existing_max_priority - priority)

                # نجهز الخيارات اللي بنرسلها مع المهمة لـ Celery
                celery_options = {
                    'priority': priority,  # نحدد أولوية المهمة في طابور Celery (لو الوسيط يدعمها)
                    'retry_policy': { # سياسة إعادة المحاولة (هذي يمكن ما تشتغل مباشرة كذا، بس فكرة)
                        'max_retries': job.max_retries,  # كم مرة يحاول يعيدها لو فشلت
                    },
                    'countdown': countdown  # كم ثانية ينتظر قبل ما يبدأ (حسبناها فوق)
                }

                # دحين نشوف موضوع وقت الجدولة
                # إذا المستخدم حدد وقت جدولة (scheduled_time) وهذا الوقت لسا ما جاش (في المستقبل)
                if job.scheduled_time and job.scheduled_time > timezone.now():
                    # نستخدم خيار 'eta' حق Celery عشان نحدد متى بالضبط لازم تشتغل المهمة
                    celery_options['eta'] = job.scheduled_time
                    # ما نحتاج countdown لو استخدمنا eta
                    celery_options.pop('countdown', None) # نحذف countdown لو موجود
                    # نسجل في اللوج إننا بنجدول المهمة
                    logger.info(f"بنجدول المهمة {job.id} لوقت {job.scheduled_time}")
                    # نجهز رسالة النجاح للمستخدم نوضح فيها إنها اتجدولت
                    success_message = f'نجحنا في إنشاء وجدولة المهمة "{task_name}" (رقمها: {job.id}) لوقت {job.scheduled_time}.'
                else:
                    # لو المستخدم ما حدد وقت جدولة، أو حدد وقت قد فات
                    if job.scheduled_time: # لو حدد وقت قد فات
                        # نسجل تحذير في اللوج
                        logger.warning(f"وقت الجدولة للمهمة {job.id} ({job.scheduled_time}) قد فات. بنحطها في الطابور عشان تتنفذ على طول.")
                    else: # لو ما حدد وقت أصلاً
                        # نسجل معلومة في اللوج
                        logger.info(f"بنحط المهمة {job.id} في الطابور عشان تتنفذ على طول (بانتظار {countdown} ثواني حسب الأولوية).")
                    # نجهز رسالة النجاح للمستخدم نوضح فيها إنها دخلت الطابور على طول
                    success_message = f'نجحنا في إنشاء ووضع المهمة "{task_name}" (رقمها: {job.id}) في الطابور للتنفيذ الفوري (مع مراعاة الأولوية).'

                # آخر خطوة: نرسل المهمة لـ Celery عشان ينفذها في الخلفية
                # apply_async هي الطريقة اللي نرسل فيها المهمة مع الخيارات اللي جهزناها
                process_job_task.apply_async(
                    args=task_args, # الوسائط العادية
                    kwargs=task_kwargs, # الوسائط المفتاحية
                    **celery_options # باقي الخيارات (priority, eta أو countdown, retry_policy)
                )

                # نعرض رسالة النجاح اللي جهزناها للمستخدم فوق
                messages.success(request, success_message)
                # نوجه المستخدم لنفس الصفحة مرة ثانية (عشان الفورم يكون فاضي ويقدر يضيف مهمة ثانية)
                return redirect('create_job') # 'create_job' هو اسم الـ URL pattern حق هذي الصفحة

            except Exception as e:
                # لو حصل أي خطأ أثناء إنشاء السجل في قاعدة البيانات أو أثناء إرسال المهمة لـ Celery
                # نسجل الخطأ بالتفصيل في اللوج
                logger.error(f"خطأ أثناء إنشاء/إرسال المهمة من الفورم: {e}", exc_info=True) # exc_info=True يضيف تفاصيل الخطأ للوج
                # نعرض رسالة خطأ للمستخدم
                messages.error(request, f'فشلنا في إنشاء أو إرسال المهمة: {e}')
                # ما بنسوي redirect، بنخلي المستخدم في نفس الصفحة عشان يشوف الخطأ ويشوف البيانات اللي دخلها في الفورم

    # إذا كان الطلب مش POST (يعني GET، المستخدم فتح الصفحة أول مرة)
    else:
        # نسوي نسخة فاضية من الفورم عشان نعرضها للمستخدم
        form = CreateJobForm()

    # نجهز الـ context اللي بنرسله للقالب (template) حق HTML
    # بنرسل الفورم عشان القالب يقدر يعرضه
    context = {'form': form}
    # نعرض القالب 'jobs/create_job.html' ونرسل له الـ context
    return render(request, 'jobs/create_job.html', context)

# ممكن نضيف دوال (views) ثانية هنا لو احتجنا، مثلاً صفحة تعرض قائمة المهام وحالتها
