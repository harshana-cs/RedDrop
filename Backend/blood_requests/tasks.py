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
                type="alert",
                title="Blood Needed Tomorrow",
                created_at__date=timezone.localdate(),
            ).exists()
            if not already:
                Notification.objects.create(
                    user=patient_user,
                    blood_request=req,
                    title="Blood Needed Tomorrow",
                    message=(
                        f"Your {req.blood_type} request at {hospital_name} is needed tomorrow. "
                        "Log in to view donor and blood bank availability."
                    ),
                    type="alert",
                )

        if req.status == "approved":
            try:
                from celery_task import orchestrate_tiered_notification
                orchestrate_tiered_notification.delay(req.id)
            except Exception:
                pass

    return f"Processed day-before reminders for {requests.count()} request(s)."

