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

logger = logging.getLogger(__name__)

class JobTask(Task):
    """Custom Task class to handle Job status updates."""
    # داله لحساب الاولويه المهام
    def calculate_countdown(job_id):
        try:
            job = Job.objects.get(id=job_id)
            # احصل على أعلى أولوية موجودة في قاعدة البيانات
            existing_max_priority = Job.objects.aggregate(max_priority=models.Max('priority'))['max_priority'] or 0
            # حساب العد التنازلي بناءً على الأولوية
            countdown = max(0, existing_max_priority - job.priority)
            return countdown
        except Job.DoesNotExist:
            return 5  # قيمة افتراضية لو المهمة مش موجودة

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Handle task failure after all retries."""
        job_id = args[0] if args else None
        if job_id:
            try:
                job = Job.objects.get(pk=job_id)
                job.status = 'failed'
                job.error_message = f"Task failed after retries: {einfo}"
                job.last_attempt_time = timezone.now()
                job.permanently_failed = True  # Set the flag for permanent failure
                job.save(update_fields=['status', 'error_message', 'last_attempt_time', 'permanently_failed'])

                # Log critical error
                logger.critical(f"ALERT: Job {job_id} ({job.task_name}) has failed permanently after all retries. Error: {einfo}")

                # Send the failed task to the dead letter queue
                # هذا يجب أن يتم قبل استدعاء self.retry() لأن retry() يرفع استثناء يوقف تنفيذ الدالة
                send_to_dead_letter_queue.delay(job_id, str(exc), str(einfo))

                # لا نقوم بإعادة المحاولة هنا لأن المهمة قد فشلت بالفعل بعد استنفاد جميع محاولات إعادة التنفيذ
                # دالة on_failure تُستدعى فقط بعد استنفاد جميع محاولات إعادة التنفيذ

            except Job.DoesNotExist:
                logger.error(f"Job {job_id} not found during final failure handling.")
                logger.critical(f"ALERT: Job {job_id} record not found during final failure handling. Error: {einfo}")
            except Exception as e:
                logger.error(f"Error during final failure handling for job {job_id}: {e}")

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Handle task retry."""
        job_id = args[0] if args else None
        if job_id:
            try:
                job = Job.objects.get(pk=job_id)
                job.retry_count = self.request.retries
                job.error_message = f"Task failed, retrying ({self.request.retries + 1}/{self.max_retries}): {exc}"
                job.last_attempt_time = timezone.now()
                job.save(update_fields=['retry_count', 'error_message', 'last_attempt_time'])
                logger.warning(f"Retrying job {job_id} (Attempt {self.request.retries + 1}/{self.max_retries}): {exc}")
            except Job.DoesNotExist:
                 logger.error(f"Job {job_id} not found during retry handling.")
            except Exception as e:
                 logger.error(f"Error during retry handling for job {job_id}: {e}")

@shared_task(bind=True, base=JobTask, autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=600, retry_jitter=True, max_retries=3)
def process_job_task(self, job_id, sleep_time=10):
    """Processes a job identified by job_id with priority support.
    Jobs with higher priority will be processed first.

    Args:
        job_id: The ID of the job to process
        sleep_time: Time to sleep in seconds to simulate work (default: 10)
    """
    # Log task start
    logger.info(f"Task {self.request.id} started with job_id={job_id}, sleep_time={sleep_time}")

    try:
        job = Job.objects.get(pk=job_id)
        logger.info(f"Starting job {job_id} ({job.task_name}) with priority {job.priority}")

        # Update status to 'in_progress' only if it's pending or failed (for retry)
        if job.status in ['pending', 'failed']:
             job.status = 'in_progress'
             job.last_attempt_time = timezone.now()
             job.retry_count = self.request.retries # Update retry count on start/retry
             job.save(update_fields=['status', 'last_attempt_time', 'retry_count'])

        # --- Simulate Task Work ---
        # Replace this section with actual task logic (e.g., sending email, generating report)
        print(f"Processing job {job_id}: {job.task_name} with priority {job.priority}...")
        logger.info(f"Job {job_id} ({job.task_name}) with priority {job.priority} is sleeping for {sleep_time} seconds")
        time.sleep(sleep_time) # Simulate work with configurable sleep time

        # Example: Simulate a potential failure for demonstration (Original code - now commented out)
        # import random
        # if random.random() < 0.6: # 60% chance of failure
        #     raise ValueError(f"Simulated processing error for job {job_id}")




        # --- Task Completion ---
        job.status = 'completed'
        job.error_message = None # Clear error on success
        job.save(update_fields=['status', 'error_message'])
        logger.info(f"Job {job_id} ({job.task_name}) completed successfully.")
        return f"Job {job_id} completed successfully."

    except Job.DoesNotExist:
        logger.error(f"Job {job_id} not found.")
        # Don't retry if the job doesn't exist
        return f"Job {job_id} not found."
    except Exception as exc:
        logger.error(f"Exception during processing job {job_id}: {exc}")
        # The autoretry_for mechanism will handle retrying based on the exception
        # The on_retry and on_failure methods in JobTask handle status updates
        raise # Re-raise the exception for Celery to handle retry/failure


@shared_task
def send_to_dead_letter_queue(job_id, error, traceback):
    """
    Stores failed tasks in the dead letter queue and sends notifications.
    """
    try:
        # Get the original job
        job = Job.objects.get(pk=job_id)

        # Create a dead letter queue entry
        dlq_entry = DeadLetterQueue.objects.create(
            original_job=job,
            task_id=job_id,  # Using job_id as task_id for simplicity
            task_name=job.task_name,
            error_message=error,
            traceback=traceback,
            args=json.dumps([job_id]),
            kwargs=json.dumps({})
        )

        # Send notification
        send_failure_notification.delay(dlq_entry.id)

        logger.info(f"Job {job_id} added to dead letter queue with ID {dlq_entry.id}")
        return f"Job {job_id} added to dead letter queue"
    except Job.DoesNotExist:
        logger.error(f"Job {job_id} not found when adding to dead letter queue")
        return f"Job {job_id} not found"
    except Exception as e:
        logger.error(f"Error adding job {job_id} to dead letter queue: {e}")
        return f"Error: {e}"


@shared_task
def send_failure_notification(dlq_entry_id):
    """
    Sends a notification about a failed task.
    """
    try:
        # Get the dead letter queue entry
        dlq_entry = DeadLetterQueue.objects.get(pk=dlq_entry_id)

        # Skip if notification already sent
        if dlq_entry.notification_sent:
            return f"Notification already sent for DLQ entry {dlq_entry_id}"

        # Prepare notification message
        subject = f"[ALERT] Task Failed Permanently: {dlq_entry.task_name}"
        message = f"""Task has failed permanently after multiple retries:

        Task ID: {dlq_entry.task_id}
        Task Name: {dlq_entry.task_name}
        Error: {dlq_entry.error_message}
        Time: {dlq_entry.created_at}

        Please check the admin interface for more details and to reprocess the task if needed.
        """

        # Send email notification if configured
        admin_emails = getattr(settings, 'ADMIN_EMAILS', [])
        if admin_emails:
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                admin_emails,
                fail_silently=True,
            )
            logger.info(f"Sent email notification for failed task {dlq_entry.task_id} to {admin_emails}")

        # Log the notification
        logger.critical(subject + "\n" + message)

        # Mark notification as sent
        dlq_entry.notification_sent = True
        dlq_entry.save(update_fields=['notification_sent'])

        return f"Notification sent for DLQ entry {dlq_entry_id}"
    except DeadLetterQueue.DoesNotExist:
        logger.error(f"DLQ entry {dlq_entry_id} not found when sending notification")
        return f"DLQ entry {dlq_entry_id} not found"
    except Exception as e:
        logger.error(f"Error sending notification for DLQ entry {dlq_entry_id}: {e}")
        return f"Error: {e}"


@shared_task
def reprocess_failed_task(dlq_entry_id):
    """
    Reprocesses a failed task from the dead letter queue.
    """
    try:
        # Get the dead letter queue entry
        dlq_entry = DeadLetterQueue.objects.get(pk=dlq_entry_id)

        # Skip if already reprocessed
        if dlq_entry.reprocessed:
            return f"DLQ entry {dlq_entry_id} already reprocessed"

        # Get the original job
        job = dlq_entry.original_job
        if not job:
            return f"Original job not found for DLQ entry {dlq_entry_id}"

        # Reset job status
        job.status = 'pending'
        job.retry_count = 0
        job.error_message = None
        job.permanently_failed = False
        job.save(update_fields=['status', 'retry_count', 'error_message', 'permanently_failed'])

        # Queue the job again
        process_job_task.apply_async(
            args=[job.id],
            kwargs={},
            countdown=0
        )

        # Mark as reprocessed
        dlq_entry.reprocessed = True
        dlq_entry.reprocessed_at = timezone.now()
        dlq_entry.save(update_fields=['reprocessed', 'reprocessed_at'])

        logger.info(f"Reprocessed failed task from DLQ entry {dlq_entry_id}")
        return f"Reprocessed DLQ entry {dlq_entry_id}"
    except DeadLetterQueue.DoesNotExist:
        logger.error(f"DLQ entry {dlq_entry_id} not found when reprocessing")
        return f"DLQ entry {dlq_entry_id} not found"
    except Exception as e:
        logger.error(f"Error reprocessing DLQ entry {dlq_entry_id}: {e}")
        return f"Error: {e}"


@shared_task(bind=True, base=JobTask, autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=600, retry_jitter=True, max_retries=4)
def test_failure_task(self, job_id):
    """
    A task that always fails for testing the failure handling mechanism.
    """
    logger.info(f"Starting test_failure_task for job {job_id}")

    try:
        job = Job.objects.get(pk=job_id)

        # Update status to 'in_progress'
        if job.status in ['pending', 'failed']:
            job.status = 'in_progress'
            job.last_attempt_time = timezone.now()
            job.retry_count = self.request.retries
            job.save(update_fields=['status', 'last_attempt_time', 'retry_count'])

        # Always fail with a test error
        raise ValueError(f"This is a test failure for job {job_id}")

    except Job.DoesNotExist:
        logger.error(f"Job {job_id} not found.")
        return f"Job {job_id} not found."
    except Exception as exc:
        logger.error(f"Exception during test_failure_task for job {job_id}: {exc}")
        raise  # Re-raise the exception for Celery to handle retry/failure
