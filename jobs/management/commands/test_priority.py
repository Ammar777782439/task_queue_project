from django.core.management.base import BaseCommand
from jobs.models import Job
from jobs.tasks import process_job_task
import time
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Tests the priority system by creating jobs with specific priorities in a specific order'

    def handle(self, *args, **options):
        # Clear existing pending jobs
        pending_jobs = Job.objects.filter(status='pending')
        if pending_jobs.exists():
            count = pending_jobs.count()
            pending_jobs.delete()
            self.stdout.write(f"Cleared {count} pending jobs.")

        # Create jobs in reverse priority order (low priority first)
        priorities = [1, 5, 10, 3, 8, 2]
        created_jobs = []

        self.stdout.write("Creating test jobs with different priorities...")

        for i, priority in enumerate(priorities):
            task_name = f"Priority Test {i+1} (Priority: {priority})"

            # Create the Job record
            job = Job.objects.create(
                task_name=task_name,
                priority=priority,
                max_retries=3,
                status='pending'
            )
            created_jobs.append(job)

            self.stdout.write(f"Created job: {task_name}")

            # Wait a moment between job creation to ensure they're created in order
            time.sleep(0.5)

        self.stdout.write(self.style.SUCCESS(f"Created {len(created_jobs)} test jobs."))

        # Now queue all jobs at once
        self.stdout.write("Queuing all jobs...")

        for job in created_jobs:
            # Prepare Celery task arguments and options
            task_args = [job.id]
            task_kwargs = {}

            # Calculate countdown based on priority (higher priority = lower countdown)
            # Max priority (10) gets 0 seconds, lowest priority (0) gets 10 seconds
            countdown = max(0, 10 - job.priority)

            celery_options = {
                'priority': job.priority,  # Keep this for reference
                'retry_policy': {
                    'max_retries': job.max_retries,
                },
                'countdown': countdown  # Add countdown based on priority
            }

            # Queue the job
            process_job_task.apply_async(
                args=task_args,
                kwargs=task_kwargs,
                **celery_options
            )

            self.stdout.write(f"Queued job: {job.task_name}")

        self.stdout.write(self.style.SUCCESS("All jobs queued. Check worker logs to see execution order."))
        self.stdout.write(self.style.WARNING("Expected execution order by priority: 10, 8, 5, 3, 2, 1"))
