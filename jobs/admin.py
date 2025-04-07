from django.contrib import admin, messages
from .models import Job, DeadLetterQueue
from .tasks import process_job_task, reprocess_failed_task # Import the tasks
from django.utils import timezone # Import timezone


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ('id', 'task_name', 'status', 'permanently_failed', 'priority', 'retry_count', 'created_at', 'last_attempt_time') # Added permanently_failed
    list_filter = ('status', 'permanently_failed', 'priority', 'created_at') # Added permanently_failed
    search_fields = ('id', 'task_name', 'status')
    ordering = ('-created_at',)
    readonly_fields = ('status', 'retry_count', 'last_attempt_time', 'error_message', 'created_at', 'updated_at', 'permanently_failed') # Added permanently_failed
    list_per_page = 25
    actions = ['retry_selected_jobs'] # Add custom action

    fieldsets = (
        (None, {
            'fields': ('task_name', 'priority', 'max_retries', 'scheduled_time')
        }),
        ('Status & Tracking', {
            'fields': ('status', 'permanently_failed', 'retry_count', 'last_attempt_time', 'error_message', 'created_at', 'updated_at'), # Added permanently_failed
            'classes': ('collapse',) # Keep this section collapsed by default
        }),
    )

    @admin.action(description='إعادة محاولة المهام الفاشلة المحددة (Retry selected failed jobs)')
    def retry_selected_jobs(self, request, queryset):
        """
        Admin action to reset and requeue selected failed jobs.
        """
        retried_count = 0
        skipped_count = 0
        for job in queryset:
            if job.status == 'failed':
                # Reset job status and retry count
                job.status = 'pending'
                job.retry_count = 0
                job.error_message = None # Clear previous error
                job.last_attempt_time = None # Clear last attempt time
                job.permanently_failed = False # Reset the permanent failure flag
                job.save(update_fields=['status', 'retry_count', 'error_message', 'last_attempt_time', 'permanently_failed']) # Added permanently_failed

                # Prepare Celery task arguments and options
                task_args = [job.id]
                task_kwargs = {}

                # Calculate countdown based on priority (higher priority = lower countdown)
                # Max priority (10) gets 0 seconds, lowest priority (0) gets 10 seconds
                countdown = max(0, 10 - job.priority)

                celery_options = {
                    'priority': job.priority,  # Keep this for reference
                    'retry_policy': {
                        'max_retries': job.max_retries,
                    },
                    'countdown': countdown  # Add countdown based on priority
                }
                # Use 'eta' if scheduled_time is set and in the future
                if job.scheduled_time and job.scheduled_time > timezone.now():
                    celery_options['eta'] = job.scheduled_time

                # Requeue the job
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


@admin.register(DeadLetterQueue)
class DeadLetterQueueAdmin(admin.ModelAdmin):
    list_display = ('id', 'task_name', 'original_job', 'created_at', 'reprocessed', 'notification_sent')
    list_filter = ('reprocessed', 'notification_sent', 'created_at')
    search_fields = ('task_name', 'task_id', 'error_message')
    readonly_fields = ('task_id', 'task_name', 'error_message', 'traceback', 'args', 'kwargs',
                       'created_at', 'notification_sent')
    actions = ['reprocess_selected_tasks', 'send_notifications_for_selected_tasks']

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
                from .tasks import send_failure_notification
                send_failure_notification.delay(dlq_entry.id)
                sent_count += 1
            else:
                skipped_count += 1

        if sent_count:
            self.message_user(request, f'تم إرسال إشعارات لـ {sent_count} مهمة فاشلة.', messages.SUCCESS)
        if skipped_count:
            self.message_user(request, f'تم تخطي {skipped_count} مهمة لأنه تم إرسال إشعارات لها بالفعل.', messages.WARNING)
