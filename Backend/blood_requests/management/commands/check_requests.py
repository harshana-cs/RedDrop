from django.core.management.base import BaseCommand
from blood_requests.models import BloodRequest
from adminpanel.models import Notification
from django.contrib.auth.models import User


class Command(BaseCommand):   # 🔥 MUST be EXACT NAME
    help = "Check expired blood requests"

    def handle(self, *args, **kwargs):

        expired_requests = BloodRequest.objects.filter(
        status="approved",
        accepted_donor__isnull=True,
        is_escalated=False
)
        admins = User.objects.filter(is_staff=True)

        for req in expired_requests:

            if req.is_expired():

                for admin in admins:
                    Notification.objects.create(
                        user=admin,
                        title="No Donor Accepted ❗",
                        message=f"Request ID {req.id} not accepted within 1 hour",
                        type="blood_request"
                    )

                req.status = "escalated"
                req.is_escalated = True
                req.save()

        self.stdout.write("Checked requests")