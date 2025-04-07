
# هانا نستدعي الحاجات اللي نشتيها من المكتبات
from __future__ import absolute_import, unicode_literals
import time  
import json
from celery import shared_task, Task 
from celery.signals import task_failure 
from .models import Job, DeadLetterQueue 
from django.utils import timezone 
import logging
from django.core.mail import send_mail
from django.conf import settings 
from django.db import models

# هانا نسوي لوجر خاص بنا عشان نسجل الأحداث
logger = logging.getLogger(__name__)

# هانا سوينا كلاس خاص للمهام عشان نعدل على حالة المهمة (Job)
class JobTask(Task):
    """كلاس خاص للمهام عشان نتحكم بحالة المهمة (Job) ونحدثها."""

    # هذي الدالة تحسب كم لازم تنتظر المهمة قبل ما تبدأ، على حسب أولويتها
    def calculate_countdown(job_id):
        """
        تحسب كم وقت الانتظار (بالثواني) للمهمة قبل ما تبدأ.
        كلما زادت الأولوية (رقم أكبر)، قل وقت الانتظار.
        """
        try:
            # ندور على المهمة بالـ ID حقها
            job = Job.objects.get(id=job_id)
            # نشوف ايش أعلى أولوية موجودة معانا في قاعدة البيانات للمهام اللي لسا ما خلصت
            existing_max_priority = Job.objects.filter(status__in=['pending', 'in_progress']).aggregate(max_priority=models.Max('priority'))['max_priority'] or 0
            # نحسب وقت الانتظار: نطرح أولوية المهمة الحالية من أعلى أولوية. لو طلعت سالب، نخليها صفر.
            # يعني لو مهمة أولويتها هي الأعلى، بتبدأ على طول (صفر انتظار).
            countdown = max(0, existing_max_priority - job.priority)
            # نرجع وقت الانتظار
            return countdown
        except Job.DoesNotExist:
            # لو ما لقينا المهمة، نرجع قيمة افتراضية (مثلاً 5 ثواني)
            logger.warning(f"المهمة رقم {job_id} مش موجودة لما جينا نحسب وقت الانتظار.")
            return 5

    # هذي الدالة تشتغل لما المهمة تفشل فشل نهائي بعد كل المحاولات
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """تتعامل مع فشل المهمة بعد ما استنفذت كل محاولات الإعادة."""
        # نأخذ الـ ID حق المهمة من الوسائط (arguments)
        job_id = args[0] if args else None
        if job_id:
            try:
                # ندور على المهمة في قاعدة البيانات
                job = Job.objects.get(pk=job_id)
                # نغير حالتها لـ "فشلت"
                job.status = 'failed'
                # نسجل رسالة الخطأ اللي حصل
                job.error_message = f"المهمة فشلت بعد كل المحاولات: {einfo}"
                # نسجل وقت آخر محاولة فاشلة
                job.last_attempt_time = timezone.now()
                # نعلم عليها إنها فشلت فشل نهائي
                job.permanently_failed = True
                # نحفظ التغييرات هذي بس (status, error_message, last_attempt_time, permanently_failed)
                job.save(update_fields=['status', 'error_message', 'last_attempt_time', 'permanently_failed'])

                # نسجل تحذير خطير (critical) في اللوج
                logger.critical(f"تنبيه: المهمة {job_id} ({job.task_name}) فشلت بشكل نهائي بعد كل المحاولات. الخطأ: {einfo}")

                # نرسل المهمة الفاشلة لقائمة المهام الميتة (Dead Letter Queue)
                
                send_to_dead_letter_queue.delay(job_id, str(exc), str(einfo))

                
                # دالة on_failure تشتغل بس بعد ما تخلص كل المحاولات

            except Job.DoesNotExist:
                # لو ما لقينا المهمة نسجل خطأ
                logger.error(f"المهمة {job_id} ما لقيناها وقت معالجة الفشل النهائي.")
                logger.critical(f"تنبيه: سجل المهمة {job_id} مش موجود وقت معالجة الفشل النهائي. الخطأ: {einfo}")
            except Exception as e:
                # لو حصل أي خطأ ثاني أثناء معالجة الفشل، نسجله
                logger.error(f"خطأ أثناء معالجة الفشل النهائي للمهمة {job_id}: {e}")







    # هذي الدالة تشتغل لما المهمة تحاول تعيد التنفيذ
    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """تتعامل مع إعادة محاولة تنفيذ المهمة."""
        # نأخذ الـ ID حق المهمة
        job_id = args[0] if args else None
        if job_id:
            try:
                # ندور على المهمة
                job = Job.objects.get(pk=job_id)
                # نحدث عدد مرات الإعادة
                job.retry_count = self.request.retries
                # نسجل رسالة الخطأ ونوضح إنها محاولة إعادة
                job.error_message = f"المهمة فشلت، بنحاول مرة ثانية ({self.request.retries + 1}/{self.max_retries}): {exc}"
                # نسجل وقت المحاولة هذي
                job.last_attempt_time = timezone.now()
                # نحفظ التغييرات (retry_count, error_message, last_attempt_time)
                job.save(update_fields=['retry_count', 'error_message', 'last_attempt_time'])
                # نسجل تحذير في اللوج عن إعادة المحاولة
                logger.warning(f"بنعيد محاولة المهمة {job_id} (المحاولة {self.request.retries + 1}/{self.max_retries}): {exc}")
            except Job.DoesNotExist:
                 # لو ما لقينا المهمة نسجل خطأ
                 logger.error(f"المهمة {job_id} ما لقيناها وقت معالجة إعادة المحاولة.")
            except Exception as e:
                 # لو حصل أي خطأ ثاني أثناء معالجة الإعادة، نسجله
                 logger.error(f"خطأ أثناء معالجة إعادة المحاولة للمهمة {job_id}: {e}")




# هانا نعرف المهمة الرئيسية اللي بتنفذ الشغل حقنا
# bind=True يعني المهمة بتقدر توصل لمعلومات عن نفسها (زي عدد المحاولات)
# base=JobTask يعني نستخدم الكلاس اللي سويناه فوق عشان نتحكم بالحالة
# autoretry_for=(Exception,) يعني لو حصل أي خطأ من نوع Exception، حاول تعيد التنفيذ تلقائياً
# retry_backoff=True يعني زيد وقت الانتظار بين كل محاولة فاشلة
# retry_backoff_max=600 يعني أقصى وقت انتظار بين المحاولات هو 600 ثانية (10 دقايق)
# retry_jitter=True يعني ضيف شوية عشوائية لوقت الانتظار عشان ما تبدأ كل المهام الفاشلة بنفس الوقت
# max_retries=3 يعني أقصى عدد محاولات هو 3 مرات
@shared_task(bind=True, base=JobTask, autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=600, retry_jitter=True, max_retries=3)
def process_job_task(self, job_id, sleep_time=10):
    """
    تنفذ المهمة اللي معرفة بالـ job_id حقها، وتدعم الأولويات.
    المهام اللي أولويتها أعلى بتشتغل قبل.

    الوسائط (Args):
        job_id: الـ ID حق المهمة اللي نشتي ننفذها.
        sleep_time: كم ثواني ترقد المهمة عشان نمثل إنها بتشتغل (الافتراضي 10 ثواني).
    """
    # نسجل في اللوج إن المهمة بدأت
    logger.info(f"المهمة {self.request.id} بدأت بالـ job_id={job_id} و sleep_time={sleep_time}")

    try:
        # ندور على المهمة بالـ ID حقها
        job = Job.objects.get(pk=job_id)
        # نسجل معلومات عن المهمة اللي بدأت
        logger.info(f"بدأنا المهمة {job_id} ({job.task_name}) بأولوية {job.priority}")

        # نحدث حالة المهمة لـ 'قيد التنفيذ' بس لو كانت 'معلقة' أو 'فشلت' (عشان إعادة المحاولة)
        if job.status in ['pending', 'failed']:
             job.status = 'in_progress'
             # نسجل وقت بدء المحاولة الحالية
             job.last_attempt_time = timezone.now()
             # نحدث عدد مرات الإعادة عند البدء أو الإعادة
             job.retry_count = self.request.retries
             # نحفظ التغييرات (status, last_attempt_time, retry_count)
             job.save(update_fields=['status', 'last_attempt_time', 'retry_count'])

        # --- هانا نمثل الشغل حق المهمة ---
        # غير هذا الجزء بالشغل الحقيقي اللي تسويه المهمة (زي إرسال إيميل، إنشاء تقرير...)
        print(f"جاري تنفيذ المهمة {job_id}: {job.task_name} بأولوية {job.priority}...")
        logger.info(f"المهمة {job_id} ({job.task_name}) بأولوية {job.priority} بترقد لمدة {sleep_time} ثواني")
        # نخليها ترقد شوية عشان نمثل إنها بتشتغل
        time.sleep(sleep_time)

        # مثال: نمثل احتمال فشل المهمة عشان نجرب (الكود الأصلي - علقنا عليه الآن)
        # import random
        # if random.random() < 0.6: # احتمال 60% إنها تفشل
        #     raise ValueError(f"خطأ محاكاة للمهمة {job_id}")

        # --- المهمة اكتملت ---
        # نغير حالة المهمة لـ 'اكتملت'
        job.status = 'completed'
        # نمسح رسالة الخطأ لو كانت موجودة لأنها نجحت
        job.error_message = None
        # نحفظ التغييرات (status, error_message)
        job.save(update_fields=['status', 'error_message'])
        # نسجل في اللوج إن المهمة خلصت بنجاح
        logger.info(f"المهمة {job_id} ({job.task_name}) اكتملت بنجاح.")
        # نرجع رسالة تأكيد
        return f"المهمة {job_id} اكتملت بنجاح."

    except Job.DoesNotExist:
        # لو ما لقينا المهمة، نسجل خطأ
        logger.error(f"المهمة {job_id} ما لقيناها.")
        # ما نعيد المحاولة لو المهمة مش موجودة أصلاً
        return f"المهمة {job_id} ما لقيناها."
    except Exception as exc:
        # لو حصل أي خطأ ثاني أثناء التنفيذ
        logger.error(f"حصل خطأ أثناء تنفيذ المهمة {job_id}: {exc}")
        
        raise 


# هذي مهمة عشان نرسل المهام الفاشلة لقائمة المهام الميتة (Dead Letter Queue)
# لما المهمة تفشل بعد كل المحاولات، هذي المهمة بتخزنها في قاعدة البيانات
@shared_task
def send_to_dead_letter_queue(job_id, error, traceback):
    """
    تخزن المهام الفاشلة في قائمة المهام الميتة وترسل إشعارات.
    """
    try:
        # نجيب المهمة الأصلية
        job = Job.objects.get(pk=job_id)

        # نسوي سجل جديد في قائمة المهام الميتة
        dlq_entry = DeadLetterQueue.objects.create(
            original_job=job, # نربطها بالمهمة الأصلية
            task_id=job_id,  # نستخدم job_id كـ task_id للتبسيط
            task_name=job.task_name, # اسم المهمة
            error_message=error, # رسالة الخطأ
            traceback=traceback, # تفاصيل الخطأ (traceback)
            args=json.dumps([job_id]), # الوسائط اللي استخدمتها المهمة (نحولها لـ JSON)
            kwargs=json.dumps({}) # الوسائط المفتاحية (نحولها لـ JSON)
        )

        # نرسل إشعار بالفشل
        send_failure_notification.delay(dlq_entry.id)

        # نسجل في اللوج إن المهمة انضافت للقائمة الميتة
        logger.info(f"المهمة {job_id} انضافت لقائمة المهام الميتة بالـ ID {dlq_entry.id}")
        return f"المهمة {job_id} انضافت لقائمة المهام الميتة"
    except Job.DoesNotExist:
        # لو ما لقينا المهمة الأصلية
        logger.error(f"المهمة {job_id} ما لقيناها وقت إضافتها لقائمة المهام الميتة")
        return f"المهمة {job_id} ما لقيناها"
    except Exception as e:
        # لو حصل أي خطأ ثاني
        logger.error(f"خطأ أثناء إضافة المهمة {job_id} لقائمة المهام الميتة: {e}")
        return f"خطأ: {e}"


# هذي مهمة عشان نرسل إشعار (إيميل مثلاً) عن مهمة فشلت
# قيد التطوير ما اكتملت
@shared_task
def send_failure_notification(dlq_entry_id):
    """
    ترسل إشعار عن مهمة فشلت.
    """
    try:
        # نجيب السجل حق المهمة الفاشلة من القائمة الميتة
        dlq_entry = DeadLetterQueue.objects.get(pk=dlq_entry_id)

        # نتأكد إن الإشعار ما قد اترسل من قبل
        if dlq_entry.notification_sent:
            logger.info(f"الإشعار قد اترسل من قبل للسجل {dlq_entry_id} في القائمة الميتة")
            return f"الإشعار قد اترسل من قبل للسجل {dlq_entry_id}"

        # نجهز رسالة الإشعار
        subject = f"[تنبيه] مهمة فشلت بشكل نهائي: {dlq_entry.task_name}"
        message = f"""في مهمة فشلت بشكل نهائي بعد عدة محاولات:

        رقم المهمة (Task ID): {dlq_entry.task_id}
        اسم المهمة: {dlq_entry.task_name}
        الخطأ: {dlq_entry.error_message}
        الوقت: {dlq_entry.created_at}

        لو سمحت شوف لوحة التحكم حق الإدارة عشان تشوف تفاصيل أكثر وتقدر تعيد تشغيل المهمة لو تشتي.
        """

        # نرسل إيميل للمدراء لو إيميلاتهم موجودة في الإعدادات
        admin_emails = getattr(settings, 'ADMIN_EMAILS', [])
        if admin_emails:
            try:
                send_mail(
                    subject, # الموضوع
                    message, # الرسالة
                    settings.DEFAULT_FROM_EMAIL, # من الإيميل الافتراضي
                    admin_emails, # لمين نرسل (قائمة إيميلات المدراء)
                    fail_silently=True, # لو فشل الإرسال، ما يسبب خطأ في المهمة هذي
                )
                logger.info(f"تم إرسال إشعار إيميل عن المهمة الفاشلة {dlq_entry.task_id} إلى {admin_emails}")
            except Exception as mail_exc:
                logger.error(f"فشل إرسال إيميل الإشعار للسجل {dlq_entry_id}: {mail_exc}")


        # نسجل الإشعار في اللوج كتحذير خطير
        logger.critical(subject + "\n" + message)

        # نعلم على السجل إن الإشعار اترسل
        dlq_entry.notification_sent = True
        dlq_entry.save(update_fields=['notification_sent'])

        return f"تم إرسال الإشعار للسجل {dlq_entry_id}"
    except DeadLetterQueue.DoesNotExist:
        # لو ما لقينا السجل حق القائمة الميتة
        logger.error(f"السجل {dlq_entry_id} مش موجود في القائمة الميتة وقت إرسال الإشعار")
        return f"السجل {dlq_entry_id} مش موجود"
    except Exception as e:
        # لو حصل أي خطأ ثاني
        logger.error(f"خطأ أثناء إرسال الإشعار للسجل {dlq_entry_id}: {e}")
        return f"خطأ: {e}"


# هذي مهمة عشان نعيد تشغيل مهمة فشلت من القائمة الميتة
# نستخدمها لما نحب نعيد تشغيل مهمة فشلت بعد ما نشوف تفاصيلها في لوحة التحكم
@shared_task
def reprocess_failed_task(dlq_entry_id):
    """
    تعيد تشغيل مهمة فشلت من قائمة المهام الميتة.
    """
    try:
        # نجيب السجل حق المهمة الفاشلة
        dlq_entry = DeadLetterQueue.objects.get(pk=dlq_entry_id)

        # نتأكد إنها ما قد أعيد تشغيلها من قبل
        if dlq_entry.reprocessed:
            logger.info(f"السجل {dlq_entry_id} قد أعيد تشغيله من قبل.")
            return f"السجل {dlq_entry_id} قد أعيد تشغيله من قبل"

        # نجيب المهمة الأصلية المرتبطة بهذا السجل
        job = dlq_entry.original_job
        if not job:
            logger.error(f"المهمة الأصلية مش موجودة للسجل {dlq_entry_id}")
            return f"المهمة الأصلية مش موجودة للسجل {dlq_entry_id}"

        # نرجع حالة المهمة الأصلية لوضع البداية
        job.status = 'pending' # نخليها معلقة
        job.retry_count = 0 # نصفر عداد المحاولات
        job.error_message = None # نمسح رسالة الخطأ
        job.permanently_failed = False # نشيل علامة الفشل النهائي
        # نحفظ التغييرات هذي بس
        job.save(update_fields=['status', 'retry_count', 'error_message', 'permanently_failed'])

        # نرجع نحط المهمة في الطابور عشان تتنفذ من جديد
        process_job_task.apply_async(
            args=[job.id], # نرسل الـ ID حقها
            kwargs={}, # مافيش وسائط مفتاحية
            countdown=0 # تبدأ على طول بدون انتظار
        )

        # نعلم على السجل إنه أعيد تشغيله
        dlq_entry.reprocessed = True
        dlq_entry.reprocessed_at = timezone.now() # نسجل وقت الإعادة
        # نحفظ التغييرات هذي بس
        dlq_entry.save(update_fields=['reprocessed', 'reprocessed_at'])

        # نسجل في اللوج إن المهمة أعيد تشغيلها
        logger.info(f"تمت إعادة تشغيل المهمة الفاشلة من السجل {dlq_entry_id}")
        return f"تمت إعادة تشغيل السجل {dlq_entry_id}"
    except DeadLetterQueue.DoesNotExist:
        # لو ما لقينا السجل
        logger.error(f"السجل {dlq_entry_id} مش موجود وقت إعادة التشغيل")
        return f"السجل {dlq_entry_id} مش موجود"
    except Exception as e:
        # لو حصل أي خطأ ثاني
        logger.error(f"خطأ أثناء إعادة تشغيل السجل {dlq_entry_id}: {e}")
        return f"خطأ: {e}"


# هذي مهمة خاصة بس عشان نجرب آلية معالجة الفشل، يعني دايماً بتفشل
# نستخدمها عشان نشوف كيف النظام يتعامل مع الفشل
@shared_task(bind=True, base=JobTask, autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=600, retry_jitter=True, max_retries=4) # زدنا عدد المحاولات هنا لـ 4 عشان نشوفها وهي تفشل أكثر
def test_failure_task(self, job_id):
    """
    مهمة تفشل دائمًا عشان نختبر آلية معالجة الفشل.
    """
    # نسجل إن مهمة الاختبار بدأت
    logger.info(f"بدأت مهمة اختبار الفشل test_failure_task للمهمة {job_id}")

    try:
        # نجيب المهمة
        job = Job.objects.get(pk=job_id)

        # نحدث حالتها لـ 'قيد التنفيذ' لو كانت 'معلقة' أو 'فشلت'
        if job.status in ['pending', 'failed']:
            job.status = 'in_progress'
            job.last_attempt_time = timezone.now()
            job.retry_count = self.request.retries
            job.save(update_fields=['status', 'last_attempt_time', 'retry_count'])

        # دايماً نرمي خطأ عشان نجرب الفشل
        logger.warning(f"مهمة اختبار الفشل {job_id} بترمي خطأ مقصود (المحاولة {self.request.retries + 1}/{self.max_retries + 1})") # +1 عشان max_retries يبدأ من 0
        raise ValueError(f"هذا فشل مقصود للاختبار للمهمة {job_id}")

    except Job.DoesNotExist:
        # لو ما لقينا المهمة
        logger.error(f"المهمة {job_id} ما لقيناها.")
        return f"المهمة {job_id} ما لقيناها."
    except Exception as exc:
        # لو حصل أي خطأ (وهو المتوقع هنا)
        logger.error(f"حصل خطأ متوقع أثناء مهمة اختبار الفشل test_failure_task للمهمة {job_id}: {exc}")
        raise  # نعيد رمي الخطأ عشان Celery يتعامل مع الإعادة أو الفشل النهائي
