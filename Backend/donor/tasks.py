from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.db.models import Q
from django.utils import timezone

from adminpanel.models import Notification
from donor.models import Donation
from common.email_utils import send_branded_email


@shared_task
def send_donation_eligibility_reminders():
    """
    Send in-app + email reminder 5 days before donor eligibility date.
    Runs daily via Celery Beat.
    """
    today = timezone.localdate()
    reminder_for_date = today + timedelta(days=5)

    due_donations = (
        Donation.objects.select_related("donor")
        .filter(
            next_donation_date=reminder_for_date,
            status__in=["verified", "completed"],
        )
    )

    notified_count = 0

    for donation in due_donations:
        donor = donation.donor
        if not donor:
            continue

        donor_name = (f"{donor.first_name or ''} {donor.last_name or ''}").strip() or "Donor"
        reminder_message = (
            f"Hi {donor_name}, your donation eligibility date is on "
            f"{reminder_for_date.strftime('%Y-%m-%d')}. Please be ready to donate."
        )

        donor_user = User.objects.filter(
            Q(email__iexact=donor.email) | Q(username__iexact=donor.email)
        ).first()

        in_app_sent = False
        if donor_user:
            already_notified = Notification.objects.filter(
                user=donor_user,
                type="donation_eligibility_reminder",
                created_at__date=today,
                message__icontains=reminder_for_date.strftime("%Y-%m-%d"),
            ).exists()

            if not already_notified:
                Notification.objects.create(
                    user=donor_user,
                    title="Donation Eligibility Reminder",
                    message=reminder_message,
                    type="donation_eligibility_reminder",
                )
                in_app_sent = True

        email_sent = False
        if donor.email:
            sent = send_branded_email(
                subject="RedDrop: Donation Eligibility Reminder",
                to=donor.email,
                title="Donation Eligibility Reminder",
                lines=[
                    f"Hi {donor_name},",
                    "Your donation eligibility date is coming up.",
                    f"Eligibility Date: {reminder_for_date.strftime('%Y-%m-%d')}",
                ],
                footer_note="We appreciate your support in saving lives.",
                from_email=settings.EMAIL_HOST_USER,
                fail_silently=True,
            )
            email_sent = sent > 0

        if in_app_sent or email_sent:
            notified_count += 1

    return f"Sent eligibility reminders to {notified_count} donors for {reminder_for_date}"
