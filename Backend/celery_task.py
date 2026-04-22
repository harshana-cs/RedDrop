# =======================================================================
# celery_tasks.py   (LOCATION 6)
# =======================================================================
# Place this file at:  your_project/celery_tasks.py
# (project root — same level as manage.py)
# =======================================================================

import logging
from celery import shared_task
from django.db.models import Q
from django.utils import timezone
from django.conf import settings
from math import radians, sin, cos, sqrt, atan2

logger = logging.getLogger(__name__)

# Keep the full tier escalation within 5 minutes total.
TIER_2_DELAY_SECONDS = 60
TIER_3_DELAY_SECONDS = 60
TIER_4_DELAY_SECONDS = 60


def _queue_or_run_now(task, *, args=None, countdown=0):
    """
    Dispatch a task asynchronously in normal environments.
    In DEBUG/local development, run immediately to avoid Redis/Celery dependency.
    """
    task_args = list(args or [])
    if getattr(settings, "DEBUG", False):
        task.run(*task_args)
        return
    task.apply_async(args=task_args, countdown=countdown)

# ─── Distance helper ───────────────────────────────────────────────────
def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c


# =======================================================================
# TASK 1: orchestrate_tiered_notification
# Entry point — called from admin_approve_blood_request()
# =======================================================================
@shared_task(bind=True, max_retries=3)
def orchestrate_tiered_notification(self, blood_request_id):
    """
    Master orchestrator that kicks off the tiered escalation chain.
    Tier 1 (0-5 km) → Tier 2 (5-15 km) → Tier 3 (15-30 km) → Tier 4 (30 km+)
    Stock check runs in parallel after Tier 2.
    """
    from blood_requests.models import BloodRequest
    from adminpanel.models import BloodRequestEscalation
    from hospital.models import Hospital

    try:
        blood_request = BloodRequest.objects.get(id=blood_request_id)
    except BloodRequest.DoesNotExist:
        logger.error(f"❌ BloodRequest #{blood_request_id} not found")
        return

    hospital = blood_request.hospital_location

    if not hospital:
        logger.warning(f"⚠️ No hospital coordinates for request #{blood_request_id} — skipping")
        return

    if not hospital.latitude or not hospital.longitude:
        try:
            from blood_requests.utils import get_coordinates_from_osm

            lat, lon = get_coordinates_from_osm(hospital.name, hospital.district)
            if lat and lon:
                hospital.latitude = lat
                hospital.longitude = lon
                hospital.save(update_fields=["latitude", "longitude"])
                logger.info(
                    f"📍 Hospital geocoded for request #{blood_request_id}: "
                    f"{hospital.name} ({lat}, {lon})"
                )
        except Exception as exc:
            logger.warning(
                f"⚠️ Failed to geocode hospital for request #{blood_request_id}: {exc}"
            )

    if not hospital.latitude or not hospital.longitude:
        logger.warning(f"⚠️ No hospital coordinates for request #{blood_request_id} — skipping")
        return

    # Create escalation tracker
    escalation, _ = BloodRequestEscalation.objects.get_or_create(
        blood_request=blood_request,
        defaults={"hospital": hospital}
    )

    logger.info(f"🚀 Orchestrating tiered notification for request #{blood_request_id}")

    # Fire Tier 1 immediately; subsequent tiers are chained with countdown delays
    _queue_or_run_now(notify_tier_1, args=[blood_request_id])

    # 24h follow-up reminder to requester (best-effort)
    try:
        follow_up_patient_24h.apply_async(args=[blood_request_id], countdown=24 * 60 * 60)
    except Exception as exc:
        logger.warning(f"Could not schedule 24h follow-up for request #{blood_request_id}: {exc}")


# =======================================================================
# TASK 2: notify_tier_1  —  0–5 km donors
# =======================================================================
@shared_task(bind=True, max_retries=3)
def notify_tier_1(self, blood_request_id):
    """Notify donors within 0–5 km. Chains to Tier 2 after 1 minute."""
    count = _notify_tier(
        blood_request_id=blood_request_id,
        tier_label='tier_1',
        min_km=0,
        max_km=5,
    )
    logger.info(f"✅ Tier 1 done — {count} donors notified for request #{blood_request_id}")

    # Chain Tier 2 after 1 minute
    _queue_or_run_now(
        notify_tier_2,
        args=[blood_request_id],
        countdown=TIER_2_DELAY_SECONDS,
    )


# =======================================================================
# TASK 3: notify_tier_2  —  5–15 km donors
# =======================================================================
@shared_task(bind=True, max_retries=3)
def notify_tier_2(self, blood_request_id):
    """Notify donors within 5–15 km. Chains to Tier 3 + stock check."""
    from blood_requests.models import BloodRequest

    # Skip if already fulfilled
    try:
        br = BloodRequest.objects.get(id=blood_request_id)
        if br.fulfilled:
            logger.info(f"🎉 Request #{blood_request_id} already fulfilled — stopping at Tier 2")
            return
    except BloodRequest.DoesNotExist:
        return

    count = _notify_tier(
        blood_request_id=blood_request_id,
        tier_label='tier_2',
        min_km=5,
        max_km=15,
    )
    logger.info(f"✅ Tier 2 done — {count} donors notified for request #{blood_request_id}")

    # Run stock check in parallel
    _queue_or_run_now(check_blood_stock, args=[blood_request_id], countdown=0)

    # Chain Tier 3 after 1 minute
    _queue_or_run_now(
        notify_tier_3,
        args=[blood_request_id],
        countdown=TIER_3_DELAY_SECONDS,
    )


# =======================================================================
# TASK 4: notify_tier_3  —  15–30 km donors
# =======================================================================
@shared_task(bind=True, max_retries=3)
def notify_tier_3(self, blood_request_id):
    """Notify donors within 15–30 km. Chains to Tier 4 after 1 minute."""
    from blood_requests.models import BloodRequest

    try:
        br = BloodRequest.objects.get(id=blood_request_id)
        if br.fulfilled:
            logger.info(f"🎉 Request #{blood_request_id} already fulfilled — stopping at Tier 3")
            return
    except BloodRequest.DoesNotExist:
        return

    count = _notify_tier(
        blood_request_id=blood_request_id,
        tier_label='tier_3',
        min_km=15,
        max_km=30,
    )
    logger.info(f"✅ Tier 3 done — {count} donors notified for request #{blood_request_id}")

    # Chain Tier 4 after 1 minute
    _queue_or_run_now(
        notify_tier_4,
        args=[blood_request_id],
        countdown=TIER_4_DELAY_SECONDS,
    )


# =======================================================================
# TASK 5: notify_tier_4  —  30 km+ donors
# =======================================================================
@shared_task(bind=True, max_retries=3)
def notify_tier_4(self, blood_request_id):
    """Notify donors beyond 30 km. Final escalation tier."""
    from blood_requests.models import BloodRequest

    try:
        br = BloodRequest.objects.get(id=blood_request_id)
        if br.fulfilled:
            logger.info(f"🎉 Request #{blood_request_id} already fulfilled — stopping at Tier 4")
            return
    except BloodRequest.DoesNotExist:
        return

    count = _notify_tier(
        blood_request_id=blood_request_id,
        tier_label='tier_4',
        min_km=30,
        max_km=None,  # no upper bound
    )
    logger.info(f"✅ Tier 4 done — {count} donors notified for request #{blood_request_id}")

    # Mark escalation as completed
    from adminpanel.models import BloodRequestEscalation
    try:
        escalation = BloodRequestEscalation.objects.get(blood_request_id=blood_request_id)
        escalation.completed_at = timezone.now()
        escalation.save(update_fields=['completed_at'])
    except BloodRequestEscalation.DoesNotExist:
        pass

    # Finalize outcome after the full donor tier scan (and stock check) completes.
    # Gives stock check some time to finish if it’s still running.
    _queue_or_run_now(finalize_escalation, args=[blood_request_id], countdown=30)


# =======================================================================
# TASK 6: check_blood_stock
# Checks blood bank + hospital stock and logs results
# =======================================================================
@shared_task(bind=True, max_retries=2)
def check_blood_stock(self, blood_request_id):
    """
    Check blood bank and nearby hospital stock.
    Updates BloodRequestEscalation with findings.
    """
    from blood_requests.models import BloodRequest
    from blood_stock.models import BloodStock
    from adminpanel.models import BloodRequestEscalation
    from hospital.models import Hospital

    try:
        blood_request = BloodRequest.objects.get(id=blood_request_id)
    except BloodRequest.DoesNotExist:
        return

    blood_type = blood_request.blood_type

    try:
        escalation = BloodRequestEscalation.objects.get(blood_request=blood_request)
    except BloodRequestEscalation.DoesNotExist:
        logger.warning(f"⚠️ Escalation record not found for request #{blood_request_id}")
        return

    # ── Check Blood Bank ─────────────────────────────────────────────
    bank_stock = BloodStock.objects.filter(
        hospital__isnull=True,
        blood_type=blood_type
    ).first()

    bank_units = bank_stock.units if bank_stock else 0
    bank_found = bank_units > 0

    escalation.blood_bank_checked = timezone.now()
    escalation.blood_bank_stock_found = bank_found
    escalation.blood_bank_units = bank_units

    logger.info(
        f"🏦 Blood Bank stock for {blood_type}: {bank_units} units "
        f"({'available' if bank_found else 'none'})"
    )

    # ── Check Hospital Stock ─────────────────────────────────────────
    hospital_stocks = BloodStock.objects.filter(
        hospital__isnull=False,
        blood_type=blood_type,
        units__gt=0
    ).select_related('hospital')

    hospital_details = {}
    for hs in hospital_stocks:
        hospital_details[hs.hospital.name] = {
            "units": hs.units,
            "district": getattr(getattr(hs.hospital, 'profile', None), 'district', None)
        }

    escalation.hospital_stock_checked = timezone.now()
    escalation.hospital_stock_found = bool(hospital_details)
    escalation.hospital_stock_details = hospital_details

    escalation.save()

    logger.info(
        f"🏥 Hospital stock for {blood_type}: "
        f"{len(hospital_details)} hospitals with available units"
    )


# =======================================================================
# PRIVATE HELPER: _notify_tier
# Does the actual donor querying, distance filtering, and alerting
# =======================================================================
def _notify_tier(blood_request_id, tier_label, min_km, max_km):
    """
    Query eligible donors in [min_km, max_km) range and send alerts.
    """
    from blood_requests.models import BloodRequest
    from blood_requests.notifications import (
        is_donor_eligible,
        get_compatible_donors,
        send_donor_alert,
    )
    from register_donor.models import Donor
    from adminpanel.models import BloodRequestEscalation, NotificationLog, Notification
    from django.contrib.auth.models import User

    try:
        blood_request = BloodRequest.objects.get(id=blood_request_id)
    except BloodRequest.DoesNotExist:
        return 0

    hospital = blood_request.hospital_location
    if not hospital or not hospital.latitude or not hospital.longitude:
        logger.warning(f"No hospital coords for request #{blood_request_id}")
        return 0

    compatible_groups = get_compatible_donors(blood_request.blood_type)
    donors = Donor.objects.filter(
        is_approved=True,
        blood_type__in=compatible_groups,
    )

    if blood_request.patient:
        donors = donors.exclude(email=blood_request.patient.emailaddress)

    alerted_count = 0

    try:
        escalation = BloodRequestEscalation.objects.get(blood_request=blood_request)
        setattr(escalation, f"{tier_label}_started", timezone.now())
        escalation.save(update_fields=[f"{tier_label}_started"])
    except BloodRequestEscalation.DoesNotExist:
        escalation = None

    for donor in donors:
        if not donor.latitude or not donor.longitude:
            continue

        if not is_donor_eligible(donor):
            logger.debug(f"Donor {donor.email} in cooldown - skipping")
            continue

        distance = haversine(
            hospital.latitude, hospital.longitude,
            donor.latitude, donor.longitude
        )

        if distance < min_km:
            continue
        if max_km is not None and distance >= max_km:
            continue

        logger.info(
            f"[{tier_label}] Alerting {donor.email} | "
            f"{donor.blood_type} | {round(distance, 2)} km"
        )

        tier_info = {"tier": tier_label.replace("tier_", "")}
        channel_success = False

        try:
            alert_result = send_donor_alert(donor, blood_request, distance, tier=tier_info)
            sms_sent = bool(alert_result.get("sms_sent"))
            email_sent = bool(alert_result.get("email_sent"))

            if donor.phone_number:
                NotificationLog.objects.create(
                    blood_request=blood_request,
                    donor=donor,
                    tier=tier_label,
                    distance_km=round(distance, 2),
                    notification_type="sms",
                    status="sent" if sms_sent else "failed",
                    error_message="" if sms_sent else "SMS send returned unsuccessful status"
                )

            if donor.email:
                NotificationLog.objects.create(
                    blood_request=blood_request,
                    donor=donor,
                    tier=tier_label,
                    distance_km=round(distance, 2),
                    notification_type="email",
                    status="sent" if email_sent else "failed",
                    error_message="" if email_sent else "Email send returned unsuccessful status"
                )

            channel_success = sms_sent or email_sent
        except Exception as exc:
            logger.error(f"Alert failed for {donor.email}: {exc}")
            NotificationLog.objects.create(
                blood_request=blood_request,
                donor=donor,
                tier=tier_label,
                distance_km=round(distance, 2),
                notification_type="email",
                status="failed",
                error_message=str(exc)
            )

        donor_user = User.objects.filter(
            Q(email__iexact=donor.email) | Q(username__iexact=donor.email)
        ).first()

        if donor_user:
            already_notified = Notification.objects.filter(
                user=donor_user,
                blood_request=blood_request,
                type="blood_request"
            ).exists()

            if not already_notified:
                Notification.objects.create(
                    user=donor_user,
                    blood_request=blood_request,
                    title="Blood Donation Needed",
                    message=(
                        f"{blood_request.blood_type} blood needed at "
                        f"{hospital.name} ({round(distance, 1)} km away). "
                        f"Can you donate?"
                    ),
                    type="blood_request"
                )
                channel_success = True
        else:
            logger.warning(f"No Django user found for donor {donor.email}")

        if channel_success:
            alerted_count += 1

    if escalation:
        setattr(escalation, f"{tier_label}_completed", timezone.now())
        setattr(escalation, f"{tier_label}_donor_count", alerted_count)
        escalation.total_donors_alerted = escalation.total_donors_alerted + alerted_count
        escalation.save(update_fields=[
            f"{tier_label}_completed",
            f"{tier_label}_donor_count",
            "total_donors_alerted"
        ])

    return alerted_count


# =======================================================================
# TASK 7: finalize_escalation
# Determines final outcome after donor tiers + stock check.
# =======================================================================
@shared_task(bind=True, max_retries=2)
def finalize_escalation(self, blood_request_id):
    from django.contrib.auth.models import User
    from django.conf import settings
    from django.core.mail import send_mail

    from adminpanel.models import BloodRequestEscalation, Notification
    from blood_requests.models import BloodRequest

    blood_request = BloodRequest.objects.filter(id=blood_request_id).select_related("patient", "hospital_location").first()
    if not blood_request:
        return

    escalation = BloodRequestEscalation.objects.filter(blood_request=blood_request).first()
    if not escalation:
        return

    # If already completed (donor OTP or bank confirmation), mark success and stop.
    if blood_request.status == "completed":
        escalation.success = True
        if not escalation.completed_at:
            escalation.completed_at = timezone.now()
        escalation.save(update_fields=["success", "completed_at"])
        return

    # Donor accepted (still awaiting patient OTP flow)
    if blood_request.fulfilled and blood_request.accepted_donor_id:
        escalation.success = True
        if not escalation.completed_at:
            escalation.completed_at = timezone.now()
        escalation.save(update_fields=["success", "completed_at"])
        return

    # Stock available path
    stock_found = bool((escalation.blood_bank_units or 0) > 0 or escalation.hospital_stock_details)
    if stock_found:
        escalation.success = True
        if not escalation.completed_at:
            escalation.completed_at = timezone.now()
        escalation.save(update_fields=["success", "completed_at"])

        if blood_request.patient:
            patient_user = User.objects.filter(username=blood_request.patient.emailaddress).first()
            if patient_user and not Notification.objects.filter(
                user=patient_user, blood_request=blood_request, type="blood_bank_found"
            ).exists():
                Notification.objects.create(
                    user=patient_user,
                    blood_request=blood_request,
                    title="Blood Stock Found",
                    message="Blood stock was found via blood bank / nearby hospitals. Please check the dashboard for details and confirm once received.",
                    type="blood_bank_found",
                )
        return

    # No donor + no stock -> urgent failure path
    escalation.success = False
    if not escalation.completed_at:
        escalation.completed_at = timezone.now()
    escalation.save(update_fields=["success", "completed_at"])

    # Admin/system notification
    Notification.objects.create(
        title="Urgent: No donor or stock found",
        message=(
            f"Request #{blood_request.id} ({blood_request.blood_type}) could not be matched to a donor and no stock was found."
        ),
        type="system_alert",
        blood_request=blood_request,
    )

    # Patient notification + email (best-effort)
    if blood_request.patient:
        patient_user = User.objects.filter(username=blood_request.patient.emailaddress).first()
        if patient_user and not Notification.objects.filter(
            user=patient_user, blood_request=blood_request, type="blood_request_failed"
        ).exists():
            Notification.objects.create(
                user=patient_user,
                blood_request=blood_request,
                title="We could not arrange blood yet",
                message=(
                    "We alerted nearby donors and checked available stock, but we could not arrange blood at this time. "
                    "Please contact the hospital directly for emergency alternatives."
                ),
                type="blood_request_failed",
            )

        try:
            send_mail(
                subject="RedDrop: We could not arrange blood yet",
                message=(
                    f"Hi {blood_request.patient.fullname},\n\n"
                    f"We alerted donors and checked available stock for your request #{blood_request.id} ({blood_request.blood_type}), "
                    f"but we could not arrange blood at this time.\n\n"
                    f"Please contact the hospital directly for immediate support.\n\n"
                    f"— RedDrop Team"
                ),
                from_email=settings.EMAIL_HOST_USER,
                recipient_list=[blood_request.patient.emailaddress],
                fail_silently=True,
            )
        except Exception:
            pass


# =======================================================================
# TASK 8: follow_up_patient_24h
# Reminder to patient to confirm whether blood was received.
# =======================================================================
@shared_task(bind=True, max_retries=1)
def follow_up_patient_24h(self, blood_request_id):
    from django.contrib.auth.models import User
    from django.conf import settings
    from django.core.mail import send_mail

    from adminpanel.models import Notification
    from blood_requests.models import BloodRequest

    blood_request = BloodRequest.objects.filter(id=blood_request_id).select_related("patient").first()
    if not blood_request or not blood_request.patient:
        return

    # Stop if already completed
    if blood_request.status == "completed":
        return

    patient_user = User.objects.filter(username=blood_request.patient.emailaddress).first()
    if not patient_user:
        return

    if Notification.objects.filter(
        user=patient_user, blood_request=blood_request, type="follow_up_24h"
    ).exists():
        return

    Notification.objects.create(
        user=patient_user,
        blood_request=blood_request,
        title="Follow up: Did you receive the blood?",
        message=(
            "It has been 24 hours since your request was approved. "
            "If you have received the blood, please confirm in your dashboard. If not, keep this request active."
        ),
        type="follow_up_24h",
    )

    try:
        send_mail(
            subject="RedDrop: Follow-up on your blood request",
            message=(
                f"Hi {blood_request.patient.fullname},\n\n"
                "Did you receive the blood?\n"
                "If yes, please open your dashboard and confirm receipt.\n\n"
                "— RedDrop Team"
            ),
            from_email=settings.EMAIL_HOST_USER,
            recipient_list=[blood_request.patient.emailaddress],
            fail_silently=True,
        )
    except Exception:
        pass
