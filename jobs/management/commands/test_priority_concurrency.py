from django.core.management.base import BaseCommand
from jobs.models import Job
from jobs.tasks import process_job_task
import time
from django.utils import timezone
import logging
import random

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'أختبر الأولوية والتزامن بإنشاء مهام بأولويات مختلفة'

    def add_arguments(self, parser):
        # هنا أضيف خيارات للأمر لما أشغله من الكوماند لاين
        parser.add_argument('--count', type=int, default=10, help='كم عدد المهام التجريبية اللي تريد تنشئها')
        parser.add_argument('--sleep', type=int, default=10, help='كم ثانية كل مهمة بتأخذ وقتها للنوم')
        parser.add_argument('--clear', action='store_true', help='لو تبي تمسح المهام السابقة قبل تنشئ مهام جديدة')

    def handle(self, *args, **options):
        count = options['count']
        sleep_time = options['sleep']
        clear = options['clear']
        
        # لو اخترت خيار --clear نمسح المهام اللي موجودة قبل
        if clear:
            deleted_count = Job.objects.all().delete()[0]
            self.stdout.write(f"تم مسح {deleted_count} مهمة كانت موجودة")

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

        self.stdout.write(f"بأنشئ {count} مهمة تجريبية بأولويات مختلفة...")

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
            self.stdout.write(f"تم إنشاء المهمة {job.id}: {job.task_name}")

        self.stdout.write(f"أنشأت {len(jobs)} مهام بأولويات مختلفة")

        # الحين بنصف كل المهام في الطابور مرة وحدة
        self.stdout.write("باصف كل المهام في الطابور بنفس الوقت...")
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

            self.stdout.write(f"تمت إضافة المهمة {job.id} بأولوية {job.priority} (عد تنازلي: {countdown:.2f} ثانية)")

        self.stdout.write(self.style.SUCCESS(f"تمت إضافة كل {count} مهمة في الطابور"))
        self.stdout.write("السلوك المتوقع:")
        self.stdout.write("1. المهام بأولوية عالية (10) تبدأ أول")
        self.stdout.write("2. بعدها المهام بأولوية متوسطة (5)")
        self.stdout.write("3. وبالأخير المهام بأولوية منخفضة (0)")
        self.stdout.write(f"4. وشوف بنفسك، ممكن تشتغل حتى 4 مهام بنفس الوقت (حسب إعدادات التزامن)")
        self.stdout.write("\nتابع لوق العمال وشوف حالة المهام في لوحة الإدارة")
        self.stdout.write("رابط لوحة الإدارة: /admin/jobs/job/")
