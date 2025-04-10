from django.core.management.base import BaseCommand
from jobs.models import Job
from jobs.kafka_utils import send_success_message_to_kafka, get_kafka_producer
from django.utils import timezone
from django.conf import settings
import json

class Command(BaseCommand):
    help = 'اختبار إرسال رسائل إلى Kafka'

    def add_arguments(self, parser):
        parser.add_argument('--job-id', type=int, help='معرف المهمة المراد إرسال بياناتها (اختياري)')
        parser.add_argument('--verbose', action='store_true', help='عرض معلومات تفصيلية')

    def handle(self, *args, **options):
        job_id = options.get('job_id')
        verbose = options.get('verbose', False)
        
        # عرض معلومات الاتصال
        self.stdout.write(f"عنوان Kafka: {settings.KAFKA_BOOTSTRAP_SERVERS}")
        self.stdout.write(f"موضوع النجاح: {settings.KAFKA_SUCCESS_TOPIC}")
        
        # التحقق من الاتصال بـ Kafka
        self.stdout.write("التحقق من الاتصال بـ Kafka...")
        producer = get_kafka_producer()
        if not producer:
            self.stdout.write(self.style.ERROR("فشل في الاتصال بـ Kafka. تحقق من السجلات للحصول على مزيد من التفاصيل."))
            return
        
        self.stdout.write(self.style.SUCCESS("تم الاتصال بـ Kafka بنجاح!"))
        
        if job_id:
            # استخدام مهمة موجودة
            try:
                job = Job.objects.get(id=job_id)
                self.stdout.write(f"تم العثور على المهمة: {job.task_name} (ID: {job.id})")
            except Job.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"لم يتم العثور على مهمة بالمعرف {job_id}"))
                return
        else:
            # إنشاء مهمة اختبار جديدة
            job = Job.objects.create(
                task_name="اختبار Kafka",
                priority=10,
                max_retries=3,
                status='completed',
                started_at=timezone.now() - timezone.timedelta(seconds=30),
                completed_at=timezone.now(),
                execution_duration=timezone.timedelta(seconds=30)
            )
            self.stdout.write(f"تم إنشاء مهمة اختبار جديدة: {job.task_name} (ID: {job.id})")
        
        # إعداد بيانات المهمة
        job_data = {
            'job_id': job.id,
            'task_name': job.task_name,
            'priority': job.priority,
            'execution_time': job.execution_duration.total_seconds() if job.execution_duration else None,
            'completed_at': job.completed_at.isoformat() if job.completed_at else None,
            'status': job.status
        }
        
        if verbose:
            self.stdout.write(f"بيانات المهمة: {json.dumps(job_data, indent=2)}")
        
        # إرسال رسالة إلى Kafka
        self.stdout.write(f"جاري إرسال بيانات المهمة {job.id} إلى Kafka...")
        success = send_success_message_to_kafka(job_data)
        
        if success:
            self.stdout.write(self.style.SUCCESS(f"تم إرسال بيانات المهمة {job.id} إلى Kafka بنجاح!"))
        else:
            self.stdout.write(self.style.ERROR(f"فشل في إرسال بيانات المهمة {job.id} إلى Kafka. تحقق من السجلات للحصول على مزيد من التفاصيل."))
