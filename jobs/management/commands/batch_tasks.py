from django.core.management.base import BaseCommand
from jobs.models import Job
from jobs.tasks import process_job_task
from django.utils import timezone
import datetime

class Command(BaseCommand):
    help = 'إنشاء دفعات من المهام المتزامنة مع فترات انتظار بينها، مع مراعاة الأولوية'

    def add_arguments(self, parser):
        parser.add_argument('--batches', type=int, default=3, help='عدد الدفعات المراد إنشاؤها')
        parser.add_argument('--tasks-per-batch', type=int, default=4, help='عدد المهام في كل دفعة')
        parser.add_argument('--execution-time', type=int, default=30, help='وقت تنفيذ كل مهمة بالثواني')
        parser.add_argument('--wait-time', type=int, default=60, help='وقت الانتظار بين الدفعات بالثواني')
        parser.add_argument('--clear', action='store_true', help='مسح المهام الموجودة قبل إنشاء مهام جديدة')
        parser.add_argument('--priority-distribution', type=str, default='high,medium,low',
                          help='توزيع الأولويات (high,medium,low) أو (10,5,0)')

    def handle(self, *args, **options):
        num_batches = options['batches']
        tasks_per_batch = options['tasks_per_batch']
        execution_time = options['execution_time']
        wait_time = options['wait_time']
        clear = options['clear']
        priority_distribution = options['priority_distribution']

        # تحويل توزيع الأولويات إلى قائمة من الأرقام
        if priority_distribution == 'high,medium,low':
            priorities = [10, 5, 0]
        else:
            try:
                priorities = [int(p) for p in priority_distribution.split(',')]
            except ValueError:
                self.stderr.write(self.style.ERROR("خطأ في تنسيق توزيع الأولويات. استخدم 'high,medium,low' أو '10,5,0'"))
                return

        # مسح المهام الموجودة إذا تم تحديد الخيار
        if clear:
            deleted_count = Job.objects.all().delete()[0]
            self.stdout.write(f"تم مسح {deleted_count} مهمة موجودة.")

        total_tasks = num_batches * tasks_per_batch

        self.stdout.write(f"سيتم إنشاء {total_tasks} مهمة في {num_batches} دفعات")
        self.stdout.write(f"كل دفعة تحتوي على {tasks_per_batch} مهام متزامنة")
        self.stdout.write(f"وقت تنفيذ كل مهمة: {execution_time} ثانية")
        self.stdout.write(f"وقت الانتظار بين الدفعات: {wait_time} ثانية")
        self.stdout.write(f"الأولويات المستخدمة: {priorities}")

        # إنشاء المهام
        for batch in range(num_batches):
            # حساب وقت بدء هذه الدفعة
            # الدفعة الأولى تبدأ فوراً، والدفعات التالية تبدأ بعد انتهاء الدفعة السابقة + وقت الانتظار
            batch_start_time = timezone.now() + datetime.timedelta(seconds=(execution_time + wait_time) * batch)

            self.stdout.write(f"\nإنشاء الدفعة {batch+1}:")
            self.stdout.write(f"وقت البدء المجدول: {batch_start_time}")

            # إنشاء قائمة بالمهام مع أولوياتها
            batch_tasks = []

            # إنشاء المهام في هذه الدفعة
            for i in range(tasks_per_batch):
                task_number = batch * tasks_per_batch + i + 1

                # تعيين الأولوية بشكل منتظم لضمان وجود مهام بأولويات مختلفة
                priority_index = i % len(priorities)
                priority = priorities[priority_index]

                job = Job.objects.create(
                    task_name=f"دفعة {batch+1} - مهمة {i+1} (أولوية {priority})",
                    priority=priority,
                    max_retries=3,
                    status='pending',
                    scheduled_time=batch_start_time  # جدولة جميع مهام الدفعة لنفس الوقت
                )

                batch_tasks.append({
                    'job': job,
                    'priority': priority,
                    'task_number': task_number
                })

                self.stdout.write(f"  - تم إنشاء المهمة {task_number}: {job.task_name}")

            # ترتيب المهام حسب الأولوية (من الأعلى إلى الأدنى)
            batch_tasks.sort(key=lambda x: x['priority'], reverse=True)

            # إرسال المهام إلى الطابور بالترتيب حسب الأولوية
            for task_info in batch_tasks:
                job = task_info['job']
                task_number = task_info['task_number']

                # إرسال المهمة إلى الطابور مع تحديد وقت البدء
                process_job_task.apply_async(
                    args=[job.id],
                    kwargs={'sleep_time': execution_time},
                    eta=batch_start_time,  # استخدام وقت محدد للبدء
                    priority=job.priority  # تعيين الأولوية في Celery
                )

                self.stdout.write(f"  - تم إرسال المهمة {task_number} إلى الطابور (أولوية {job.priority})")

            self.stdout.write(f"الدفعة التالية ستبدأ بعد: {execution_time + wait_time} ثانية من بدء هذه الدفعة")

        self.stdout.write(self.style.SUCCESS("\nتم إنشاء جميع المهام بنجاح!"))
        total_time = (execution_time + wait_time) * (num_batches - 1) + execution_time
        self.stdout.write(f"سيستغرق تنفيذ جميع المهام حوالي {total_time} ثانية")
        self.stdout.write(f"راقب حالة المهام في لوحة الإدارة: http://127.0.0.1:8000/admin/jobs/job/")

        # توضيح سلوك التنفيذ المتوقع
        self.stdout.write("\nالسلوك المتوقع:")
        self.stdout.write("1. ستبدأ كل دفعة في الوقت المحدد لها.")
        self.stdout.write("2. في كل دفعة، ستبدأ المهام ذات الأولوية الأعلى أولاً.")
        self.stdout.write("3. سيتم تنفيذ ما يصل إلى 4 مهام متزامنة (حسب إعدادات التزامن).")
        self.stdout.write("4. بعد انتهاء جميع مهام الدفعة، سيكون هناك فترة انتظار قبل بدء الدفعة التالية.")
