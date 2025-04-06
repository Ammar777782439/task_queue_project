from django.core.management.base import BaseCommand, CommandError
from django.core.management.base import BaseCommand, CommandError
from jobs.models import Job
from jobs.tasks import process_job_task
import logging
from django.utils import timezone # Import timezone
from datetime import datetime # Import datetime

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Creates a new job and queues it for processing. Optionally schedules it for a future time.'

    def add_arguments(self, parser):
        parser.add_argument('task_name', type=str, help='The name of the task to create.')
        parser.add_argument('--priority', type=int, default=0, help='The priority of the job (higher value means higher priority).')
        parser.add_argument('--max_retries', type=int, default=3, help='Maximum number of retries for the job.')
        parser.add_argument('--schedule_at', type=str, default=None, help='Schedule the task for a specific time (YYYY-MM-DD HH:MM:SS). Requires Celery Beat.')
        # Add other arguments as needed for specific task parameters

    def handle(self, *args, **options):
        task_name = options['task_name']
        priority = options['priority']
        max_retries = options['max_retries']
        schedule_at_str = options['schedule_at']

        scheduled_time = None
        if schedule_at_str:
            try:
                # Attempt to parse the datetime string (assuming local timezone if not specified)
                naive_dt = datetime.strptime(schedule_at_str, '%Y-%m-%d %H:%M:%S')
                # Make it timezone-aware using Django's current timezone
                scheduled_time = timezone.make_aware(naive_dt, timezone.get_current_timezone())
            except ValueError:
                raise CommandError("Invalid datetime format for --schedule_at. Use 'YYYY-MM-DD HH:MM:SS'.")

        try:
            # Create the Job record in the database
            job = Job.objects.create(
                task_name=task_name,
                priority=priority,
                max_retries=max_retries,
                status='pending', # Initial status
                scheduled_time=scheduled_time # Save scheduled time
            )
            self.stdout.write(self.style.SUCCESS(f'Successfully created job {job.id} with task name "{task_name}".'))

            # Prepare Celery task arguments and options
            task_args = [job.id]
            task_kwargs = {} # Add task-specific kwargs if needed
            celery_options = {
                'priority': priority,  # This is used by the router to select the queue
                'retry_policy': {
                    'max_retries': job.max_retries,
                },
                # Explicitly set the queue based on priority
                'queue': f'priority_{priority}'
            }

            # Use 'eta' if scheduled_time is set and in the future
            if job.scheduled_time and job.scheduled_time > timezone.now():
                celery_options['eta'] = job.scheduled_time
                self.stdout.write(self.style.SUCCESS(f'Successfully scheduled job {job.id} for {job.scheduled_time}.'))
            else:
                # If scheduled_time is in the past or not set, queue for immediate processing
                if job.scheduled_time:
                     self.stdout.write(self.style.WARNING(f"Scheduled time {job.scheduled_time} is in the past. Queuing for immediate processing."))
                self.stdout.write(self.style.SUCCESS(f'Successfully queued job {job.id} for immediate processing.'))

            # Queue the job using Celery
            process_job_task.apply_async(
                args=task_args,
                kwargs=task_kwargs,
                **celery_options
            )

        except Exception as e:
            logger.error(f"Error creating or queuing job: {e}")
            raise CommandError(f'Failed to create or queue job: {e}')
