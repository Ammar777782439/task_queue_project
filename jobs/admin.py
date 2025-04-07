# -*- coding: utf-8 -*-
# هانا نستدعي الحاجات اللي بنحتاجها
import time # عشان لو حبينا نسوي تأخير أو شي
from django.contrib import admin, messages # نستدعي الأدمن والرسائل عشان نعرضها للمستخدم في لوحة التحكم
from .models import Job, DeadLetterQueue # نستدعي المودلز حقنا (الجداول حق قاعدة البيانات)
from .tasks import process_job_task, reprocess_failed_task, test_failure_task  # هانا استدعينا المهام حق Celery اللي بنستخدمهن في الأكشنز تحت
from django.utils import timezone  # استدعينا التوقيت عشان نضبط جدولة المهام لو حبينا
from .tasks import send_failure_notification  # استدعاء مهمة إرسال الإشعارات حق الفشل

# سجلنا موديل Job (جدول المهام) في لوحة التحكم عشان نقدر نشوفه ونتحكم فيه
@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    # هنا بنحدد الأعمدة اللي بتظهر في القائمة الرئيسية للمهام في لوحة التحكم
    list_display = ('id', 'task_name', 'status', 'permanently_failed', 'priority', 'retry_count', 'created_at', 'last_attempt_time')
    # هذي فلاتر عشان نقدر نصفي المهام بسرعة حسب حالتها أو أولويتها أو متى انضافت
    list_filter = ('status', 'permanently_failed', 'priority', 'created_at')
    # هذي الحقول اللي نقدر نبحث فيها عن مهمة معينة
    search_fields = ('id', 'task_name', 'status')
    # نرتب المهام بحيث الأحدث تظهر أول شي
    ordering = ('-created_at',)
    # هذي الحقول ما نسمح للمستخدم يعدلها من لوحة التحكم، بس يشوفها
    readonly_fields = ('status', 'retry_count', 'last_attempt_time', 'error_message', 'created_at', 'updated_at', 'permanently_failed')
    # كم مهمة تظهر في كل صفحة من القائمة
    list_per_page = 25
    # هذي أكشنز (إجراءات) نقدر نسويها على مجموعة مهام نحددها من القائمة
    actions = ['retry_selected_jobs', 'fail_completed_jobs']

    # هانا ننظم كيف تظهر الحقول لما نفتح مهمة عشان نعدلها أو نشوف تفاصيلها
    fieldsets = (
        # القسم الأول: المعلومات الأساسية اللي يقدر المستخدم يدخلها
        (None, {
            'fields': ('task_name', 'priority', 'max_retries', 'scheduled_time') # اسم المهمة، أولويتها، أقصى محاولات، وقت جدولتها لو نشتي
        }),
        # القسم الثاني: معلومات عن حالة المهمة وتتبعها (نخليه مخفي افتراضياً عشان ما يزحم الشاشة)
        ('Status & Tracking', { # هذا عنوان القسم
            'fields': ('status', 'permanently_failed', 'retry_count', 'last_attempt_time', 'error_message', 'created_at', 'updated_at'), # الحقول اللي بتظهر فيه
            'classes': ('collapse',)  # هذا يخليه مخفي وينفتح بزر
        }),
    )

    # هذا الأكشن (الإجراء) اللي سويناه عشان نعيد محاولة تنفيذ المهام اللي فشلت
    @admin.action(description='إعادة محاولة المهام الفاشلة المحددة (Retry selected failed jobs)') # هذا الوصف اللي بيظهر في القائمة
    def retry_selected_jobs(self, request, queryset):
        """
        هذي الدالة تاخذ المهام اللي حددها المستخدم (queryset) وتعيد جدولتها لو كانت فاشلة.
        """
        retried_count = 0 # عداد للمهام اللي أعدنا جدولتها
        skipped_count = 0 # عداد للمهام اللي تخطيناها (لأنها مش فاشلة)
        # نلف على كل مهمة حددها المستخدم
        for job in queryset:
            # نتأكد إن المهمة حالتها 'failed' (فشلت)
            if job.status == 'failed':
                # بنرجع المهمة كأنها جديدة علشان نعيد معالجتها
                job.status = 'pending' # نرجع حالتها 'معلقة'
                job.retry_count = 0 # نصفر عداد المحاولات
                job.error_message = None # نمسح رسالة الخطأ القديمة
                job.last_attempt_time = None # نمسح وقت آخر محاولة
                job.permanently_failed = False # نشيل علامة الفشل النهائي
                # نحفظ التغييرات هذي بس في قاعدة البيانات
                job.save(update_fields=['status', 'retry_count', 'error_message', 'last_attempt_time', 'permanently_failed'])

                # نجهز بيانات المهمة عشان نرسلها لـ Celery مرة ثانية
                task_args = [job.id] # الوسيط الأساسي هو الـ ID حق المهمة
                task_kwargs = {} # مافيش وسائط مفتاحية هنا
                # نحسب وقت الانتظار قبل ما تبدأ المهمة، كلما زادت الأولوية قل الانتظار
                # هانا سوينا معادلة بسيطة، ممكن نغيرها بعدين
                countdown = max(0, 10 - job.priority)

                # نجهز الخيارات حق Celery
                celery_options = {
                    'priority': job.priority,  # نستخدم نفس الأولوية الأصلية
                    'retry_policy': { # سياسة إعادة المحاولة (هذي يمكن ما تشتغل مباشرة كذا، بس فكرة)
                        'max_retries': job.max_retries, # نستخدم نفس أقصى عدد محاولات
                    },
                    'countdown': countdown  # وقت الانتظار اللي حسبناه فوق
                }

                # لو كان للمهمة وقت مجدول في المستقبل، نستخدمه بدل الـ countdown
                if job.scheduled_time and job.scheduled_time > timezone.now():
                    celery_options['eta'] = job.scheduled_time # eta يعني الوقت المقدر للوصول (وقت التنفيذ)

                # نطلق المهمة (نرسلها للطابور حق Celery) باستخدام دالة process_job_task
                process_job_task.apply_async(
                    args=task_args, # الوسائط العادية
                    kwargs=task_kwargs, # الوسائط المفتاحية
                    **celery_options # باقي الخيارات (الأولوية، وقت الانتظار/الجدولة)
                )
                retried_count += 1 # نزيد عداد المهام اللي أعدنا جدولتها
            else:
                # لو المهمة مش فاشلة، نتخطاها ونزيد العداد حق التخطي
                skipped_count += 1

        # بعد ما نخلص اللفة على كل المهام، نعرض رسالة للمستخدم في لوحة التحكم
        if retried_count: # لو أعدنا جدولة أي مهمة
            self.message_user(request, f'تمت إعادة جدولة {retried_count} مهمة فاشلة بنجاح.', messages.SUCCESS) # رسالة نجاح
        if skipped_count: # لو تخطينا أي مهمة
            self.message_user(request, f'تم تخطي {skipped_count} مهمة لأنها ليست في حالة "فشل".', messages.WARNING) # رسالة تحذير

    # هذا الأكشن يحول المهام المكتملة إلى فاشلة، سويناه عشان نجرب أو لو حبينا نعيد معالجة مهمة خلصت
    @admin.action(description='جعل المهام المكتملة تفشل (Mark completed jobs as failed)') # الوصف اللي بيظهر
    def fail_completed_jobs(self, request, queryset):
        """
        هذي الدالة تاخذ المهام المكتملة اللي حددها المستخدم وتخليها تفشل عن طريق استدعاء مهمة اختبار الفشل.
        """
        count = 0 # عداد للمهام اللي حولناها لفاشلة
        # نلف على المهام المحددة
        for job in queryset:
            # نتأكد إن حالتها 'completed' (اكتملت)
            if job.status == 'completed':
                # هنا نستخدم مهمة test_failure_task اللي دايماً تفشل عشان نخلي المهمة الأصلية تفشل
                test_failure_task.apply_async(
                    args=[job.id], # نرسل الـ ID حق المهمة الأصلية
                    kwargs={}, # مافيش وسائط مفتاحية
                    countdown=0 # تبدأ على طول
                )
                count += 1 # نزيد العداد
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
    # الأعمدة اللي بتظهر في القائمة
    list_display = ('id', 'task_name', 'original_job_link', 'created_at', 'reprocessed', 'notification_sent') # أضفنا رابط للمهمة الأصلية
    # فلاتر
    list_filter = ('reprocessed', 'notification_sent', 'created_at')
    # حقول البحث
    search_fields = ('task_name', 'task_id', 'error_message', 'original_job__id', 'original_job__task_name') # أضفنا البحث في المهمة الأصلية
    # الحقول اللي للقراءة فقط
    readonly_fields = ('original_job_link', 'task_id', 'task_name', 'error_message', 'traceback_formatted', 'args', 'kwargs',
                       'created_at', 'reprocessed_at', 'notification_sent') # عدلنا شوية
    # الأكشنز المتاحة لهذا الموديل
    actions = ['reprocess_selected_tasks', 'send_notifications_for_selected_tasks']
    # ترتيب الحقول في صفحة التفاصيل/التعديل
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
