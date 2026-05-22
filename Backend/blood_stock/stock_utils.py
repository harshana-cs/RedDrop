from __future__ import annotations

from datetime import timedelta
from typing import Iterable

from django.utils import timezone

from adminpanel.models import Notification


BLOOD_TYPES = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]


def is_expired(expiry_date) -> bool:
    if not expiry_date:
        return False
    return expiry_date < timezone.localdate()

def is_nearing_expiry(expiry_date, *, days: int = 5, today=None) -> bool:
    """
    True when expiry_date is within the next `days` days (inclusive) and not already expired.
    Used for "expiry coming near 5 days" monitoring.
    """
    if not expiry_date:
        return False
    if today is None:
        today = timezone.localdate()
    if expiry_date < today:
        return False
    return expiry_date <= (today + timedelta(days=int(days)))


def available_units(stock) -> int:
    if not stock:
        return 0
    if is_expired(stock.expiry_date):
        return 0
    return max(int(stock.units or 0), 0)


def stock_state(stock) -> dict:
    units = available_units(stock)
    minimum_required = int(getattr(stock, "minimum_required", 10) or 10) if stock else 10
    return {
        "units": units,
        "minimum_required": minimum_required,
        "expired": bool(stock and is_expired(stock.expiry_date)),
        "scarcity": units < minimum_required,
        "unavailable": units <= 0,
    }


def notify_stock_scarcity_for_hospital(hospital, scarce_types: Iterable[str], unavailable_types: Iterable[str]) -> None:
    scarce_types = sorted(set(scarce_types))
    unavailable_types = sorted(set(unavailable_types))
    if not scarce_types and not unavailable_types:
        return

    today = timezone.localdate()
    scarcity_label = ", ".join(scarce_types)
    unavailable_label = ", ".join(unavailable_types)

    title = "Blood Stock Scarcity Alert"
    message = (
        f"Scarcity detected for hospital {hospital.name}. "
        f"Low/critical blood types: {scarcity_label or 'None'}. "
        f"Unavailable blood types: {unavailable_label or 'None'}."
    )

    already_hospital = Notification.objects.filter(
        hospital=hospital,
        type="system_alert",
        title=title,
        created_at__date=today,
    ).exists()
    if not already_hospital:
        Notification.objects.create(
            hospital=hospital,
            title=title,
            message=message,
            type="system_alert",
        )

    already_admin = Notification.objects.filter(
        hospital__isnull=True,
        user__isnull=True,
        type="system_alert",
        title=title,
        created_at__date=today,
        message__icontains=hospital.name,
    ).exists()
    if not already_admin:
        Notification.objects.create(
            title=title,
            message=message,
            type="system_alert",
        )


def notify_stock_expiry_for_hospital(hospital, expiring_rows: Iterable[dict], *, days: int = 5) -> None:
    """
    Creates a daily notification when any in-stock blood unit(s) are nearing expiry.
    Sends one notification for the hospital and one for admins (system-level).
    """
    rows = list(expiring_rows or [])
    if not rows:
        return

    today = timezone.localdate()
    title = "Blood Expiry Alert"

    # Hospital-specific notification (once per day)
    already_hospital = Notification.objects.filter(
        hospital=hospital,
        type="system_alert",
        title=title,
        created_at__date=today,
    ).exists()
    if not already_hospital:
        types = ", ".join(sorted({r.get("blood_type") for r in rows if r.get("blood_type")})) or "Unknown"
        Notification.objects.create(
            hospital=hospital,
            title=title,
            message=f"Blood units nearing expiry (within {int(days)} days): {types}.",
            type="system_alert",
        )

    # Admin/system notification (once per day per hospital mention)
    already_admin = Notification.objects.filter(
        hospital__isnull=True,
        user__isnull=True,
        type="system_alert",
        title=title,
        created_at__date=today,
        message__icontains=hospital.name,
    ).exists()
    if not already_admin:
        types = ", ".join(sorted({r.get("blood_type") for r in rows if r.get("blood_type")})) or "Unknown"
        Notification.objects.create(
            title=title,
            message=f"Hospital {hospital.name} has blood units nearing expiry (within {int(days)} days): {types}.",
            type="system_alert",
        )
