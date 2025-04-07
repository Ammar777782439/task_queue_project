from django.core.management.base import BaseCommand
from jobs.models import Job
from jobs.tasks import process_job_task
import time
from django.utils import timezone
import logging
import random

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Tests both priority and concurrency by creating jobs with different priorities'

    def add_arguments(self, parser):
        parser.add_argument('--count', type=int, default=10, help='Number of test jobs to create')
        parser.add_argument('--sleep', type=int, default=10, help='Sleep time for each job in seconds')
        parser.add_argument('--clear', action='store_true', help='Clear existing jobs before creating new ones')

    def handle(self, *args, **options):
        count = options['count']
        sleep_time = options['sleep']
        clear = options['clear']
        
        # Clear existing jobs if requested
        if clear:
            deleted_count = Job.objects.all().delete()[0]
            self.stdout.write(f"Cleared {deleted_count} existing jobs")
        
        # Create a list of priorities to assign
        # We'll create jobs with priorities 0, 5, and 10 to clearly see the difference
        priorities = []
        for i in range(count):
            if i % 3 == 0:
                priorities.append(10)  # High priority
            elif i % 3 == 1:
                priorities.append(5)   # Medium priority
            else:
                priorities.append(0)   # Low priority
        
        # Shuffle the priorities to ensure they're not created in priority order
        random.shuffle(priorities)
        
        self.stdout.write(f"Creating {count} test jobs with varying priorities...")
        
        # Create the jobs
        jobs = []
        for i in range(count):
            priority = priorities[i]
            job = Job.objects.create(
                task_name=f"Priority-{priority} Job {i+1}",
                priority=priority,
                max_retries=3,
                status='pending'
            )
            jobs.append(job)
            self.stdout.write(f"Created job {job.id}: {job.task_name}")
        
        self.stdout.write(f"Created {len(jobs)} jobs with varying priorities")
        
        # Queue all jobs at once
        self.stdout.write("Queuing all jobs simultaneously...")
        
        for job in jobs:
            # Calculate countdown based on priority (higher priority = lower countdown)
            # Max priority (10) gets 0 seconds, lowest priority (0) gets 10 seconds
            countdown = max(0, 10 - job.priority)
            
            # Add a small random delay to ensure jobs with same priority don't always process in creation order
            countdown += random.uniform(0, 0.1)
            
            # Queue the job with the appropriate priority
            process_job_task.apply_async(
                args=[job.id],
                kwargs={'sleep_time': sleep_time},  # Pass sleep time to simulate work
                countdown=countdown
            )
            
            self.stdout.write(f"Queued job {job.id} with priority {job.priority} (countdown: {countdown:.2f}s)")
        
        self.stdout.write(self.style.SUCCESS(f"All {count} jobs queued"))
        self.stdout.write("Expected behavior:")
        self.stdout.write("1. High priority jobs (10) should start first")
        self.stdout.write("2. Medium priority jobs (5) should start next")
        self.stdout.write("3. Low priority jobs (0) should start last")
        self.stdout.write(f"4. Up to 4 jobs should run concurrently (based on your concurrency settings)")
        self.stdout.write("\nMonitor the worker logs and check the job statuses in the admin interface")
        self.stdout.write("Admin URL: /admin/jobs/job/")
