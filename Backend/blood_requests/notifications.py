from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from adminpanel.sms import send_sms

MIN_GAP_DAYS = 56

# Donor blood -> receiver blood types
BLOOD_COMPATIBILITY: dict[str, list[str]] = {
    "O-": ["O-", "O+", "A-", "A+", "B-", "B+", "AB-", "AB+"],
    "O+": ["O+", "A+", "B+", "AB+"],
    "A-": ["A-", "A+", "AB-", "AB+"],
    "A+": ["A+", "AB+"],
    "B-": ["B-", "B+", "AB-", "AB+"],
    "B+": ["B+", "AB+"],
    "AB-": ["AB-", "AB+"],
    "AB+": ["AB+"],
}


def get_compatible_donors(recipient_blood_type: str) -> list[str]:
    """
    Return donor blood groups that can donate to `recipient_blood_type`.
    """
    return [
        donor_blood
        for donor_blood, receivers in BLOOD_COMPATIBILITY.items()
        if recipient_blood_type in receivers
    ]


def is_donor_eligible(donor) -> bool:
    """
    Donor eligibility based on minimum gap between verified donations.
    """
    from donor.models import Donation

    last_donation = (
        Donation.objects.filter(donor=donor, status="verified")
        .order_by("-date")
        .first()
    )
    if not last_donation:
        return True

    next_allowed = last_donation.date + timedelta(days=MIN_GAP_DAYS)
    return timezone.now().date() >= next_allowed


def send_donor_alert(donor, blood_request, distance_km: float, *, tier: dict[str, Any] | None = None) -> dict[str, bool]:
    """
    Send SMS + Email alert to a donor, with optional tier info.
    Returns dict with channel success flags.
    """
    result = {"sms_sent": False, "email_sent": False}

    # SMS (keep short)
    sms_message = (
        f"Blood needed: {blood_request.blood_type} ({round(distance_km, 1)}km). "
        f"Login to accept. - RedDrop"
    )
    if getattr(donor, "phone_number", None):
        result["sms_sent"] = send_sms(donor.phone_number, sms_message)

    tier_text = f" (Tier {tier.get('tier')})" if tier else ""
    subject = f"RedDrop: {blood_request.blood_type} blood needed near you{tier_text}"

    hospital_name = (
        blood_request.hospital_location.name
        if getattr(blood_request, "hospital_location", None)
        else "N/A"
    )

    message = (
        f"Hi {getattr(donor, 'first_name', '')},\n\n"
        f"{blood_request.blood_type} blood is urgently needed near you.\n\n"
        f"Hospital : {hospital_name}\n"
        f"District : {blood_request.district}\n"
        f"Distance : {round(distance_km, 1)} km\n"
        f"Contact  : {blood_request.contact_phone}\n"
        f"Required By : {blood_request.required_date.strftime('%Y-%m-%d') if blood_request.required_date else 'ASAP'}\n\n"
        f"Login to donate:\n"
        f"http://localhost:5500/donor_dashboard.html\n\n"
        f"Thank you for saving lives.\n"
        f"— RedDrop Team"
    )

    if getattr(donor, "email", None):
        sent = send_mail(
            subject,
            message,
            settings.EMAIL_HOST_USER,
            [donor.email],
            fail_silently=True,
        )
        result["email_sent"] = sent > 0

    return result

