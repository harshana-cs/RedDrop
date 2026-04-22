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
from math import radians, sin, cos, sqrt, atan2

logger = logging.getLogger(__name__)

# Keep the full tier escalation within 5 minutes total.
TIER_2_DELAY_SECONDS = 60
TIER_3_DELAY_SECONDS = 60
TIER_4_DELAY_SECONDS = 60

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
    notify_tier_1.delay(blood_request_id)


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
    notify_tier_2.apply_async(args=[blood_request_id], countdown=TIER_2_DELAY_SECONDS)


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
    check_blood_stock.apply_async(args=[blood_request_id], countdown=0)

    # Chain Tier 3 after 1 minute
    notify_tier_3.apply_async(args=[blood_request_id], countdown=TIER_3_DELAY_SECONDS)


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
    notify_tier_4.apply_async(args=[blood_request_id], countdown=TIER_4_DELAY_SECONDS)


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
    Updates BloodRequestEscalation with counts.
    Returns the number of donors alerted in this tier.
    """
    from blood_requests.models import BloodRequest
    from blood_requests.views import is_donor_eligible, get_compatible_donors, send_donor_alert
    from register_donor.models import Donor
    from adminpanel.models import BloodRequestEscalation, NotificationLog
    from django.contrib.auth.models import User
    from adminpanel.models import Notification

    try:
        blood_request = BloodRequest.objects.get(id=blood_request_id)
    except BloodRequest.DoesNotExist:
        return 0

    hospital = blood_request.hospital_location
    if not hospital or not hospital.latitude or not hospital.longitude:
        logger.warning(f"⚠️ No hospital coords for request #{blood_request_id}")
        return 0

    # Get compatible donor blood types
    compatible_groups = get_compatible_donors(blood_request.blood_type)

    donors = Donor.objects.filter(
        is_approved=True,
        blood_type__in=compatible_groups,
    )

    # Exclude the patient
    if blood_request.patient:
        donors = donors.exclude(email=blood_request.patient.emailaddress)

    alerted_count = 0

    # Update escalation start time for this tier
    try:
        escalation = BloodRequestEscalation.objects.get(blood_request=blood_request)
        setattr(escalation, f'{tier_label}_started', timezone.now())
        escalation.save(update_fields=[f'{tier_label}_started'])
    except BloodRequestEscalation.DoesNotExist:
        escalation = None

    for donor in donors:
        if not donor.latitude or not donor.longitude:
            continue

        if not is_donor_eligible(donor):
            logger.debug(f"  ⏳ Donor {donor.email} in cooldown — skipping")
            continue

        distance = haversine(
            hospital.latitude, hospital.longitude,
            donor.latitude, donor.longitude
        )

        # Filter by tier distance range
        if distance < min_km:
            continue
        if max_km is not None and distance >= max_km:
            continue

        logger.info(
            f"  [{tier_label}] Alerting {donor.email} | "
            f"{donor.blood_type} | {round(distance, 2)} km"
        )

        tier_info = {"tier": tier_label.replace("tier_", "")}

        # ── Send alert (SMS + email) ─────────────────────────────────
        try:
            send_donor_alert(donor, blood_request, distance, tier=tier_info)

            NotificationLog.objects.create(
                blood_request=blood_request,
                donor=donor,
                tier=tier_label,
                distance_km=round(distance, 2),
                notification_type='email',
                status='sent'
            )

            alerted_count += 1

        except Exception as e:
            logger.error(f"  ❌ Alert failed for {donor.email}: {e}")
            NotificationLog.objects.create(
                blood_request=blood_request,
                donor=donor,
                tier=tier_label,
                distance_km=round(distance, 2),
                notification_type='email',
                status='failed',
                error_message=str(e)
            )

        # ── In-app notification for donor ────────────────────────────
        donor_user = User.objects.filter(email__iexact=donor.email).first()
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

    # ── Update escalation completion stats ───────────────────────────
    if escalation:
        setattr(escalation, f'{tier_label}_completed', timezone.now())
        setattr(escalation, f'{tier_label}_donor_count', alerted_count)
        escalation.total_donors_alerted = (
            escalation.total_donors_alerted + alerted_count
        )
        escalation.save(update_fields=[
            f'{tier_label}_completed',
            f'{tier_label}_donor_count',
            'total_donors_alerted'
        ])

    return alerted_count


def _notify_tier(blood_request_id, tier_label, min_km, max_km):
    """
    Query eligible donors in [min_km, max_km) range and send alerts.
    This later definition intentionally overrides the older helper above.
    """
    from blood_requests.models import BloodRequest
    from blood_requests.views import is_donor_eligible, get_compatible_donors, send_donor_alert
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
