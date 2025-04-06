from __future__ import absolute_import, unicode_literals
import time
from celery import shared_task, Task
from .models import Job
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

class JobTask(Task):
    """Custom Task class to handle Job status updates."""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Handle task failure after all retries."""
        job_id = args[0] if args else None
        if job_id:
            try:
                job = Job.objects.get(pk=job_id)
                job.status = 'failed'
                job.error_message = f"Task failed after retries: {einfo}"
                job.last_attempt_time = timezone.now()
                job.save(update_fields=['status', 'error_message', 'last_attempt_time'])
                logger.error(f"Job {job_id} failed permanently: {einfo}")
                # Implement further failure handling like alerting or dead-letter queue logic here
            except Job.DoesNotExist:
                logger.error(f"Job {job_id} not found during final failure handling.")
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

@shared_task(bind=True, base=JobTask, autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=600, retry_jitter=True)
def process_job_task(self, job_id):
    """
    Processes a job identified by job_id.
    Updates job status and handles retries.
    """
    try:
        job = Job.objects.get(pk=job_id)
        logger.info(f"Starting job {job_id} ({job.task_name})")

        # Update status to 'in_progress' only if it's pending or failed (for retry)
        if job.status in ['pending', 'failed']:
             job.status = 'in_progress'
             job.last_attempt_time = timezone.now()
             job.retry_count = self.request.retries # Update retry count on start/retry
             job.save(update_fields=['status', 'last_attempt_time', 'retry_count'])

        # --- Simulate Task Work ---
        # Replace this section with actual task logic (e.g., sending email, generating report)
        print(f"Processing job {job_id}: {job.task_name}...")
        time.sleep(5) # Simulate work

        # Example: Simulate a potential failure for demonstration
        import random
        if random.random() < 0.6: # 60% chance of failure
            raise ValueError(f"Simulated processing error for job {job_id}")

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
