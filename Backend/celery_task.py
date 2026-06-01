# =======================================================================
# celery_task.py  (project root — same level as manage.py)
#
# Works WITHOUT Redis/Celery:
#   - Each tier runs in a background thread with a real time delay
#   - Tier 1 → wait 75s → Tier 2 → wait 75s → Tier 3 → wait 75s → Tier 4
#   - Total: ~5 minutes across all 4 tiers
#   - Each tier checks if the request was already fulfilled before running
#   - Stock is polled repeatedly during each tier so newly uploaded stock is caught
#   - finalize_escalation runs ~30s after Tier 4
# =======================================================================

import logging
import threading
import time
from math import radians, sin, cos, sqrt, atan2
from common.email_utils import send_branded_email

logger = logging.getLogger(__name__)

# ── Timing (seconds between tiers) ───────────────────────────────────
# Keep donor-tier progression within ~5 minutes total wall clock.
TIER_1_DELAY   = 0    # starts immediately
TIER_2_DELAY   = 100  # keep total escalation window around 5 minutes
TIER_3_DELAY   = 100
TIER_4_DELAY   = 100
FINALIZE_DELAY = 0    # finalize immediately after Tier 4
STOCK_POLL_INTERVAL = 5  # re-check stock every 5s while a tier is running

MIN_GAP_DAYS = 56     # donor cooldown period


# ── Distance helper ───────────────────────────────────────────────────
def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


# ── Fake Celery task wrapper ──────────────────────────────────────────
class SyncTask:
    """
    Wraps a plain function so .delay() / .apply_async() work.
    .delay() runs in a background daemon thread so the HTTP response
    is returned immediately and tiers run independently.
    """
    def __init__(self, func):
        self.func = func
        self.__name__ = func.__name__

    def delay(self, *args, **kwargs):
        t = threading.Thread(target=self._run, args=args, kwargs=kwargs, daemon=True)
        t.start()

    def apply_async(self, args=None, kwargs=None, countdown=0, **extra):
        def _run():
            if countdown:
                time.sleep(countdown)
            self._run(*(args or []), **(kwargs or {}))
        threading.Thread(target=_run, daemon=True).start()

    def _run(self, *args, **kwargs):
        try:
            self.func(*args, **kwargs)
        except Exception as exc:
            logger.error(f"[SyncTask] {self.__name__} failed: {exc}", exc_info=True)

    def run(self, *args, **kwargs):
        return self.func(*args, **kwargs)

    def __call__(self, *args, **kwargs):
        return self.func(*args, **kwargs)


def shared_task(bind=False, max_retries=3):
    """Drop-in @shared_task decorator shim — no Celery needed."""
    def decorator(func):
        return SyncTask(func)
    return decorator


# ── Fulfillment check ─────────────────────────────────────────────────
def _is_already_fulfilled(blood_request_id):
    """True if a donor already accepted the request — stops further tiers."""
    try:
        from blood_requests.models import BloodRequest
        br = BloodRequest.objects.get(id=blood_request_id)
        return br.fulfilled or br.status == "completed"
    except Exception:
        return False


def _is_stock_found(blood_request_id):
    """True when blood bank / hospital stock has been found for this request."""
    try:
        from adminpanel.models import BloodRequestEscalation
        esc = BloodRequestEscalation.objects.get(blood_request_id=blood_request_id)
        return (esc.blood_bank_units or 0) > 0 or bool(esc.hospital_stock_details)
    except Exception:
        return False


def _should_stop_search(blood_request_id):
    """Stop donor search only when donor path is fulfilled/completed."""
    return _is_already_fulfilled(blood_request_id)


def _mark_escalation_complete(blood_request_id):
    """Stamps completed_at on the escalation record."""
    from django.utils import timezone
    from adminpanel.models import BloodRequestEscalation
    try:
        esc = BloodRequestEscalation.objects.get(blood_request_id=blood_request_id)
        if not esc.completed_at:
            esc.completed_at = timezone.now()
            esc.save(update_fields=["completed_at"])
    except BloodRequestEscalation.DoesNotExist:
        pass


def _sleep_with_donor_acceptance_checks(blood_request_id, total_seconds):
    """Sleep in short intervals and stop early if the request is already fulfilled."""
    remaining = total_seconds
    while remaining > 0:
        if _should_stop_search(blood_request_id):
            return True

        chunk = min(STOCK_POLL_INTERVAL, remaining)
        time.sleep(chunk)
        remaining -= chunk

    return _should_stop_search(blood_request_id)


# =======================================================================
# TASK 1 — orchestrate_tiered_notification
# Entry point called from admin_approve_blood_request().
# Spawns ONE background thread that walks through all 4 tiers with real
# time delays, stopping early if a donor accepts during the search.
# =======================================================================
@shared_task(bind=True, max_retries=3)
def orchestrate_tiered_notification(blood_request_id):

    def _run_all_tiers():
        # Django apps must be set up in non-main threads on some servers
        try:
            import django
            django.setup()
        except RuntimeError:
            pass  # already set up

        from blood_requests.models import BloodRequest
        from adminpanel.models import BloodRequestEscalation

        try:
            blood_request = BloodRequest.objects.get(id=blood_request_id)
        except BloodRequest.DoesNotExist:
            logger.error(f"[Escalation] BloodRequest #{blood_request_id} not found")
            return

        hospital = blood_request.hospital_location
        if not hospital:
            logger.warning(f"[Escalation] No hospital for request #{blood_request_id}")
            return

        # Geocode hospital if coordinates are missing
        if not hospital.latitude or not hospital.longitude:
            try:
                from blood_requests.utils import get_coordinates_from_osm
                lat, lon = get_coordinates_from_osm(
                    hospital.name, getattr(hospital, 'district', '')
                )
                if lat and lon:
                    hospital.latitude = lat
                    hospital.longitude = lon
                    hospital.save(update_fields=["latitude", "longitude"])
                    logger.info(f"[Escalation] Geocoded hospital for #{blood_request_id}")
            except Exception as exc:
                logger.warning(f"[Escalation] Geocoding failed for #{blood_request_id}: {exc}")

        if not hospital.latitude or not hospital.longitude:
            logger.warning(f"[Escalation] No coords — skipping #{blood_request_id}")
            return

        BloodRequestEscalation.objects.get_or_create(
            blood_request=blood_request,
            defaults={"hospital": blood_request.created_by_hospital}
        )

        logger.info(f"[Escalation] compatible-donor tiered search starting for #{blood_request_id}")
        # ── TIER 1: 0–5 km (immediate) ───────────────────────────────
        _notify_tier(blood_request_id, "tier_1", 0, 5)

        # ── Wait → TIER 2: 5–15 km ───────────────────────────────────
        if _sleep_with_donor_acceptance_checks(blood_request_id, TIER_2_DELAY):
            logger.info(f"[Escalation] #{blood_request_id} stopped before Tier 2 (donor accepted)")
            _mark_escalation_complete(blood_request_id)
            return
        if _should_stop_search(blood_request_id):
            logger.info(f"[Escalation] #{blood_request_id} stopped after Tier 1 (donor accepted)")
            _mark_escalation_complete(blood_request_id)
            return

        _notify_tier(blood_request_id, "tier_2", 5, 15)

        # ── Wait → TIER 3: 15–30 km ──────────────────────────────────
        if _sleep_with_donor_acceptance_checks(blood_request_id, TIER_3_DELAY):
            logger.info(f"[Escalation] #{blood_request_id} stopped before Tier 3 (donor accepted)")
            _mark_escalation_complete(blood_request_id)
            return
        if _should_stop_search(blood_request_id):
            logger.info(f"[Escalation] #{blood_request_id} stopped after Tier 2 (donor accepted)")
            _mark_escalation_complete(blood_request_id)
            return

        _notify_tier(blood_request_id, "tier_3", 15, 30)

        # ── Wait → TIER 4: 30+ km ────────────────────────────────────
        if _sleep_with_donor_acceptance_checks(blood_request_id, TIER_4_DELAY):
            logger.info(f"[Escalation] #{blood_request_id} stopped before Tier 4 (donor accepted)")
            _mark_escalation_complete(blood_request_id)
            return
        if _should_stop_search(blood_request_id):
            logger.info(f"[Escalation] #{blood_request_id} stopped after Tier 3 (donor accepted)")
            _mark_escalation_complete(blood_request_id)
            return

        _notify_tier(blood_request_id, "tier_4", 30, None)
        logger.info(f"[Escalation] All 4 tiers completed for #{blood_request_id}")

        # ── Finalize after letting stock check finish ─────────────────
        # Check stock once after the full tier window.
        check_blood_stock(blood_request_id)
        time.sleep(FINALIZE_DELAY)
        finalize_escalation(blood_request_id)

    # Launch background thread — returns immediately so HTTP response is fast
    threading.Thread(target=_run_all_tiers, daemon=True).start()
    # Safety net: if nothing is resolved after 10 minutes, mark the request incomplete.
    timeout_timer = threading.Timer(10 * 60, _mark_request_incomplete_after_timeout, args=(blood_request_id,))
    timeout_timer.daemon = True
    timeout_timer.start()
    logger.info(f"[Escalation] Background thread started for #{blood_request_id}")


# =======================================================================
# TASK 6 — check_blood_stock
# =======================================================================
@shared_task(bind=True, max_retries=2)
def check_blood_stock(blood_request_id):
    from django.utils import timezone
    from django.conf import settings
    from blood_requests.models import BloodRequest
    from blood_stock.models import BloodStock
    from adminpanel.models import BloodRequestEscalation

    try:
        blood_request = BloodRequest.objects.get(id=blood_request_id)
    except BloodRequest.DoesNotExist:
        return

    try:
        escalation = BloodRequestEscalation.objects.get(blood_request=blood_request)
    except BloodRequestEscalation.DoesNotExist:
        logger.warning(f"[StockCheck] Escalation not found for #{blood_request_id}")
        return

    blood_type = blood_request.blood_type

    # Central blood bank (hospital=None)
    bank_stock = BloodStock.objects.filter(
        hospital__isnull=True, blood_type=blood_type
    ).first()
    bank_units = bank_stock.units if bank_stock else 0

    escalation.blood_bank_checked = timezone.now()
    escalation.blood_bank_stock_found = bank_units > 0
    escalation.blood_bank_units = bank_units

    # Hospital stock
    hospital_stocks = BloodStock.objects.filter(
        hospital__isnull=False, blood_type=blood_type, units__gt=0
    ).select_related("hospital")

    hospital_details = {}
    for hs in hospital_stocks:
        profile = getattr(hs.hospital, "profile", None)
        hospital_details[hs.hospital.name] = {
            "units": hs.units,
            "district": getattr(profile, "district", None),
            "contact_phone": getattr(profile, "contact_number", None),
            "contact_email": getattr(profile, "email", None),
            "address": getattr(profile, "address", None),
        }

    escalation.hospital_stock_checked = timezone.now()
    escalation.hospital_stock_found = bool(hospital_details)
    escalation.hospital_stock_details = hospital_details
    escalation.save()

    logger.info(
        f"[StockCheck] #{blood_request_id}: bank={bank_units} units, "
        f"hospitals={len(hospital_details)}"
    )


# =======================================================================
# TASK 7 — finalize_escalation
# =======================================================================
@shared_task(bind=True, max_retries=2)
def finalize_escalation(blood_request_id):
    from django.utils import timezone
    from django.conf import settings
    from django.core.mail import send_mail
    from django.contrib.auth.models import User
    from adminpanel.models import BloodRequestEscalation, Notification
    from blood_requests.models import BloodRequest

    blood_request = BloodRequest.objects.filter(
        id=blood_request_id
    ).select_related("patient", "hospital_location").first()
    if not blood_request:
        return

    escalation = BloodRequestEscalation.objects.filter(
        blood_request=blood_request
    ).first()
    if not escalation:
        return

    # Already completed via OTP
    if blood_request.status == "completed":
        escalation.success = True
        escalation.completed_at = escalation.completed_at or timezone.now()
        escalation.save(update_fields=["success", "completed_at"])
        return

    # Donor accepted (awaiting patient OTP flow)
    if blood_request.fulfilled and blood_request.accepted_donor_id:
        escalation.success = True
        escalation.completed_at = escalation.completed_at or timezone.now()
        escalation.save(update_fields=["success", "completed_at"])
        return

    # Stock found → notify patient
    stock_found = (escalation.blood_bank_units or 0) > 0 or escalation.hospital_stock_details
    if stock_found:
        escalation.success = True
        escalation.completed_at = escalation.completed_at or timezone.now()
        escalation.save(update_fields=["success", "completed_at"])

        if blood_request.patient:
            patient_user = User.objects.filter(
                username=blood_request.patient.emailaddress
            ).first()
            if patient_user and not Notification.objects.filter(
                user=patient_user, blood_request=blood_request, type="blood_bank_found"
            ).exists():
                Notification.objects.create(
                    user=patient_user,
                    blood_request=blood_request,
                    title="Blood Stock Found",
                    message=(
                        "Blood stock was found via blood bank / nearby hospitals. "
                        "Please check the dashboard for details."
                    ),
                    type="blood_bank_found",
                )
        return

    # Nothing found
    escalation.success = False
    escalation.completed_at = escalation.completed_at or timezone.now()
    escalation.save(update_fields=["success", "completed_at"])

    Notification.objects.create(
        title="Urgent: No compatible donor or stock found",
        message=(
            f"Request #{blood_request.id} ({blood_request.blood_type}) "
            "could not be matched to a compatible donor and no stock was found."
        ),
        type="system_alert",
        blood_request=blood_request,
    )

    if blood_request.created_by_hospital_id and not Notification.objects.filter(
        hospital_id=blood_request.created_by_hospital_id,
        blood_request=blood_request,
        type="blood_request_failed"
    ).exists():
        Notification.objects.create(
            hospital_id=blood_request.created_by_hospital_id,
            blood_request=blood_request,
            title="No compatible donor or stock found after escalation",
            message=(
                f"For request #{blood_request.id} ({blood_request.blood_type}), "
                "all compatible-donor tiers completed and stock checks found no available units yet."
            ),
            type="blood_request_failed",
        )

    if blood_request.patient:
        patient_user = User.objects.filter(
            username=blood_request.patient.emailaddress
        ).first()
        if patient_user and not Notification.objects.filter(
            user=patient_user, blood_request=blood_request, type="blood_request_failed"
        ).exists():
            Notification.objects.create(
                user=patient_user,
                blood_request=blood_request,
                title="We could not arrange blood yet",
                message=(
                    "We alerted nearby donors and checked available stock, "
                    "but we could not arrange blood at this time. "
                    "Please contact the hospital directly."
                ),
                type="blood_request_failed",
            )
        try:
            send_mail(
                subject="RedDrop: We could not arrange blood yet",
                message=(
                    f"Hi {blood_request.patient.fullname},\n\n"
                    f"We alerted donors and checked stock for request "
                    f"#{blood_request.id} ({blood_request.blood_type}), "
                    "but could not arrange blood.\n\n"
                    "Please contact the hospital directly.\n\n"
                    "— RedDrop Team"
                ),
                from_email=settings.EMAIL_HOST_USER,
                recipient_list=[blood_request.patient.emailaddress],
                fail_silently=True,
            )
        except Exception:
            pass

    try:
        _broadcast_sms_to_all_donors_no_match(blood_request)
    except Exception as exc:
        logger.error(f"[BroadcastSMS-NoMatch] failed for #{blood_request.id}: {exc}")


# =======================================================================
# TIMEOUT HELPERS
# =======================================================================
def _mark_request_incomplete_after_timeout(blood_request_id):
    """
    Final safety net for unresolved approved requests.
    Marks the request incomplete once the 10-minute search window expires.
    """
    try:
        import django
        django.setup()
    except RuntimeError:
        pass
    except Exception as exc:
        logger.error(f"[Timeout] Django setup failed for #{blood_request_id}: {exc}")
        return

    from blood_requests.models import BloodRequest
    from adminpanel.models import BloodRequestEscalation, Notification
    from django.contrib.auth.models import User

    req = BloodRequest.objects.filter(id=blood_request_id).first()
    if not req or req.status in {"completed", "rejected", "incomplete"} or req.fulfilled:
        return
    if req.accepted_donor_id:
        return
    if req.approved_at and req.approved_at > timezone.now() - timedelta(minutes=10):
        return

    esc = BloodRequestEscalation.objects.filter(blood_request=req).first()
    has_stock = bool(
        esc and (
            (esc.blood_bank_units or 0) > 0
            or bool(esc.hospital_stock_details)
        )
    )
    if has_stock:
        return

    if req.status not in {"approved", "no_match"}:
        return

    req.status = "incomplete"
    req.save(update_fields=["status"])
    logger.info(f"[Timeout] Request #{req.id} marked incomplete after 10 minutes")

    if req.patient:
        patient_user = User.objects.filter(username=req.patient.emailaddress).first()
        if patient_user and not Notification.objects.filter(
            user=patient_user,
            blood_request=req,
            type="blood_request_failed",
        ).exists():
            Notification.objects.create(
                user=patient_user,
                blood_request=req,
                title="Request Marked Incomplete",
                message=(
                    "No donor or stock was confirmed within the search window, "
                    "so the request has been marked incomplete."
                ),
                type="blood_request_failed",
            )


# =======================================================================
# PRIVATE HELPER — _notify_tier
# =======================================================================
def _notify_tier(blood_request_id, tier_label, min_km, max_km):
    from django.utils import timezone
    from django.db.models import Q
    from django.contrib.auth.models import User
    from blood_requests.models import BloodRequest
    from register_donor.models import Donor
    from adminpanel.models import BloodRequestEscalation, NotificationLog, Notification

    try:
        blood_request = BloodRequest.objects.get(id=blood_request_id)
    except BloodRequest.DoesNotExist:
        return 0

    # Early exit if already fulfilled
    if _should_stop_search(blood_request_id):
        logger.info(f"[{tier_label}] #{blood_request_id} already fulfilled — skip")
        return 0

    hospital = blood_request.hospital_location
    if not hospital or not hospital.latitude or not hospital.longitude:
        logger.warning(f"[{tier_label}] No hospital coords for #{blood_request_id}")
        return 0

    compatible_groups = _get_compatible_donors(blood_request.blood_type)
    donors = Donor.objects.filter(is_approved=True, blood_type__in=compatible_groups)

    if blood_request.patient:
        donors = donors.exclude(email=blood_request.patient.emailaddress)

    try:
        escalation = BloodRequestEscalation.objects.get(blood_request=blood_request)
        setattr(escalation, f"{tier_label}_started", timezone.now())
        escalation.save(update_fields=[f"{tier_label}_started"])
    except BloodRequestEscalation.DoesNotExist:
        escalation = None

    alerted_count = 0

    for donor in donors:
        # Stop mid-tier if a donor accepted while we were looping
        if _should_stop_search(blood_request_id):
            logger.info(f"[{tier_label}] #{blood_request_id} stop condition reached mid-tier — stopping")
            break

        if not donor.latitude or not donor.longitude:
            continue
        if not _is_donor_eligible(donor):
            continue

        distance = haversine(
            hospital.latitude, hospital.longitude,
            donor.latitude, donor.longitude,
        )

        if distance < min_km:
            continue
        if max_km is not None and distance >= max_km:
            continue

        logger.info(
            f"[{tier_label}] Alerting compatible donor {donor.email} | "
            f"{donor.blood_type} | {round(distance, 2)} km"
        )

        sms_sent = False
        email_sent = False
        channel_success = False

        # ── SMS ──────────────────────────────────────────────────────
        try:
            if donor.phone_number:
                from adminpanel.sms import send_sms
                sms_sent = bool(send_sms(
                    donor.phone_number,
                    f"RedDrop: {blood_request.blood_type} blood needed at "
                    f"{hospital.name} ({round(distance, 1)} km away). Login to respond."
                ))
        except Exception as exc:
            logger.error(f"[{tier_label}] SMS failed for {donor.email}: {exc}")

        # ── Email ─────────────────────────────────────────────────────
        try:
            if donor.email:
                from django.conf import settings
                from django.core.mail import send_mail as _send_mail
                send_branded_email(
                    subject=f"RedDrop: Compatible donor request for {blood_request.blood_type}",
                    message=(
                        f"Hi {donor.first_name or 'Donor'},\n\n"
                        f"You are a compatible donor for a {blood_request.blood_type} blood request at "
                        f"{hospital.name} ({round(distance, 1)} km away).\n\n"
                        f"Urgency: {blood_request.urgency}\n"
                        f"Units needed: {blood_request.units_required}\n\n"
                        "Please login to RedDrop to accept or decline this request.\n\n"
                        "— RedDrop Team"
                    ),
                    from_email=settings.EMAIL_HOST_USER,
                    recipient_list=[donor.email],
                    fail_silently=True,
                )
                email_sent = True
        except Exception as exc:
            logger.error(f"[{tier_label}] Email failed for {donor.email}: {exc}")

        # ── Notification logs ─────────────────────────────────────────
        if donor.phone_number:
            NotificationLog.objects.create(
                blood_request=blood_request, donor=donor, tier=tier_label,
                distance_km=round(distance, 2), notification_type="sms",
                status="sent" if sms_sent else "failed",
                error_message="" if sms_sent else "SMS failed",
            )
        if donor.email:
            NotificationLog.objects.create(
                blood_request=blood_request, donor=donor, tier=tier_label,
                distance_km=round(distance, 2), notification_type="email",
                status="sent" if email_sent else "failed",
                error_message="" if email_sent else "Email failed",
            )

        # ── In-app notification ───────────────────────────────────────
        donor_user = User.objects.filter(
            Q(email__iexact=donor.email) | Q(username__iexact=donor.email)
        ).first()

        if donor_user:
            already = Notification.objects.filter(
                user=donor_user, blood_request=blood_request, type="blood_request"
            ).exists()
            if not already:
                Notification.objects.create(
                    user=donor_user,
                    blood_request=blood_request,
                    title="Blood Donation Needed",
                    message=(
                        f"{blood_request.blood_type} blood needed at "
                        f"{hospital.name} ({round(distance, 1)} km away). Can you donate?"
                    ),
                    type="blood_request",
                )
                channel_success = True
        else:
            logger.warning(f"[{tier_label}] No Django user for donor {donor.email}")

        if sms_sent or email_sent or channel_success:
            alerted_count += 1

    # Update escalation record
    if escalation:
        try:
            escalation.refresh_from_db()
            setattr(escalation, f"{tier_label}_completed", timezone.now())
            setattr(escalation, f"{tier_label}_donor_count", alerted_count)
            escalation.total_donors_alerted = (escalation.total_donors_alerted or 0) + alerted_count
            escalation.save(update_fields=[
                f"{tier_label}_completed",
                f"{tier_label}_donor_count",
                "total_donors_alerted",
            ])
        except Exception as exc:
            logger.error(f"[{tier_label}] Escalation update failed: {exc}")

    logger.info(f"[{tier_label}] Done — {alerted_count} alerted for #{blood_request_id}")
    return alerted_count


def _broadcast_sms_to_all_donors_no_match(blood_request):
    """
    Final fallback: send SMS to all approved donors regardless of blood type
    only after compatible-donor tiers and stock checks found no match.
    """
    from register_donor.models import Donor
    from adminpanel.sms import send_sms

    hospital_name = blood_request.hospital_location.name if blood_request.hospital_location else "a hospital"
    contact_phone = blood_request.contact_phone or "N/A"
    message = (
        f"RedDrop Alert: Urgent blood request #{blood_request.id} ({blood_request.blood_type}) "
        f"at {hospital_name}. All-donor SMS fallback: no compatible donor or stock match was found. "
        f"If able, contact hospital: {contact_phone}."
    )

    sent = 0
    failed = 0
    for donor in Donor.objects.filter(is_approved=True):
        phone = getattr(donor, "phone_number", None)
        if not phone:
            continue
        try:
            ok = bool(send_sms(phone, message))
            if ok:
                sent += 1
            else:
                failed += 1
        except Exception:
            failed += 1

    logger.info(f"[BroadcastSMS-NoMatch] all-donor SMS fallback for request #{blood_request.id}: sent={sent}, failed={failed}")


# ── Donor eligibility ─────────────────────────────────────────────────
def _is_donor_eligible(donor):
    from django.utils import timezone
    try:
        from donor.models import Donation
        last = (
            Donation.objects
            .filter(donor=donor, status__in=["completed", "verified"])
            .order_by("-date")
            .first()
        )
        if last:
            return (timezone.now().date() - last.date).days >= MIN_GAP_DAYS
        return True
    except Exception:
        pass
    if hasattr(donor, "last_donation_date") and donor.last_donation_date:
        from django.utils import timezone
        return (timezone.now().date() - donor.last_donation_date).days >= MIN_GAP_DAYS
    return True


# ── Blood compatibility ───────────────────────────────────────────────
_COMPAT = {
    "O-":  ["O-", "O+", "A-", "A+", "B-", "B+", "AB-", "AB+"],
    "O+":  ["O+", "A+", "B+", "AB+"],
    "A-":  ["A-", "A+", "AB-", "AB+"],
    "A+":  ["A+", "AB+"],
    "B-":  ["B-", "B+", "AB-", "AB+"],
    "B+":  ["B+", "AB+"],
    "AB-": ["AB-", "AB+"],
    "AB+": ["AB+"],
}

def _get_compatible_donors(patient_blood_type):
    """Return donor blood types that CAN donate TO the patient's blood type."""
    compatible = [bt for bt, recipients in _COMPAT.items() if patient_blood_type in recipients]
    return compatible if compatible else [patient_blood_type]


# Add this import at top of celery_task.py if not already there
from django.utils import timezone
from datetime import timedelta
import logging
logger = logging.getLogger(__name__)


def mark_no_match_requests():
    """
    Marks unresolved requests as incomplete after the no-match window.
    This mirrors the dashboard timeout so unresolved requests stop reopening.
    """
    from blood_requests.models import BloodRequest
    from adminpanel.models import BloodRequestEscalation, Notification
    from django.contrib.auth.models import User

    cutoff = timezone.now() - timedelta(minutes=10)

    candidates = BloodRequest.objects.filter(
        status='approved',
        fulfilled=False,
        accepted_donor__isnull=True,
        approved_at__lte=cutoff,
    )

    updated = []

    for req in candidates:
        esc = BloodRequestEscalation.objects.filter(
            blood_request=req
        ).first()

        # Skip if stock was found — patient still needs to confirm
        has_stock = bool(
            esc and (
                (esc.blood_bank_units or 0) > 0
                or bool(esc.hospital_stock_details)
            )
        )
        if has_stock:
            continue

        # Skip if all 4 tiers haven't completed yet — still searching
        all_tiers_done = bool(
            esc and
            esc.tier_1_completed and
            esc.tier_2_completed and
            esc.tier_3_completed and
            esc.tier_4_completed
        )
        if not all_tiers_done:
            continue

        # Mark as incomplete so the dashboard stops reopening it
        req.status = 'incomplete'
        req.save(update_fields=['status'])
        updated.append(req.id)

        logger.info(f"[no_match] Request #{req.id} marked as incomplete")

        # Notify the patient
        try:
            patient = req.patient
            if patient:
                patient_user = User.objects.filter(
                    username=patient.emailaddress
                ).first()

                if patient_user:
                    Notification.objects.create(
                        user=patient_user,
                        blood_request=req,
                        title="No Donor Found",
                        message=(
                            f"We were unable to find a donor for your "
                            f"{req.blood_type} blood request at "
                            f"{req.hospital_location.name if req.hospital_location else 'the hospital'}. "
                            f"Please contact the hospital directly or submit a new request."
                        ),
                        type="blood_request_failed",
                    )
        except Exception as e:
            logger.error(f"Failed to notify patient for req {req.id}: {e}")

    logger.info(
        f"[no_match] Scanned {candidates.count()} candidates, "
        f"marked {len(updated)} incomplete: {updated}"
    )
    return f"Marked {len(updated)} requests as incomplete"
