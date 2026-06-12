# blood_requests/tasks.py

from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from .models import BloodRequest
from adminpanel.models import Notification
from django.contrib.auth.models import User


@shared_task
def check_unaccepted_requests():
    """
    Runs every 5 minutes.
    Finds blood requests that:
    - Are approved
    - Not fulfilled (no donor accepted)
    - Created more than 1 hour ago
    - Haven't been flagged yet
    """

    threshold_time = timezone.now() - timedelta(hours=1)

    unaccepted_requests = BloodRequest.objects.filter(
        status='approved',
        fulfilled=False,
        created_at__lte=threshold_time,
        admin_alerted=False,   # ✅ prevent duplicate alerts
    )

    for blood_request in unaccepted_requests:

        # ✅ Notify all admin users
        admin_users = User.objects.filter(is_staff=True)

        for admin in admin_users:
            Notification.objects.create(
                user=admin,
                title="⚠️ No Donor Found for Blood Request",
                message=(
                    f"Blood request #{blood_request.id} for "
                    f"{blood_request.blood_type} at "
                    f"{blood_request.hospital_location.name} "
                    f"has not been accepted by any donor in the last 1 hour. "
                    f"Please find an alternative."
                ),
                type="no_donor_alert",
                blood_request=blood_request,
            )

        # ✅ Also create a general admin log (no user)
        Notification.objects.create(
            title="⚠️ No Donor Found",
            message=(
                f"Request #{blood_request.id} ({blood_request.blood_type}) "
                f"at {blood_request.hospital_location.name} — "
                f"no donor accepted after 1 hour."
            ),
            type="no_donor_alert",
        )

        # ✅ Mark as alerted so we don't spam
        blood_request.admin_alerted = True
        blood_request.save()

    return f"Checked {unaccepted_requests.count()} unaccepted requests"