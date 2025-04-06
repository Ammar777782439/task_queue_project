from django.contrib import admin, messages
from .models import Job
from .tasks import process_job_task # Import the task
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
                celery_options = {
                    'priority': job.priority,  # This is used by the router to select the queue
                    'retry_policy': {
                        'max_retries': job.max_retries,
                    },
                    # Explicitly set the queue based on priority
                    'queue': f'priority_{job.priority}'
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
