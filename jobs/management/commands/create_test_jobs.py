import random
from django.core.management.base import BaseCommand, CommandError
from jobs.models import Job
from jobs.tasks import process_job_task
import logging
from django.utils import timezone

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Creates multiple test jobs with varying priorities and queues them.'

    def add_arguments(self, parser):
        parser.add_argument(
            'count',
            type=int,
            help='The number of test jobs to create.'
        )
        parser.add_argument(
            '--max_priority',
            type=int,
            default=10,
            help='Maximum priority value to assign randomly (0 to max_priority).'
        )

    def handle(self, *args, **options):
        count = options['count']
        max_priority = options['max_priority']

        if count <= 0:
            raise CommandError("Count must be a positive integer.")
        if max_priority < 0:
            raise CommandError("Max priority must be non-negative.")

        created_count = 0
        queued_count = 0

        self.stdout.write(f"Attempting to create and queue {count} test jobs...")

        for i in range(count):
            task_name = f"Test Job {i + 1}"
            # Assign random priority between 0 and max_priority
            priority = random.randint(0, max_priority)
            max_retries = 3 # Default retries for test jobs

            try:
                # Create the Job record
                job = Job.objects.create(
                    task_name=task_name,
                    priority=priority,
                    max_retries=max_retries,
                    status='pending'
                )
                created_count += 1

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

                # Queue the job for immediate processing
                process_job_task.apply_async(
                    args=task_args,
                    kwargs=task_kwargs,
                    **celery_options
                )
                queued_count += 1

            except Exception as e:
                logger.error(f"Error creating or queuing test job {task_name}: {e}")
                self.stderr.write(self.style.ERROR(f'Failed to create or queue test job {task_name}: {e}'))

        self.stdout.write(self.style.SUCCESS(f'Successfully created {created_count} and queued {queued_count} out of {count} test jobs.'))
