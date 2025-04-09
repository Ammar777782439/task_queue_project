
import time
from django.contrib import admin, messages
from django.db.models import Sum, F
from django.db.models.functions import Coalesce
import datetime
from .models import Job, DeadLetterQueue
from .tasks import process_job_task, reprocess_failed_task, test_failure_task
from django.utils import timezone
from .tasks import send_failure_notification

# سجلنا الموديل في لوحه التخكم
@admin.register(Job)
class JobAdmin(admin.ModelAdmin):

    list_display = ('id', 'task_name', 'status', 'permanently_failed', 'priority', 'retry_count', 'created_at', 'started_at', 'completed_at', 'execution_duration', 'last_attempt_time') # أضفنا حقول الوقت والمدة

    list_filter = ('status', 'permanently_failed', 'priority', 'created_at')

    search_fields = ('id', 'task_name', 'status')

    ordering = ('-created_at',)

    readonly_fields = ('status', 'retry_count', 'last_attempt_time', 'error_message', 'created_at', 'updated_at', 'permanently_failed', 'started_at', 'completed_at', 'execution_duration') # أضفنا حقول الوقت والمدة

    list_per_page = 25

    actions = ['retry_selected_jobs', 'fail_completed_jobs']

    # استخدام قوالب مخصصة للتحديث التلقائي
    # change_list_template = 'admin/jobs/job/change_list.html'
    # change_form_template = 'admin/jobs/job/change_form.html'


    fieldsets = (

        (None, {
            'fields': ('task_name', 'priority', 'max_retries', 'scheduled_time')
        }),

        ('Status & Tracking', {
            'fields': ('status', 'permanently_failed', 'retry_count', 'last_attempt_time', 'error_message', 'created_at', 'updated_at', 'started_at', 'completed_at', 'execution_duration'), # أضفنا حقول الوقت والمدة
            'classes': ('collapse',)
        }),
    )


    def save_model(self, request, obj, form, change):
        """
        تجاوز دالة حفظ الموديل عشان نرسل المهمة لـ Celery بعد إنشائها من الأدمن.
        """

        super().save_model(request, obj, form, change)


        is_new = not change

        if is_new or obj.status == 'pending':

            countdown = max(0, 10 - obj.priority)






            process_job_task.apply_async(
                args=[obj.id],
                kwargs={},
                countdown=countdown
            )


            self.message_user(
                request,
                f'تم إنشاء المهمة "{obj.task_name}" (رقم {obj.id}) وإرسالها للمعالجة.',
                messages.SUCCESS
            )

    # --- تجاوز دالة عرض القائمة لحساب المجموع ---
    # def changelist_view(self, request, extra_context=None):
    #     response = super().changelist_view(request, extra_context=extra_context)


    #     try:
    #         qs = response.context_data['cl'].queryset
    #     except (AttributeError, KeyError):

    #         return response

    #     # فلترة المهام المكتملة التي لها مدة تنفيذ
    #     completed_jobs_with_duration = qs.filter(status='completed', execution_duration__isnull=False)

    #     # حساب مجموع مدد التنفيذ
    #     # نستخدم Coalesce لضمان أن المجموع يكون timedelta(0) إذا لم تكن هناك مهام مطابقة بدلاً من None
    #     total_duration_aggregate = completed_jobs_with_duration.aggregate(
    #         total_duration=Coalesce(Sum('execution_duration'), datetime.timedelta(0))
    #     )
    #     total_duration = total_duration_aggregate['total_duration']

    #     # --- عرض المجموع كرسالة للمستخدم ---

    #     total_seconds = int(total_duration.total_seconds())
    #     hours, remainder = divmod(total_seconds, 3600)
    #     minutes, seconds = divmod(remainder, 60)
    #     duration_str = f"{hours} ساعة, {minutes} دقيقة, {seconds} ثانية"

    #     # # عرض الرسالة في أعلى الصفحة
    #     # self.message_user(
    #     #     request,
    #     #     f"إجمالي وقت التنفيذ للمهام المكتملة المعروضة: {duration_str}",
    #     #     level=messages.INFO # مستوى الرسالة (معلومات)
    #     # )
    #     # # --- نهاية عرض الرسالة ---


    #     return response



    # هذا الأكشن (الإجراء) اللي سويناه عشان نعيد محاولة تنفيذ المهام اللي فشلت
    @admin.action(description='إعادة محاولة المهام الفاشلة المحددة (Retry selected failed jobs)') # هذا الوصف اللي بيظهر في القائمة
    def retry_selected_jobs(self, request, queryset):
        """
        هذي الدالة تاخذ المهام اللي حددها المستخدم (queryset) وتعيد جدولتها لو كانت فاشلة.
        """
        retried_count = 0
        skipped_count = 0

        for job in queryset:

            if job.status == 'failed':

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
                    'priority': job.priority,
                    'retry_policy': { # سياسة إعادة المحاولة (هذي يمكن ما تشتغل مباشرة كذا، بس فكرة)
                        'max_retries': job.max_retries, # نستخدم نفس أقصى عدد محاولات
                    },
                    'countdown': countdown  # وقت الانتظار اللي حسبناه فوق
                }

                # لو كان للمهمة وقت مجدول في المستقبل، نستخدمه بدل الـ countdown
                if job.scheduled_time and job.scheduled_time > timezone.now():
                    celery_options['eta'] = job.scheduled_time


                process_job_task.apply_async(
                    args=task_args,
                    kwargs=task_kwargs,
                    **celery_options #
                )
                retried_count += 1
            else:

                skipped_count += 1

        # بعد ما نخلص اللفة على كل المهام، نعرض رسالة للمستخدم في لوحة التحكم
        if retried_count:
            self.message_user(request, f'تمت إعادة جدولة {retried_count} مهمة فاشلة بنجاح.', messages.SUCCESS) # رسالة نجاح
        if skipped_count:
            self.message_user(request, f'تم تخطي {skipped_count} مهمة لأنها ليست في حالة "فشل".', messages.WARNING) # رسالة تحذير

    # هذا الأكشن يحول المهام المكتملة إلى فاشلة، سويناه عشان نجرب أو لو حبينا نعيد معالجة مهمة خلصت
    @admin.action(description='جعل المهام المكتملة تفشل (Mark completed jobs as failed)') # الوصف اللي بيظهر
    def fail_completed_jobs(self, request, queryset):
        """
        هذي الدالة تاخذ المهام المكتملة اللي حددها المستخدم وتخليها تفشل عن طريق استدعاء مهمة اختبار الفشل.
        """
        count = 0

        for job in queryset:

            if job.status == 'completed':

                test_failure_task.apply_async(
                    args=[job.id],
                    kwargs={},
                    countdown=0
                )
                count += 1

                # ملاحظة: الكود الأصلي كان يغير الحالة مباشرة هنا، بس الأفضل نستخدم مهمة الفشل عشان نختبر مسار الفشل كامل
                # job.status = 'failed'
                # job.error_message = 'Marked as failed manually by admin action.'
                # job.permanently_failed = True # أو False لو تشتي تسمح بإعادة المحاولة من الأكشن الثاني
                # job.save(update_fields=['status', 'error_message', 'permanently_failed'])

        # بعد ما نخلص، نعرض رسالة للمستخدم
        if count > 0:
            self.message_user(request, f"تم إرسال {count} مهمة مكتملة لمسار الفشل للاختبار.", messages.INFO) # رسالة معلومات
        else:
             self.message_user(request, "لم يتم تحديد أي مهام مكتملة.", messages.WARNING) # رسالة تحذير لو ما حدد شي مكتمل


# سجلنا موديل DeadLetterQueue (جدول المهام الميتة) في لوحة التحكم
@admin.register(DeadLetterQueue)
class DeadLetterQueueAdmin(admin.ModelAdmin):

    list_display = ('id', 'task_name', 'original_job_link', 'created_at', 'reprocessed', 'notification_sent') # أضفنا رابط للمهمة الأصلية

    list_filter = ('reprocessed', 'notification_sent') # أضفنا فلاتر للإشعارات والمعالجة

    search_fields = ('task_name', 'task_id', 'error_message', 'original_job__id', 'original_job__task_name') # أضفنا البحث في المهمة الأصلية

    readonly_fields = ('original_job_link', 'task_id', 'task_name', 'error_message', 'traceback_formatted', 'args', 'kwargs',
                       'created_at', 'reprocessed_at', 'notification_sent') # عدلنا شوية

    actions = ['reprocess_selected_tasks', 'send_notifications_for_selected_tasks']

    # # استخدام قوالب مخصصة للتحديث التلقائي
    # change_list_template = 'admin/jobs/deadletterqueue/change_list.html'
    # change_form_template = 'admin/jobs/deadletterqueue/change_form.html'

    fieldsets = (
        # معلومات أساسية
        (None, {
            'fields': ('original_job_link', 'task_name', 'task_id') # استخدمنا الرابط بدل الحقل العادي
        }),
        # تفاصيل الخطأ (مخفي افتراضياً)
        ('Error Details', {
            'fields': ('error_message', 'traceback_formatted'), # استخدمنا الحقل المنسق للـ traceback
            'classes': ('collapse',)
        }),
        # تفاصيل المهمة (الوسائط) (مخفي افتراضياً)
        ('Task Details', {
            'fields': ('args', 'kwargs'),
            'classes': ('collapse',)
        }),
        # حالة المعالجة والإشعار
        ('Status', {
            'fields': ('reprocessed', 'reprocessed_at', 'notification_sent', 'created_at')
        }),
    )

    # دالة عشان نسوي رابط للمهمة الأصلية في القائمة وفي التفاصيل
    def original_job_link(self, obj):
        from django.urls import reverse
        from django.utils.html import format_html
        if obj.original_job:
            link = reverse("admin:jobs_job_change", args=[obj.original_job.id]) # نجيب الرابط لصفحة تعديل المهمة الأصلية
            return format_html('<a href="{}">{} (ID: {})</a>', link, obj.original_job.task_name, obj.original_job.id) # نرجع الرابط كـ HTML
        return "No original job linked" # لو مافيش مهمة أصلية
    original_job_link.short_description = 'Original Job' # الاسم اللي بيظهر للعمود/الحقل

    # دالة عشان نعرض الـ traceback بشكل مرتب أكثر
    def traceback_formatted(self, obj):
        from django.utils.html import format_html
        return format_html('<pre>{}</pre>', obj.traceback) # نستخدم <pre> عشان يحافظ على التنسيق
    traceback_formatted.short_description = 'Traceback' # الاسم اللي بيظهر

    # هذا الأكشن لإعادة معالجة المهام اللي في قائمة Dead Letter
    @admin.action(description='إعادة معالجة المهام المحددة (Reprocess selected tasks)') # الوصف
    def reprocess_selected_tasks(self, request, queryset):
        """
        ياخذ السجلات المحددة من قائمة المهام الميتة ويحاول يعيد معالجتها.
        """
        reprocessed_count = 0 # عداد للي أعدنا معالجتها
        skipped_count = 0 # عداد للي تخطيناها
        # نلف على السجلات المحددة
        for dlq_entry in queryset:
            # نتأكد إنها ما قد أعيدت معالجتها من قبل
            if not dlq_entry.reprocessed:
                # نطلق المهمة حقت إعادة المعالجة (reprocess_failed_task) ونرسل لها الـ ID حق السجل هذا
                reprocess_failed_task.delay(dlq_entry.id)
                reprocessed_count += 1 # نزيد العداد
            else:
                # لو قد أعيدت معالجتها، نتخطاها
                skipped_count += 1

        # نعرض رسالة للمستخدم بالنتيجة
        if reprocessed_count:
            self.message_user(request, f'تمت جدولة إعادة معالجة {reprocessed_count} مهمة فاشلة.', messages.SUCCESS)
        if skipped_count:
            self.message_user(request, f'تم تخطي {skipped_count} مهمة لأنها تمت إعادة معالجتها بالفعل.', messages.WARNING)

    # هذا الأكشن يرسل إشعارات للمهام الفاشلة اللي في القائمة الميتة
    @admin.action(description='إرسال إشعارات للمهام المحددة (Send notifications for selected tasks)') # الوصف
    def send_notifications_for_selected_tasks(self, request, queryset):
        """
        ياخذ السجلات المحددة ويرسل إشعار لكل واحد منها لو ما قد اترسل له إشعار من قبل.
        """
        sent_count = 0 # عداد للي أرسلنا لها إشعار
        skipped_count = 0 # عداد للي تخطيناها
        # نلف على السجلات
        for dlq_entry in queryset:
            # نتأكد إن الإشعار ما قد اترسل
            if not dlq_entry.notification_sent:
                # نطلق مهمة إرسال الإشعار (send_failure_notification) ونرسل لها الـ ID حق السجل
                send_failure_notification.delay(dlq_entry.id)
                sent_count += 1 # نزيد العداد
            else:
                # لو قد اترسل، نتخطاها
                skipped_count += 1

        # نعرض رسالة بالنتيجة
        if sent_count:
            self.message_user(request, f'تم إرسال طلبات إشعارات لـ {sent_count} مهمة فاشلة.', messages.SUCCESS) # غيرنا الصياغة شوية
        if skipped_count:
            self.message_user(request, f'تم تخطي {skipped_count} مهمة لأنه تم إرسال إشعارات لها بالفعل.', messages.WARNING)
