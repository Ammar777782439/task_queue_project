

from django.db import models # عشان نعرف الجداول (المودلز) والحقول حقها
from django.utils import timezone # عشان نتعامل مع الوقت، زي وقت إنشاء السجل

# هذا الموديل (الجدول) الرئيسي حق المهام اللي بنحطها في الطابور
class Job(models.Model):
    # هذي الخيارات المتاحة لحالة المهمة، عشان نختار منها بس
    STATUS_CHOICES = [
        ('pending', 'معلقة'), # المهمة لسا ما بدأت
        ('in_progress', 'قيد التنفيذ'), # المهمة شغالة حالياً
        ('completed', 'اكتملت'), # المهمة خلصت بنجاح
        ('failed', 'فشلت'), # المهمة فشلت وما قدرنا نكملها
    ]

    # اسم المهمة، عشان نعرف ايش تسوي (نص عادي، أقصى طول 255 حرف)
    task_name = models.CharField(max_length=255, help_text="اسم وصفي للمهمة (مثلاً: إرسال النشرة الإخبارية).")
    # أولوية المهمة (رقم صحيح، الافتراضي صفر)
    # كلما زاد الرقم، زادت الأولوية (يعني تشتغل قبل غيرها)
    # ملاحظة: لازم الوسيط (زي RabbitMQ أو Redis) يدعم الأولويات عشان تشتغل صح
    priority = models.IntegerField(default=0, help_text="أولوية المهمة (قيمة أعلى تعني أولوية أعلى، يتطلب دعم الوسيط).")
    # حالة المهمة الحالية (نص، أقصى طول 20 حرف)
    # نختار من الخيارات اللي عرفناها فوق (STATUS_CHOICES)، والافتراضي 'pending'
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        help_text="الحالة الحالية للمهمة (معلقة، قيد التنفيذ، مكتملة، فشلت)."
    )
    # كم مرة حاولنا نعيد تشغيل المهمة بعد ما فشلت (رقم صحيح، الافتراضي صفر)
    retry_count = models.IntegerField(default=0, help_text="عدد المرات التي تمت فيها إعادة محاولة المهمة بعد الفشل.")
    # أقصى عدد مرات مسموح نعيد فيها المحاولة (رقم صحيح، الافتراضي 3)
    max_retries = models.IntegerField(default=3, help_text="الحد الأقصى لعدد مرات إعادة المحاولة المسموح بها للمهمة.")
    # الوقت اللي نشتي المهمة تشتغل فيه لو حبينا نأجلها (تاريخ ووقت)
    # ممكن يكون فاضي (null=True) ومش مطلوب (blank=True)
    scheduled_time = models.DateTimeField(null=True, blank=True, help_text="الوقت المجدول لتنفيذ المهمة (إذا كانت مؤجلة).")
    # متى كانت آخر مرة حاولنا ننفذ فيها المهمة (تاريخ ووقت)
    # ممكن يكون فاضي
    last_attempt_time = models.DateTimeField(null=True, blank=True, help_text="وقت آخر محاولة لتنفيذ المهمة.")
    # رسالة الخطأ لو المهمة فشلت (نص طويل)
    # ممكن يكون فاضي
    error_message = models.TextField(blank=True, null=True, help_text="رسالة الخطأ في حال فشل المهمة.")
    # متى أنشأنا سجل المهمة هذا أول مرة (تاريخ ووقت، يتسجل تلقائياً أول ما نضيفه)
    created_at = models.DateTimeField(auto_now_add=True, help_text="وقت إنشاء سجل المهمة.")
    # متى آخر مرة عدلنا فيها على سجل المهمة هذا (تاريخ ووقت، يتحدث تلقائياً كلما عدلنا)
    updated_at = models.DateTimeField(auto_now=True, help_text="وقت آخر تحديث لسجل المهمة.")
    # علامة (صح/خطأ) عشان نعرف إذا المهمة فشلت فشل نهائي بعد كل المحاولات (الافتراضي خطأ)
    permanently_failed = models.BooleanField(default=False, help_text="يشير إلى ما إذا كانت المهمة قد فشلت نهائيًا بعد كل المحاولات.")

    # --- حقول تتبع وقت التنفيذ ---
    # متى بدأ العامل بتنفيذ المهمة لأول مرة (تاريخ ووقت)
    started_at = models.DateTimeField(null=True, blank=True, help_text="وقت بدء تنفيذ المهمة الفعلي.")
    # متى اكتملت المهمة بنجاح (تاريخ ووقت)
    completed_at = models.DateTimeField(null=True, blank=True, help_text="وقت اكتمال المهمة بنجاح.")
    # المدة المستغرقة لتنفيذ المهمة (الفرق بين الانتهاء والبدء)
    execution_duration = models.DurationField(null=True, blank=True, help_text="المدة المستغرقة لتنفيذ المهمة (من البدء إلى الاكتمال).")

    # هذي الدالة تحدد كيف يظهر اسم المهمة لما نطبعها أو نشوفها في لوحة التحكم
    def __str__(self):
        # بنرجع اسم المهمة وحالتها
        return f"{self.task_name} - {self.status}"

    # ممكن نضيف هنا دوال ثانية خاصة بالمهمة لو احتجنا، مثلاً دالة تحسب كم باقي وقت على جدولتها


# هذا الموديل (الجدول) حق قائمة المهام الميتة (Dead Letter Queue)
# بنخزن فيه المهام اللي فشلت فشل نهائي وما قدرنا نعالجها
class DeadLetterQueue(models.Model):
    """موديل لتخزين المهام الفاشلة اللي ما قدرنا نعالجها بعد عدة محاولات."""

    # رابط للمهمة الأصلية اللي فشلت (علاقة واحد لمتعدد مع جدول Job)
    # لو انحذفت المهمة الأصلية، نخلي هذا الحقل فاضي (SET_NULL)
    # ممكن يكون فاضي
    # related_name هو الاسم اللي نستخدمه عشان نوصل لسجلات القائمة الميتة من سجل المهمة الأصلية
    original_job = models.ForeignKey(Job, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='dead_letter_entries',
                                    help_text="المهمة الأصلية التي فشلت.")
    # الـ ID حق المهمة في Celery (نص، أقصى طول 255)
    task_id = models.CharField(max_length=255, help_text="معرف المهمة في Celery.")
    # اسم المهمة (نص، أقصى طول 255)
    task_name = models.CharField(max_length=255, help_text="اسم المهمة.")
    # رسالة الخطأ اللي سببت الفشل (نص طويل، مطلوب)
    error_message = models.TextField(help_text="رسالة الخطأ التي تسببت في فشل المهمة.")
    # تفاصيل الخطأ (Traceback) (نص طويل، ممكن يكون فاضي)
    traceback = models.TextField(blank=True, null=True, help_text="تتبع الاستدعاء للخطأ (Traceback).")
    # الوسائط (arguments) اللي استخدمتها المهمة لما فشلت (نص طويل، نخزنها كـ JSON عادةً)
    args = models.TextField(blank=True, null=True, help_text="وسائط المهمة (عادةً بصيغة JSON).")
    # الوسائط المفتاحية (keyword arguments) اللي استخدمتها المهمة (نص طويل، نخزنها كـ JSON عادةً)
    kwargs = models.TextField(blank=True, null=True, help_text="وسائط المهمة المسماة (عادةً بصيغة JSON).")
    # متى انضافت المهمة هذي للقائمة الميتة (تاريخ ووقت، الافتراضي هو الوقت الحالي)
    created_at = models.DateTimeField(default=timezone.now, help_text="وقت إضافة المهمة إلى قائمة انتظار الرسائل الميتة.")
    # علامة (صح/خطأ) عشان نعرف إذا حاولنا نعيد معالجة المهمة هذي من القائمة الميتة (الافتراضي خطأ)
    reprocessed = models.BooleanField(default=False, help_text="هل تمت إعادة معالجة المهمة؟")
    # متى تمت إعادة معالجة المهمة (تاريخ ووقت، ممكن يكون فاضي)
    reprocessed_at = models.DateTimeField(null=True, blank=True, help_text="وقت إعادة معالجة المهمة.")
    # علامة (صح/خطأ) عشان نعرف إذا أرسلنا إشعار بفشل المهمة هذي (الافتراضي خطأ)
    notification_sent = models.BooleanField(default=False, help_text="هل تم إرسال إشعار بفشل المهمة؟")

    # هذي معلومات إضافية للموديل عشان تظهر بشكل أفضل في لوحة التحكم
    class Meta:
        verbose_name = "مهمة فاشلة (DLQ)" # الاسم المفرد للموديل بالعربي
        verbose_name_plural = "المهام الفاشلة (DLQ)" # الاسم الجمع للموديل بالعربي
        ordering = ['-created_at'] # نرتب السجلات بحيث الأحدث تظهر أول

    # كيف يظهر اسم السجل هذا لما نطبعها أو نشوفها
    def __str__(self):
        # بنرجع اسم المهمة والـ ID حقها
        return f"مهمة فاشلة: {self.task_name} ({self.task_id})"
