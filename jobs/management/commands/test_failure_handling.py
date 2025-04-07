from django.core.management.base import BaseCommand
from jobs.models import Job
from jobs.tasks import test_failure_task
import time
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Creates a test job that will fail to test the failure handling mechanism'

    def add_arguments(self, parser):
        parser.add_argument('--name', type=str, default='Test Failure Job', help='Name for the test job')
        parser.add_argument('--priority', type=int, default=5, help='Priority for the test job')
        parser.add_argument('--max-retries', type=int, default=2, help='Maximum retries for the test job')

    def handle(self, *args, **options):
        name = options['name']
        priority = options['priority']
        max_retries = options['max_retries']
        
        # Create a test job
        job = Job.objects.create(
            task_name=name,
            priority=priority,
            max_retries=max_retries,
            status='pending'
        )
        
        self.stdout.write(f"Created test job '{name}' with ID {job.id}")
        
        # Queue the test failure task
        test_failure_task.apply_async(
            args=[job.id],
            kwargs={},
            countdown=0
        )
        
        self.stdout.write(self.style.SUCCESS(f"Queued test_failure_task for job {job.id}"))
        self.stdout.write("This task will fail and test the failure handling mechanism.")
        self.stdout.write("Check the worker logs and the Dead Letter Queue in the admin interface.")
        self.stdout.write(f"Admin URL: /admin/jobs/deadletterqueue/")
