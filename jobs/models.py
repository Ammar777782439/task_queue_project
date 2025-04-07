
from django.db import models
from django.utils import timezone

class Job(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('failed', 'Failed'), # Changed to Arabic for consistency if needed elsewhere
    ]

    task_name = models.CharField(max_length=255, help_text="اسم وصفي للمهمة (مثلاً: إرسال النشرة الإخبارية).")
    priority = models.IntegerField(default=0, help_text="أولوية المهمة (قيمة أعلى تعني أولوية أعلى، يتطلب دعم الوسيط).")
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        help_text="الحالة الحالية للمهمة (قيد الانتظار، قيد التنفيذ، مكتملة، فشلت)."
    )
    retry_count = models.IntegerField(default=0, help_text="عدد المرات التي تمت فيها إعادة محاولة المهمة بعد الفشل.")
    max_retries = models.IntegerField(default=3, help_text="الحد الأقصى لعدد مرات إعادة المحاولة المسموح بها للمهمة.")
    scheduled_time = models.DateTimeField(null=True, blank=True, help_text="الوقت المجدول لتنفيذ المهمة (إذا كانت مؤجلة).")
    last_attempt_time = models.DateTimeField(null=True, blank=True, help_text="وقت آخر محاولة لتنفيذ المهمة.")
    error_message = models.TextField(blank=True, null=True, help_text="رسالة الخطأ في حال فشل المهمة.")
    created_at = models.DateTimeField(auto_now_add=True, help_text="وقت إنشاء سجل المهمة.")
    updated_at = models.DateTimeField(auto_now=True, help_text="وقت آخر تحديث لسجل المهمة.")
    permanently_failed = models.BooleanField(default=False, help_text="يشير إلى ما إذا كانت المهمة قد فشلت نهائيًا بعد كل المحاولات.")

    def __str__(self):
        return f"{self.task_name} - {self.status}"


class DeadLetterQueue(models.Model):
    """Model for storing failed tasks that couldn't be processed after multiple retries."""

    original_job = models.ForeignKey(Job, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='dead_letter_entries',
                                    help_text="المهمة الأصلية التي فشلت.")
    task_id = models.CharField(max_length=255, help_text="معرف المهمة في Celery.")
    task_name = models.CharField(max_length=255, help_text="اسم المهمة.")
    error_message = models.TextField(help_text="رسالة الخطأ التي تسببت في فشل المهمة.")
    traceback = models.TextField(blank=True, null=True, help_text="تتبع الاستدعاء للخطأ.")
    args = models.TextField(blank=True, null=True, help_text="وسائط المهمة.")
    kwargs = models.TextField(blank=True, null=True, help_text="وسائط المهمة المسماة.")
    created_at = models.DateTimeField(default=timezone.now, help_text="وقت إضافة المهمة إلى قائمة انتظار الرسائل الميتة.")
    reprocessed = models.BooleanField(default=False, help_text="ما إذا تمت إعادة معالجة المهمة.")
    reprocessed_at = models.DateTimeField(null=True, blank=True, help_text="وقت إعادة معالجة المهمة.")
    notification_sent = models.BooleanField(default=False, help_text="ما إذا تم إرسال إشعار بفشل المهمة.")

    class Meta:
        verbose_name = "مهمة فاشلة"
        verbose_name_plural = "المهام الفاشلة"
        ordering = ['-created_at']

    def __str__(self):
        return f"Failed Task: {self.task_name} ({self.task_id})"
