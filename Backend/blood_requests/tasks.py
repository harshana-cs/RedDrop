from datetime import timedelta

from celery import shared_task
from django.contrib.auth.models import User
from django.utils import timezone

from adminpanel.models import Notification
from blood_requests.models import BloodRequest


@shared_task
def send_day_before_reminders():
    """Notify patients one day before and start matching for scheduled approved requests."""
    tomorrow = timezone.localdate() + timedelta(days=1)

    requests = BloodRequest.objects.filter(
        required_date=tomorrow,
        fulfilled=False,
        status__in=["pending", "approved"],
    ).select_related("patient", "hospital_location")

    for req in requests:
        patient = req.patient
        if not patient or not patient.emailaddress:
            continue

        patient_user = User.objects.filter(username=patient.emailaddress).first()
        hospital_name = req.hospital_location.name if req.hospital_location else "your selected hospital"

        if patient_user:
            already = Notification.objects.filter(
                user=patient_user,
                blood_request=req,
                type="day_before_request_confirm",
                title="Blood Needed Tomorrow - Please Confirm",
                created_at__date=timezone.localdate(),
            ).exists()
            if not already:
                Notification.objects.create(
                    user=patient_user,
                    blood_request=req,
                    title="Blood Needed Tomorrow - Please Confirm",
                    message=(
                        f"You requested {req.blood_type} blood at {hospital_name} for tomorrow. "
                        "Do you still confirm this request?"
                    ),
                    type="day_before_request_confirm",
                )

        if req.status == "approved":
            try:
                from celery_task import orchestrate_tiered_notification
                orchestrate_tiered_notification.delay(req.id)
            except Exception:
                pass

    return f"Processed day-before reminders for {requests.count()} request(s)."
