import time
from django.core.management.base import BaseCommand
from jobs.models import Job
from jobs.tasks import process_job_task

class Command(BaseCommand):
    help = 'Sends all pending jobs from the database to the Celery queue.'

    def handle(self, *args, **options):
        pending_jobs = Job.objects.filter(status='pending')
        count = pending_jobs.count()

        if count == 0:
            self.stdout.write(self.style.WARNING('No pending jobs found to send.'))
            return

        self.stdout.write(f'Found {count} pending jobs. Sending them to the queue...')

        sent_count = 0
        for job in pending_jobs:
            try:
                process_job_task.delay(job.id)
                self.stdout.write(self.style.SUCCESS(f'Successfully sent task for Job {job.id} ({job.task_name})'))
                sent_count += 1
                time.sleep(0.2) # Add a small delay between sending tasks
            except Exception as e:
                self.stderr.write(self.style.ERROR(f'Failed to send task for Job {job.id}: {e}'))

        self.stdout.write(f'\nFinished sending {sent_count}/{count} pending jobs. Check the worker logs.')
