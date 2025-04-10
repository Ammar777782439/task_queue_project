from django.core.management.base import BaseCommand
from jobs.models import Job
from jobs.tasks import process_job_task, monitor_batch_completion
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
        parser.add_argument('--long-task', type=str, default=None,
                          help='تحديد مهمة طويلة المدة بالصيغة "batch:task:time" مثل "1:3:90" لجعل المهمة 3 في الدفعة 1 تستغرق 90 ثانية')
        parser.add_argument('--long-tasks', type=str, default=None,
                          help='تحديد عدة مهام طويلة المدة بالصيغة "batch1:task1:time1,batch2:task2:time2" مثل "1:3:90,2:2:120"')

    def handle(self, *args, **options):
        num_batches = options['batches']
        tasks_per_batch = options['tasks_per_batch']
        execution_time = options['execution_time']
        wait_time = options['wait_time']
        clear = options['clear']
        priority_distribution = options['priority_distribution']
        long_task = options['long_task']
        long_tasks = options['long_tasks']

        # إنشاء قاموس للمهام الطويلة
        long_task_dict = {}

        # معالجة مهمة طويلة واحدة
        if long_task:
            try:
                batch, task, time_value = map(int, long_task.split(':'))
                long_task_dict[(batch, task)] = time_value
                self.stdout.write(f"تم تحديد مهمة طويلة: الدفعة {batch}, المهمة {task}, الوقت {time_value} ثانية")
            except (ValueError, IndexError):
                self.stderr.write(self.style.ERROR("خطأ في تنسيق المهمة الطويلة. استخدم الصيغة 'batch:task:time' مثل '1:3:90'"))
                return

        # معالجة عدة مهام طويلة
        if long_tasks:
            try:
                for task_spec in long_tasks.split(','):
                    batch, task, time_value = map(int, task_spec.split(':'))
                    long_task_dict[(batch, task)] = time_value
                    self.stdout.write(f"تم تحديد مهمة طويلة: الدفعة {batch}, المهمة {task}, الوقت {time_value} ثانية")
            except (ValueError, IndexError):
                self.stderr.write(self.style.ERROR("خطأ في تنسيق المهام الطويلة. استخدم الصيغة 'batch1:task1:time1,batch2:task2:time2' مثل '1:3:90,2:2:120'"))
                return

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

        # حساب أوقات التنفيذ لكل دفعة مع مراعاة المهام الطويلة
        batch_execution_times = []
        for b in range(num_batches):
            b_num = b + 1
            max_time = execution_time
            for t in range(1, tasks_per_batch + 1):
                if (b_num, t) in long_task_dict:
                    max_time = max(max_time, long_task_dict[(b_num, t)])
            batch_execution_times.append(max_time)

        # حساب أوقات بدء كل دفعة
        batch_start_times = []
        current_time = timezone.now()
        batch_start_times.append(current_time)

        for b in range(1, num_batches):
            next_start = current_time + datetime.timedelta(seconds=batch_execution_times[b-1] + wait_time)
            batch_start_times.append(next_start)
            current_time = next_start

        # قائمة لتخزين معرفات المهام لكل دفعة
        all_batch_job_ids = []

        # إنشاء المهام
        for batch in range(num_batches):
            # استخدام وقت البدء المحسوب مسبقاً
            batch_start_time = batch_start_times[batch]

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

            # جمع معرفات المهام لكل دفعة
            batch_job_ids = [task_info['job'].id for task_info in batch_tasks]

            # إضافة معرفات المهام للقائمة الرئيسية
            all_batch_job_ids.append(batch_job_ids)

            # لا نحتاج إلى إعداد معرفات الدفعة التالية هنا
            # سنستخدم القائمة all_batch_job_ids لاحقاً

            # إرسال المهام إلى الطابور بالترتيب حسب الأولوية
            for task_info in batch_tasks:
                job = task_info['job']
                task_number = task_info['task_number']

                # تحديد وقت التنفيذ (العادي أو الطويل)
                task_execution_time = execution_time

                # التحقق مما إذا كانت هذه مهمة طويلة
                batch_num = batch + 1  # الدفعات تبدأ من 1 في المعاملات
                # استخراج رقم المهمة من اسم المهمة
                task_name_parts = job.task_name.split(' - ')
                if len(task_name_parts) > 1:
                    task_part = task_name_parts[1].split(' ')[1]
                    try:
                        task_num = int(task_part)
                    except ValueError:
                        task_num = 0
                else:
                    task_num = 0

                if (batch_num, task_num) in long_task_dict:
                    task_execution_time = long_task_dict[(batch_num, task_num)]
                    self.stdout.write(f"  - المهمة {task_number} ستستغرق وقتاً أطول: {task_execution_time} ثانية")

                # إرسال المهمة إلى الطابور مع تحديد وقت البدء
                # للدفعة الأولى فقط، نستخدم eta
                # للدفعات اللاحقة، ستتم جدولتها بواسطة مهمة المراقبة
                if batch == 0:
                    process_job_task.apply_async(
                        args=[job.id],
                        kwargs={'sleep_time': task_execution_time},
                        eta=batch_start_time,  # استخدام وقت محدد للبدء
                        priority=job.priority  # تعيين الأولوية في Celery
                    )
                    self.stdout.write(f"  - تم إرسال المهمة {task_number} إلى الطابور (أولوية {job.priority}, وقت التنفيذ: {task_execution_time} ثانية)")
                else:
                    # للدفعات اللاحقة، نحفظ المعرفات فقط ولا نرسل المهام بعد
                    # سيتم إرسالها بواسطة مهمة المراقبة
                    self.stdout.write(f"  - تم تجهيز المهمة {task_number} للدفعة {batch+1} (أولوية {job.priority}, وقت التنفيذ: {task_execution_time} ثانية)")

            # استخدام وقت التنفيذ المحسوب مسبقاً
            batch_num = batch + 1

            # إذا كانت هذه هي الدفعة الأولى وهناك دفعة تالية
            if batch == 0 and batch < num_batches - 1:

                # لا نرسل مهمة المراقبة هنا لأننا سنرسلها لاحقاً
                self.stdout.write(f"سيتم إرسال مهمة مراقبة للدفعة {batch+1} وبدء الدفعة {batch+2} بعد اكتمالها لاحقاً")

                # عرض معلومات عن الدفعة التالية
                next_batch_start = batch_start_times[batch + 1]
                self.stdout.write(f"الدفعة التالية ستبدأ بعد اكتمال الدفعة الحالية وفترة انتظار {wait_time} ثانية")
                self.stdout.write(f"الوقت المقدر لبدء الدفعة التالية (بناءً على التقدير الأولي): {next_batch_start}")

            # إذا كانت هذه ليست الدفعة الأولى وليست الدفعة الأخيرة
            elif batch > 0 and batch < num_batches - 1:

                # لا نرسل مهمة مراقبة هنا لأن الدفعة السابقة ستقوم بذلك
                self.stdout.write(f"ستبدأ الدفعة {batch+1} بعد اكتمال الدفعة {batch} وفترة انتظار {wait_time} ثانية")

            # إذا كانت هذه هي الدفعة الأخيرة
            elif batch == num_batches - 1:
                self.stdout.write(f"هذه هي الدفعة الأخيرة ({batch+1})")

        self.stdout.write(self.style.SUCCESS("\nتم إنشاء جميع المهام بنجاح!"))

        # إرسال مهام المراقبة لكل دفعة
        for batch in range(num_batches - 1):  # لا نحتاج إلى مراقبة الدفعة الأخيرة
            # إذا كانت هذه هي الدفعة الأولى
            if batch == 0:
                monitor_batch_completion.apply_async(
                    args=[all_batch_job_ids[batch], all_batch_job_ids[batch + 1], wait_time],
                    countdown=10  # بدء المراقبة بعد 10 ثواني
                )
                self.stdout.write(f"\nتم إرسال مهمة مراقبة للدفعة {batch+1} وبدء الدفعة {batch+2} بعد اكتمالها")

        # حساب الوقت الإجمالي من أوقات البدء المحسوبة مسبقاً
        if num_batches > 0:
            total_time = batch_execution_times[-1]  # وقت تنفيذ الدفعة الأخيرة

            if num_batches > 1:
                # إضافة الوقت بين بداية الدفعة الأولى وبداية الدفعة الأخيرة
                time_diff = (batch_start_times[-1] - batch_start_times[0]).total_seconds()
                total_time += time_diff
        else:
            total_time = 0

        self.stdout.write(f"سيستغرق تنفيذ جميع المهام حوالي {total_time} ثانية")
        self.stdout.write(f"راقب حالة المهام في لوحة الإدارة: http://127.0.0.1:8000/admin/jobs/job/")

        # توضيح سلوك التنفيذ المتوقع
        self.stdout.write("\nالسلوك المتوقع:")
        self.stdout.write("1. ستبدأ الدفعة الأولى فوراً، وستبدأ الدفعات التالية فقط بعد اكتمال الدفعة السابقة.")
        self.stdout.write("2. في كل دفعة، ستبدأ المهام ذات الأولوية الأعلى أولاً.")
        self.stdout.write("3. سيتم تنفيذ ما يصل إلى 4 مهام متزامنة (حسب إعدادات التزامن).")
        self.stdout.write("4. بعد انتهاء جميع مهام الدفعة، سيكون هناك فترة انتظار قبل بدء الدفعة التالية.")
        self.stdout.write("5. تستخدم مهمة مراقبة للتأكد من اكتمال جميع مهام الدفعة قبل بدء الدفعة التالية.")
        self.stdout.write("6. إذا فشلت مهمة وتمت إعادة محاولتها، فستنتظر مهمة المراقبة حتى تكتمل جميع المحاولات قبل بدء الدفعة التالية.")

        # توضيح سلوك المهام الطويلة
        if long_task_dict:
            self.stdout.write("\nسلوك المهام الطويلة:")
            self.stdout.write("1. المهام الطويلة ستستغرق وقتاً أطول من المهام العادية.")
            self.stdout.write("2. مهمة المراقبة ستنتظر حتى تكتمل جميع المهام في الدفعة قبل بدء فترة الانتظار.")
            self.stdout.write("3. إذا كانت هناك مهمة طويلة تستغرق وقتاً أطول من المهام الأخرى، فستنتظر مهمة المراقبة حتى تكتمل هذه المهمة قبل بدء الدفعة التالية.")
            self.stdout.write("4. هذا يضمن أن الدفعة التالية لن تبدأ أبداً قبل اكتمال جميع مهام الدفعة الحالية، بغض النظر عن مدة تنفيذها.")

            # عرض المهام الطويلة
            self.stdout.write("\nالمهام الطويلة المحددة:")
            for (batch_num, task_num), time_value in long_task_dict.items():
                self.stdout.write(f"- الدفعة {batch_num}, المهمة {task_num}: {time_value} ثانية")
