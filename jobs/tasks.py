
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
from .kafka_utils import send_success_message_to_kafka
# هانا نسوي لوجر خاص بنا عشان نسجل الأحداث
logger = logging.getLogger(__name__)

# هانا سوينا كلاس خاص للمهام عشان نعدل على حالة المهمة (Job)
class JobTask(Task):
    """كلاس خاص للمهام عشان نتحكم بحالة المهمة (Job) ونحدثها."""

    # هذي الدالة تحسب كم لازم تنتظر المهمة قبل ما تبدأ، على حسب أولويتها
    @staticmethod
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
            logger.warning(f" the task {job_id} not found in the database.")
            return 5

    # هاذي الداله يستدعيها السلري اذ فشلت المهمه بعد كل المحاولات
    def on_failure(self, exc, task_id, args, kwargs, einfo):

        """تتعامل مع فشل المهمة بعد ما استنفذت كل محاولات الإعادة."""

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
                logger.critical(f"Task  {job_id} ({job.task_name})  failed permanently after several attempts: {einfo}")

                # نرسل المهمة الفاشلة لقائمة المهام الميتة (Dead Letter Queue)

                send_to_dead_letter_queue.delay(job_id, str(exc), str(einfo))



            except Job.DoesNotExist:

                logger.error(f"Job {job_id} not found during final failure handling.")
                logger.critical(f"ALERT: Job {job_id} record not found during final failure handling. Error: {einfo}")
            except Exception as e:

                logger.error(f"Error during final failure handling for job {job_id}: {e}")







    # هذي الدالة تشتغل لما المهمة تحاول تعيد التنفيذ
    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """تتعامل مع إعادة محاولة تنفيذ المهمة."""
        # نأخذ الـ ID حق المهمة
        job_id = args[0] if args else None
        if job_id:
            try:

                job = Job.objects.get(pk=job_id)

                job.retry_count = self.request.retries

                job.error_message = f" Mission failed, try again ({self.request.retries + 1}/{self.max_retries}): {exc}"

                job.last_attempt_time = timezone.now()

                job.save(update_fields=['retry_count', 'error_message', 'last_attempt_time'])

                logger.warning(f"Retrying job {job_id} (Attempt {self.request.retries + 1}/{self.max_retries}): {exc}")
            except Job.DoesNotExist:
                 # لو ما لقينا المهمة نسجل خطأ
                 logger.error(f"Job {job_id} not found during retry handling.")
            except Exception as e:
                 # لو حصل أي خطأ ثاني أثناء معالجة الإعادة، نسجله
                 logger.error(f" Error processing task retry {job_id}: {e}")




# هانا نعرف المهمة الرئيسية اللي بتنفذ الشغل حقنا
# bind=True يعني المهمة بتقدر توصل لمعلومات عن نفسها (زي عدد المحاولات)
# base=JobTask يعني نستخدم الكلاس اللي سويناه فوق عشان نتحكم بالحالة
# autoretry_for=(Exception,) يعني لو حصل أي خطأ من نوع Exception، حاول تعيد التنفيذ تلقائ
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
    logger.info(f"the task {self.request.id} with job_id= {job_id} and sleep_time={sleep_time}")

    try:
        # ندور على المهمة بالـ ID حقها
        job = Job.objects.get(pk=job_id)
        # نسجل معلومات عن المهمة اللي بدأت
        logger.info(f"the task {job_id} ({job.task_name}) with priority  {job.priority}")

        # --- تسجيل وقت البدء (فقط في المحاولة الأولى) ---
        first_attempt = self.request.retries == 0
        if job.status == 'pending' and first_attempt and not job.started_at: # تأكد من أنه لم يتم تسجيله من قبل
            job.started_at = timezone.now() # <-- تسجيل وقت البدء

        # نحدث حالة المهمة لـ 'قيد التنفيذ' بس لو كانت 'معلقة' أو 'فشلت' (عشان إعادة المحاولة)
        if job.status in ['pending', 'failed']:
             job.status = 'in_progress'
             # نسجل وقت بدء المحاولة الحالية
             job.last_attempt_time = timezone.now()
             # نحدث عدد مرات الإعادة عند البدء أو الإعادة
             job.retry_count = self.request.retries
             # --- حفظ وقت البدء مع التحديثات الأخرى ---
             update_fields = ['status', 'last_attempt_time', 'retry_count']
             if job.started_at and first_attempt: # تأكد من حفظ started_at إذا تم تعيينه في هذه المحاولة
                 update_fields.append('started_at')
             job.save(update_fields=update_fields)

        # --- هانا نمثل الشغل حق المهمة ---


        # نغير هذا الجزء ب المحاكه الي نشتيها زي ارسال ايميلات وا انشاء تقارير وغيره
        print(f"The task is being executed {job_id}: {job.task_name} With priority {job.priority}...")

        logger.info(f"The task {job_id} ({job.task_name}) With priority {job.priority} She lies down for a while{sleep_time} Seconds")
        # ناخرها  شوية عشان نمثل إنها بتشتغل
        time.sleep(sleep_time)




        import random
        if random.random() < 0.1: # 90% chance of failure
            raise Exception("Random failure occurred during task execution.")

        # --- المهمة اكتملت ---
        job.status = 'completed'
        job.error_message = None
        # --- تسجيل وقت الانتهاء وحساب المدة ---
        job.completed_at = timezone.now() # <-- تسجيل وقت الانتهاء
        if job.started_at: # تأكد من وجود وقت بدء لحساب المدة
            job.execution_duration = job.completed_at - job.started_at # <-- حساب المدة
        # --- حفظ وقت الانتهاء والمدة مع التحديثات الأخرى ---
        update_fields = ['status', 'error_message', 'completed_at']
        if job.execution_duration: # تأكد من حفظ المدة إذا تم حسابها
            update_fields.append('execution_duration')
        job.save(update_fields=update_fields)

        # إرسال رسالة النجاح إلى Kafka
        logger.info(f"محاولة إرسال بيانات المهمة {job.id} إلى Kafka")
        try:
            # إعداد بيانات المهمة
            job_data = {
                'job_id': job.id,
                'task_name': job.task_name,
                'priority': job.priority,
                'execution_time': job.execution_duration.total_seconds() if job.execution_duration else None,
                'completed_at': job.completed_at.isoformat() if job.completed_at else None,
                'status': 'completed'
            }
            send_success_message_to_kafka(job_data)
            logger.info(f"تم إرسال بيانات المهمة {job.id} إلى Kafka بنجاح")
        except Exception as e:
            logger.error(f"فشل في إرسال بيانات المهمة {job.id} إلى Kafka: {e}")

        logger.info(f"The task {job_id} ({job.task_name}) completed successfully. Duration: {job.execution_duration}")

        return f" The task {job_id} ({job.task_name}) completed successfully. Duration: {job.execution_duration}"

    except Job.DoesNotExist:

        logger.error(f"The task {job_id} not found.")

        return f"The task {job_id} not found"
    except Exception as exc:

        logger.error(f"  Error processing task {job_id}: {exc}")

        raise



# مهمة لمراقبة اكتمال دفعة من المهام وبدء الدفعة التالية
@shared_task
def monitor_batch_completion(batch_job_ids, next_batch_job_ids=None, wait_time=60):
    """
    تراقب اكتمال دفعة من المهام وتبدأ الدفعة التالية بعد فترة انتظار محددة.

    Args:
        batch_job_ids: قائمة معرفات المهام في الدفعة الحالية
        next_batch_job_ids: قائمة معرفات المهام في الدفعة التالية
        wait_time: وقت الانتظار بالثواني بعد اكتمال الدفعة الحالية
    """
    logger.info(f"بدء مراقبة اكتمال الدفعة: {batch_job_ids}")

    if not batch_job_ids:
        logger.warning("لا توجد مهام في الدفعة الحالية للمراقبة")
        return "لا توجد مهام في الدفعة الحالية للمراقبة"

    # انتظار حتى تكتمل جميع مهام الدفعة الحالية
    all_completed = False
    max_wait_time = 3600  # ساعة واحدة كحد أقصى للانتظار
    start_time = time.time()

    while not all_completed and (time.time() - start_time) < max_wait_time:
        # التحقق من حالة جميع المهام في الدفعة
        jobs = Job.objects.filter(id__in=batch_job_ids)
        completed_count = jobs.filter(status__in=['completed', 'failed', 'permanently_failed']).count()

        if completed_count == len(batch_job_ids):
            all_completed = True
            logger.info(f"اكتملت جميع مهام الدفعة: {batch_job_ids}")
        else:
            # انتظار 5 ثواني قبل التحقق مرة أخرى
            logger.info(f"انتظار اكتمال المهام... {completed_count}/{len(batch_job_ids)} مكتملة")
            time.sleep(5)

    if not all_completed:
        logger.warning(f"انتهت مهلة انتظار اكتمال الدفعة بعد {max_wait_time} ثانية")
        return f"انتهت مهلة انتظار اكتمال الدفعة بعد {max_wait_time} ثانية"

    # انتظار فترة إضافية بعد اكتمال الدفعة
    if wait_time > 0:
        logger.info(f"انتظار {wait_time} ثانية قبل بدء الدفعة التالية")
        time.sleep(wait_time)

    # بدء الدفعة التالية إذا كانت موجودة
    if next_batch_job_ids:
        logger.info(f"بدء الدفعة التالية: {next_batch_job_ids}")

        # تحديث حالة المهام في الدفعة التالية إلى 'pending'
        Job.objects.filter(id__in=next_batch_job_ids).update(status='pending')

        # إرسال المهام إلى الطابور
        for job_id in next_batch_job_ids:
            job = Job.objects.get(id=job_id)
            process_job_task.apply_async(
                args=[job_id],
                kwargs={},
                priority=job.priority
            )

        return f"تم بدء الدفعة التالية: {next_batch_job_ids}"
    else:
        logger.info("لا توجد دفعة تالية للبدء")
        return "لا توجد دفعة تالية للبدء"

# لما المهمة تفشل بعد كل المحاولات، هذي المهمة بتخزنها في قاعدة البيانات
@shared_task
def send_to_dead_letter_queue(job_id, error, traceback):
    """
    تخزن المهام الفاشلة في قائمة المهام الميتة وترسل إشعارات.
    """
    try:

        job = Job.objects.get(pk=job_id)


        dlq_entry = DeadLetterQueue.objects.create(
            original_job=job,
            task_id=job_id,
            task_name=job.task_name,
            error_message=error,
            traceback=traceback,
            args=json.dumps([job_id]),
            kwargs=json.dumps({})
        )


        send_failure_notification.delay(dlq_entry.id)


        logger.info(f"The task {job_id} Added to the dead task list with ID  {dlq_entry.id}")
        return f"The task {job_id} added to the dead task list with ID {dlq_entry.id}"
    except Job.DoesNotExist:

        logger.error(f"The task  {job_id} not found.")
        return f"The task  {job_id} not found"
    except Exception as e:

        logger.error(f"Error while adding task{job_id} to the dead task list: {e}")
        return f"found: {e}"


# مهمة لإرسال إشعار (بريد إلكتروني) حول فشل المهمة
# قيد التطوير
@shared_task
def send_failure_notification(dlq_entry_id):
    """
    Sends a notification about a failed task.
    """
    try:

        dlq_entry = DeadLetterQueue.objects.get(pk=dlq_entry_id)


        if dlq_entry.notification_sent:
            logger.info(f"Notification already sent for record {dlq_entry_id} in Dead Letter Queue")
            return f"Notification already sent for record {dlq_entry_id}"


        subject = f"[ALERT] Task failed permanently: {dlq_entry.task_name}"
        message = f"""A task has failed permanently after several attempts:

        Task ID: {dlq_entry.task_id}
        Task Name: {dlq_entry.task_name}
        Error: {dlq_entry.error_message}
        Time: {dlq_entry.created_at}


        """


        admin_emails = getattr(settings, 'ADMIN_EMAILS', [])
        if admin_emails:
            try:
                send_mail(
                    subject, # Subject
                    message, # Message
                    settings.DEFAULT_FROM_EMAIL, # From default email
                    admin_emails, # To admin emails list
                    fail_silently=True, # If sending fails, don't raise an error in this task
                )
                logger.info(f"Email notification sent for failed task {dlq_entry.task_id} to {admin_emails}")
            except Exception as mail_exc:
                logger.error(f"Failed to send email notification for record {dlq_entry_id}: {mail_exc}")



        logger.critical(subject + "\n" + message)


        dlq_entry.notification_sent = True
        dlq_entry.save(update_fields=['notification_sent'])

        return f"Notification sent for record {dlq_entry_id}"
    except DeadLetterQueue.DoesNotExist:

        logger.error(f"Record {dlq_entry_id} not found in Dead Letter Queue when sending notification")
        return f"Record {dlq_entry_id} not found"
    except Exception as e:

        logger.error(f"Error while sending notification for record {dlq_entry_id}: {e}")
        return f"Error: {e}"


# مهمة لإعادة معالجة مهمة فاشلة من قائمة انتظار الرسائل المهملة
# تُستخدم عند الرغبة في إعادة محاولة مهمة فاشلة بعد مراجعة تفاصيلها في لوحة الإدارة
@shared_task
def reprocess_failed_task(dlq_entry_id):
    """
    Reprocesses a failed task from the Dead Letter Queue.
    """
    try:

        dlq_entry = DeadLetterQueue.objects.get(pk=dlq_entry_id)


        if dlq_entry.reprocessed:
            logger.info(f"Record {dlq_entry_id} has already been reprocessed.")
            return f"Record {dlq_entry_id} has already been reprocessed"


        job = dlq_entry.original_job
        if not job:
            logger.error(f"Original job not found for record {dlq_entry_id}")
            return f"Original job not found for record {dlq_entry_id}"


        job.status = 'pending'
        job.retry_count = 0
        job.error_message = None
        job.permanently_failed = False

        job.save(update_fields=['status', 'retry_count', 'error_message', 'permanently_failed'])


        process_job_task.apply_async(
            args=[job.id],
            kwargs={},
            countdown=JobTask.calculate_countdown(job.id),
        )


        dlq_entry.reprocessed = True
        dlq_entry.reprocessed_at = timezone.now()

        dlq_entry.save(update_fields=['reprocessed', 'reprocessed_at'])


        logger.info(f"Failed task from record {dlq_entry_id} has been reprocessed")
        return f"Record {dlq_entry_id} has been reprocessed"
    except DeadLetterQueue.DoesNotExist:

        logger.error(f"Record {dlq_entry_id} not found during reprocessing")
        return f"Record {dlq_entry_id} not found"
    except Exception as e:

        logger.error(f"Error while reprocessing record {dlq_entry_id}: {e}")
        return f"Error: {e}"

# مهمة خاصة لاختبار آلية معالجة الأعطال - فهي تفشل دائمًا.
# تُستخدم لمعرفة كيفية تعامل النظام مع الأعطال.
@shared_task(bind=True, base=JobTask, autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=600, retry_jitter=True, max_retries=3)

def test_failure_task(self, job_id):
    #طبعا هاذي اليه معالجه الفشل الثاننيه اضافيه
    """
    مهمة تفشل دائمًا في اختبار آلية التعامل مع الفشل.
    """

    logger.info(f"Started failure test task test_failure_task for job {job_id}")

    try:

        job = Job.objects.get(pk=job_id)


        if job.status in ['pending', 'failed']:
            job.status = 'in_progress'
            job.last_attempt_time = timezone.now()
            job.retry_count = self.request.retries
            job.save(update_fields=['status', 'last_attempt_time', 'retry_count'])


        logger.warning(f"Failure test task {job_id} is throwing an intentional error (Attempt {self.request.retries + 1}/{self.max_retries + 1})") # +1 because max_retries starts from 0
        raise ValueError(f"This is an intentional failure for testing job {job_id}")

    except Job.DoesNotExist:

        logger.error(f"Job {job_id} not found.")
        return f"Job {job_id} not found."
    except Exception as exc:

        logger.error(f"Expected error during failure test task test_failure_task for job {job_id}: {exc}")
        raise
