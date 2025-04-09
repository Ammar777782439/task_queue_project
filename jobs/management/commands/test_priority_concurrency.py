from django.core.management.base import BaseCommand
from jobs.models import Job
from jobs.tasks import process_job_task
import time
from django.utils import timezone
import logging
import random

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Test priority and concurrency by creating jobs with different priorities'

    def add_arguments(self, parser):
        # هنا أضيف خيارات للأمر لما أشغله من الكوماند لاين
        parser.add_argument('--count', type=int, default=10, help='Number of test jobs to create')
        parser.add_argument('--sleep', type=int, default=10, help='Sleep time in seconds for each job')
        parser.add_argument('--clear', action='store_true', help='Clear previous jobs before creating new ones')

    def handle(self, *args, **options):
        count = options['count']
        sleep_time = options['sleep']
        clear = options['clear']
        
        # لو اخترت خيار --clear نمسح المهام اللي موجودة قبل
        if clear:
            deleted_count = Job.objects.all().delete()[0]
            self.stdout.write(f"Cleared {deleted_count} existing jobs.")

        # هنا بأجهز لستة أولويات عشان أعطي لكل مهمة أولويتها
        priorities = []
        for i in range(count):
            if i % 3 == 0:
                priorities.append(10)  # أولوية عالية
            elif i % 3 == 1:
                priorities.append(5)   # أولوية متوسطة
            else:
                priorities.append(0)   # أولوية منخفضة

        # بأخلط الأولويات عشان ما تكون بنفس الترتيب أثناء الإنشاء
        random.shuffle(priorities)

        self.stdout.write(f"Creating {count} test jobs with different priorities...")

        # هنا بننشئ المهام ونحفظهم في لستة jobs
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

        self.stdout.write(f"{len(jobs)} jobs created with different priorities.")

        # الحين بنصف كل المهام في الطابور مرة وحدة
        self.stdout.write("Queueing all jobs at once...")
        # بأحسب أعلى أولوية موجودة من بين كل المهام اللي أنشأتها
        max_priority = max(priorities)

        for job in jobs:
            # بأحسب العد التنازلي حسب الأولوية (كل ما زادت الأولوية نقص الوقت)
            countdown = max(0, max_priority - job.priority)

            # بأضيف تأخير بسيط عشوائي عشان المهام بنفس الأولوية ما تبدأ كلها بنفس اللحظة
            countdown += random.uniform(0, 0.1)

            # بأضيف المهمة في الطابور مع الوقت المحسوب
            process_job_task.apply_async(
                args=[job.id],
                kwargs={'sleep_time': sleep_time},  # بأرسل له وقت النوم عشان يحاكي شغل حقيقي
                countdown=countdown
            )

            self.stdout.write(f"Queued job {job.id} with priority {job.priority} (countdown: {countdown:.2f} seconds)")

        self.stdout.write(self.style.SUCCESS(f"All {count} jobs have been queued successfully."))
        self.stdout.write("Expected behavior:")
        self.stdout.write("1. High priority jobs (10) start first.")
        self.stdout.write("2. Then medium priority jobs (5).")
        self.stdout.write("3. Finally, low priority jobs (0).")
        self.stdout.write("4. Observe up to 4 jobs running concurrently (depending on concurrency settings).")
        self.stdout.write("\nCheck worker logs and monitor job statuses in the admin panel.")
        self.stdout.write("Admin panel URL: /admin/jobs/job/")
