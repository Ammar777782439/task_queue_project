from django.core.management.base import BaseCommand, CommandError
from jobs.models import Job
from jobs.tasks import process_job_task
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Creates a new job and queues it for processing.'

    def add_arguments(self, parser):
        parser.add_argument('task_name', type=str, help='The name of the task to create.')
        parser.add_argument('--priority', type=int, default=0, help='The priority of the job (higher value means higher priority).')
        parser.add_argument('--max_retries', type=int, default=3, help='Maximum number of retries for the job.')
        # Add other arguments as needed for specific task parameters

    def handle(self, *args, **options):
        task_name = options['task_name']
        priority = options['priority']
        max_retries = options['max_retries']

        try:
            # Create the Job record in the database
            job = Job.objects.create(
                task_name=task_name,
                priority=priority,
                max_retries=max_retries,
                status='pending' # Initial status
            )
            self.stdout.write(self.style.SUCCESS(f'Successfully created job {job.id} with task name "{task_name}".'))

            # Queue the job using Celery, passing the job ID and applying priority
            # Note: Celery priorities require a broker that supports them (like Redis in certain configurations, or RabbitMQ).
            # Redis priority support might need specific setup. Check Celery docs.
            # For simplicity, we pass priority here, but its effect depends on the broker setup.
            process_job_task.apply_async(
                args=[job.id],
                priority=priority, # Pass priority to Celery
                # You might need to pass other task-specific arguments here
                # kwargs={'param1': 'value1'}
                retry_policy={ # Pass retry settings from the Job model to the task instance
                    'max_retries': job.max_retries,
                    # 'retry_backoff': True, # Already set in @shared_task decorator
                    # 'retry_backoff_max': 600, # Already set
                    # 'retry_jitter': True, # Already set
                }
            )

            self.stdout.write(self.style.SUCCESS(f'Successfully queued job {job.id} for processing.'))

        except Exception as e:
            logger.error(f"Error creating or queuing job: {e}")
            raise CommandError(f'Failed to create or queue job: {e}')
