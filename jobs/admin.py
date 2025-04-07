import time
from django.contrib import admin, messages
from .models import Job, DeadLetterQueue
from .tasks import process_job_task, reprocess_failed_task, test_failure_task # Import the tasks
from django.utils import timezone # Import timezone
from .tasks import send_failure_notification
from jobs.models import DeadLetterQueue
@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ('id', 'task_name', 'status', 'permanently_failed', 'priority', 'retry_count', 'created_at', 'last_attempt_time')
    list_filter = ('status', 'permanently_failed', 'priority', 'created_at')
    search_fields = ('id', 'task_name', 'status')
    ordering = ('-created_at',)
    readonly_fields = ('status', 'retry_count', 'last_attempt_time', 'error_message', 'created_at', 'updated_at', 'permanently_failed')
    list_per_page = 25
    actions = ['retry_selected_jobs', 'fail_completed_jobs']  # إضافة أكشن جديدة

    fieldsets = (
        (None, {
            'fields': ('task_name', 'priority', 'max_retries', 'scheduled_time')
        }),
        ('Status & Tracking', {
            'fields': ('status', 'permanently_failed', 'retry_count', 'last_attempt_time', 'error_message', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    @admin.action(description='إعادة محاولة المهام الفاشلة المحددة (Retry selected failed jobs)')
    def retry_selected_jobs(self, request, queryset):
        retried_count = 0
        skipped_count = 0
        for job in queryset:
            if job.status == 'failed':
                # إعادة ضبط حالة المهمة وعدد المحاولات
                job.status = 'pending'
                job.retry_count = 0
                job.error_message = None
                job.last_attempt_time = None
                job.permanently_failed = False
                job.save(update_fields=['status', 'retry_count', 'error_message', 'last_attempt_time', 'permanently_failed'])

                task_args = [job.id]
                task_kwargs = {}
                countdown = max(0, 10 - job.priority)

                celery_options = {
                    'priority': job.priority,  # Keep this for reference
                    'retry_policy': {
                        'max_retries': job.max_retries,
                    },
                    'countdown': countdown  # Add countdown based on priority
                 }
                if job.scheduled_time and job.scheduled_time > timezone.now():
                    celery_options['eta'] = job.scheduled_time

                process_job_task.apply_async(
                    args=task_args,
                    kwargs=task_kwargs,
                    **celery_options
                )
                retried_count += 1
            else:
                skipped_count += 1

        if retried_count:
            self.message_user(request, f'تمت إعادة جدولة {retried_count} مهمة فاشلة بنجاح.', messages.SUCCESS)
        if skipped_count:
            self.message_user(request, f'تم تخطي {skipped_count} مهمة لأنها ليست في حالة "فشل".', messages.WARNING)

    @admin.action(description='جعل المهام المكتملة تفشل')
    def fail_completed_jobs(self, request, queryset):
        """
        أكشن لتحويل المهام المكتملة إلى حالة فاشلة مع تسجيل عدد المحاولات
        """
        count = 0 
        for job in queryset:
            if job.status == 'completed':  
                # job.status = 'failed'  
                # job.retry_count += 1  
                # job.save(update_fields=['status', 'retry_count'])
                # count += 1
                test_failure_task.apply_async(
                  args=[job.id],
                  kwargs={},
                  countdown=0
                 )
                 
                dlq_entries = DeadLetterQueue.objects.filter(original_job=job)
        
                if dlq_entries.exists():
                  self.stdout.write(self.style.SUCCESS(f"Success! Job {queryset.id} was added to the Dead Letter Queue."))
                  for entry in dlq_entries:
                      self.stdout.write(f"DLQ Entry ID: {entry.id}")
                      self.stdout.write(f"Error Message: {entry.error_message[:100]}...")
                else:
                    self.stdout.write(self.style.ERROR(f"Error! Job {queryset.id} was NOT added to the Dead Letter Queue."))
                    self.stdout.write("Check the worker logs for more information.")

                       
        self.message_user(request, f"تم تحويل {count} مهمة إلى فاشلة")  # إظهار رسالة للمستخدم بعد التحديث

@admin.register(DeadLetterQueue)
class DeadLetterQueueAdmin(admin.ModelAdmin):
    list_display = ('id', 'task_name', 'original_job', 'created_at', 'reprocessed', 'notification_sent')
    list_filter = ('reprocessed', 'notification_sent', 'created_at')
    search_fields = ('task_name', 'task_id', 'error_message')
    readonly_fields = ('task_id', 'task_name', 'error_message', 'traceback', 'args', 'kwargs',
                       'created_at', 'notification_sent')
    actions = ['reprocess_selecte_tasks', 'send_notifications_for_selected_tasks']

    fieldsets = (
        (None, {
            'fields': ('original_job', 'task_name', 'task_id')
        }),
        ('Error Details', {
            'fields': ('error_message', 'traceback'),
            'classes': ('collapse',)
        }),
        ('Task Details', {
            'fields': ('args', 'kwargs'),
            'classes': ('collapse',)
        }),
        ('Status', {
            'fields': ('reprocessed', 'reprocessed_at', 'notification_sent', 'created_at')
        }),
    )

    @admin.action(description='إعادة معالجة المهام المحددة (Reprocess selected tasks)')
    def reprocess_selected_tasks(self, request, queryset):
        """
        Admin action to reprocess selected failed tasks.
        """
        reprocessed_count = 0
        skipped_count = 0
        for dlq_entry in queryset:
            if not dlq_entry.reprocessed:
                # Queue the reprocessing task
                reprocess_failed_task.delay(dlq_entry.id)
                reprocessed_count += 1
            else:
                skipped_count += 1

        if reprocessed_count:
            self.message_user(request, f'تمت جدولة إعادة معالجة {reprocessed_count} مهمة فاشلة.', messages.SUCCESS)
        if skipped_count:
            self.message_user(request, f'تم تخطي {skipped_count} مهمة لأنها تمت إعادة معالجتها بالفعل.', messages.WARNING)

    @admin.action(description='إرسال إشعارات للمهام المحددة (Send notifications for selected tasks)')
    def send_notifications_for_selected_tasks(self, request, queryset):
        """
        Admin action to send notifications for selected failed tasks.
        """
        sent_count = 0
        skipped_count = 0
        for dlq_entry in queryset:
            if not dlq_entry.notification_sent:
                # Queue the notification task
                
                send_failure_notification.delay(dlq_entry.id)
                sent_count += 1
            else:
                skipped_count += 1

        if sent_count:
            self.message_user(request, f'تم إرسال إشعارات لـ {sent_count} مهمة فاشلة.', messages.SUCCESS)
        if skipped_count:
            self.message_user(request, f'تم تخطي {skipped_count} مهمة لأنه تم إرسال إشعارات لها بالفعل.', messages.WARNING)
