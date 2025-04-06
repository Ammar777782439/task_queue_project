from django import forms
from .models import Job

class CreateJobForm(forms.Form):
    task_name = forms.CharField(
        max_length=255,
        required=True,
        label="Task Name",
        widget=forms.TextInput(attrs={'placeholder': 'e.g., Send Newsletter'})
    )
    priority = forms.IntegerField(
        initial=0,
        required=False,
        label="Priority",
        help_text="القيمة الأعلى تعني أولوية أعلى(supported by some brokers)."
    )
    max_retries = forms.IntegerField(
        initial=3,
        required=False,
        label="Max Retries",
        min_value=0,
        help_text="الحد الأقصى لعدد المرات التي سيتم فيها إعادة محاولة المهمة عند الفشل."
    )
    # Add fields for any specific parameters your tasks might need
    # Example:
    # email_address = forms.EmailField(required=False, label="Recipient Email (for email tasks)")

    # We don't include fields like status, retry_count etc. as they are managed internally.
    # We also don't directly use ModelForm because we want to trigger the Celery task
    # separately after creating the Job instance in the view.
