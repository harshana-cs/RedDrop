from datetime import timedelta
from urllib import request
from django.conf import settings
from django.core.mail import send_mail
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.timezone import datetime, now
from .models import DonationCamp
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from blood_requests.models import BloodRequest
from hospital.models import Hospital, HospitalProfile, HospitalApplication
from register_donor.models import Donor
from donor.models import Donation, DonationConfirmation
from loginsignup.models import Patient
from register_donor.models import Donor
from rest_framework.decorators import api_view
from rest_framework.response import Response
from blood_stock.models import BloodStock, BloodStockHistory
from blood_stock.stock_utils import BLOOD_TYPES, available_units, is_nearing_expiry
from django.db import transaction
from django.contrib.auth.models import User
from math import radians, sin, cos, sqrt, atan2
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from dateutil.relativedelta import relativedelta
from .models import HospitalAuditLog, Notification
# ✅ NEW IMPORTS for tiered notification system (LOCATION 8)
import logging
# from celery_tasks import orchestrate_tiered_notification
# ✅ NEW IMPORTS for escalation tracking endpoints (LOCATION 9)
from .models import BloodRequestEscalation, NotificationLog
import random
import requests
from common.email_utils import send_branded_email
from common.upload_screening import screen_uploaded_file, notify_suspicious_upload
# Add this with your other imports at the top
from blood_requests.notifications import is_donor_eligible
from celery_task import orchestrate_tiered_notification
from .sms import send_sms
# Add this near the top of adminpanel/views.py
BLOOD_COMPATIBILITY = {
    "O-": ["O-", "O+", "A-", "A+", "B-", "B+", "AB-", "AB+"],
    "O+": ["O+", "A+", "B+", "AB+"],
    "A-": ["A-", "A+", "AB-", "AB+"],
    "A+": ["A+", "AB+"],
    "B-": ["B-", "B+", "AB-", "AB+"],
    "B+": ["B+", "AB+"],
    "AB-": ["AB-", "AB+"],
    "AB+": ["AB+"],
}

# ✅ NEW: Logger instance (LOCATION 8)
logger = logging.getLogger(__name__)

# ================= ACCOUNT STATUS EMAIL HELPERS =================
def _parse_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y", "on"}:
            return True
        if normalized in {"false", "0", "no", "n", "off", ""}:
            return False
    return default


def _send_hospital_status_email(hospital, is_active):
    profile = getattr(hospital, "profile", None)
    recipient = profile.email if profile and profile.email else None
    if not recipient:
        return

    state = "activated" if is_active else "deactivated"
    send_branded_email(
        subject=f"RedDrop: Hospital account {state}",
        to=recipient,
        title=f"Hospital Account {state.capitalize()}",
        lines=[
            f"Hello {hospital.name},",
            f"Your hospital account has been {state} by the RedDrop admin team.",
            "You can now log in and access your dashboard." if is_active else "You will not be able to log in until the account is reactivated.",
        ],
        bullets=[
            f"Hospital: {hospital.name}",
            f"Status: {state.capitalize()}",
        ],
        footer_note="Thank you for partnering with RedDrop and helping strengthen emergency blood access.",
        from_email=settings.EMAIL_HOST_USER,
        fail_silently=True,
    )


def _send_user_status_email(user, is_active, reason=""):
    if not user.emailaddress:
        return

    state = "activated" if is_active else "deactivated"
    reason_text = reason.strip() if isinstance(reason, str) else ""
    send_branded_email(
        subject=f"RedDrop: User account {state}",
        to=user.emailaddress,
        title=f"User Account {state.capitalize()}",
        lines=[
            f"Hello {user.fullname},",
            f"Your RedDrop user account has been {state} by admin.",
            "You can now log in again." if is_active else "You will not be able to log in until the account is reactivated.",
            f"Reason: {reason_text}" if reason_text else None,
        ],
        bullets=[
            f"User: {user.fullname}",
            f"Email: {user.emailaddress}",
            f"Status: {state.capitalize()}",
        ],
        footer_note="If you need help, please contact the RedDrop support team.",
        from_email=settings.EMAIL_HOST_USER,
        fail_silently=True,
    )

# ================= HELPER =================
def fetch_hospital_coordinates(hospital_name):
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": f"{hospital_name} Nepal",
        "format": "json",
        "limit": 1
    }
    headers = {"User-Agent": "reddrop-system"}
    response = requests.get(url, params=params, headers=headers)
    data = response.json()
    if data:
        lat = float(data[0]["lat"])
        lon = float(data[0]["lon"])
        return lat, lon
    return None, None


def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c


def send_donor_alert(donor, blood_request, distance, tier=None):
    sms_sent = False
    email_sent = False

    # SMS
    try:
        if donor.phone_number:
            message = (
                f"URGENT: {blood_request.blood_type} blood needed at "
                f"{blood_request.hospital_location.name if blood_request.hospital_location else 'hospital'}. "
                f"You are {round(distance, 1)} km away. Login to RedDrop to help."
            )
            result = send_sms(donor.phone_number, message)
            logger.info(f"SMS to {donor.phone_number}: result={result}")
            sms_sent = bool(result)
        else:
            logger.warning(f"Donor {donor.id} has no phone number - SMS skipped")
    except Exception as e:
        logger.error(f"SMS ERROR for donor {donor.id} ({donor.phone_number}): {e}", exc_info=True)

    # EMAIL
    try:
        if donor.email:
            send_branded_email(
                subject=f"{blood_request.blood_type} blood needed",
                to=donor.email,
                title="Urgent Blood Needed",
                lines=[
                    f"Hi {donor.first_name or 'Donor'},",
                    f"We need {blood_request.blood_type} blood as soon as possible.",
                    "Please log in to your RedDrop dashboard and respond if you are available.",
                ],
                bullets=[
                    f"Hospital: {blood_request.hospital_location.name if blood_request.hospital_location else 'Hospital'}",
                    f"District: {blood_request.district}",
                    f"Contact: {blood_request.contact_phone}",
                ],
                cta_text="Open Donor Dashboard",
                cta_url="http://localhost:5500/donor_dashboard.html",
                footer_note="Your response can help save a life.",
                from_email=settings.EMAIL_HOST_USER,
                fail_silently=False,
            )
            email_sent = True
        else:
            logger.warning(f"Donor {donor.id} has no email - email skipped")
    except Exception as e:
        logger.error(f"EMAIL ERROR for donor {donor.id}: {e}", exc_info=True)

    return {
        "sms_sent": sms_sent,
        "email_sent": email_sent
    }

# ================= ADMIN SECRET LOGIN =================
@api_view(["POST"])
@permission_classes([AllowAny])
def admin_secret_login(request):
    secret = request.data.get("secret_key")
    if not secret:
        return Response(
            {"success": False, "message": "Secret Key Required"},
            status=400
        )
    if secret == settings.ADMIN_SECRET_KEY:
        return Response({
            "success": True,
            "redirect": "admin_dashboard.html"
        })
    return Response(
        {"success": False, "message": "Invalid Secret Key"},
        status=401
    )


# ================= PENDING BLOOD REQUESTS =================
@api_view(["GET"])
@permission_classes([AllowAny])
def admin_pending_blood_requests(request):
    blood_requests = (
        BloodRequest.objects
        .filter(status="pending")
        .select_related("patient")
        .order_by("-created_at")
    )
    data = []
    for r in blood_requests:
        patient = r.patient
        data.append({
            "id": r.id,
            "patient_name": f"{patient.fullname}" if patient else "By Hospital",
            "blood_type": r.blood_type,
            "hospital": r.hospital_location.name if r.hospital_location else None,
            "urgency": r.urgency,
            "units": r.units_required,
            "district": r.district,
            "contact": r.contact_phone,
            "date": r.required_date.strftime("%Y-%m-%d") if r.required_date else None,
            "created_at": r.created_at.isoformat(),
            "hospital_doc": r.hospital_doc.url if r.hospital_doc else None,
            "doctor_note": r.doctor_note.url if r.doctor_note else None,
        })
    return Response({
        "success": True,
        "count": len(data),
        "data": data
    })


# ================= PENDING DONOR REGISTRATIONS =================
@api_view(["GET"])
@permission_classes([AllowAny])
def admin_pending_donor_registrations(request):
    donors = Donor.objects.filter(
        is_profile_completed=True,
        is_approved=False
    )
    data = []
    for d in donors:
        data.append({
            "id": d.id,
            "name": f"{d.first_name or ''} {d.last_name or ''}".strip(),
            "blood_type": d.blood_type,
            "phone": d.phone_number,
            "email": d.email,
            "city": d.city,
            "created_on": d.created_on.isoformat() if d.created_on else None,
            "citizenship_id": d.citizenship_id.url if d.citizenship_id else None,
            "photo": d.photo.url if d.photo else None,
        })
    return Response({
        "success": True,
        "count": len(data),
        "data": data
    })


# ================= APPROVE BLOOD REQUEST (MODIFIED - LOCATION 1) =================
@api_view(["POST"])
@permission_classes([AllowAny])
def admin_approve_blood_request(request, request_id):
    from django.utils import timezone
    from django.conf import settings
    from django.core.mail import send_mail
    from django.contrib.auth.models import User
    from blood_requests.models import BloodRequest
    from adminpanel.models import BloodRequestEscalation, Notification
    import logging
    logger = logging.getLogger(__name__)

    try:
        blood_request = BloodRequest.objects.get(id=request_id)
    except BloodRequest.DoesNotExist:
        return Response({"success": False, "message": "Blood request not found"}, status=404)

    if blood_request.status.lower() != "pending":
        return Response({"success": False, "message": "Request already processed"}, status=400)

    blood_request.status = "approved"
    blood_request.rejection_reason = ""
    blood_request.rejected_at = None
    blood_request.patient_confirmed = False
    blood_request.fulfilled = False
    blood_request.approved_at = timezone.now()
    blood_request.save()

    required_date = blood_request.required_date
    today_date = timezone.localdate()
    days_until_required = (required_date - today_date).days if required_date else 0
    is_future_scheduled = (
        days_until_required >= 3 and
        (blood_request.urgency or "").lower() not in {"critical", "high"}
    )

    if blood_request.patient:
        patient_user = User.objects.filter(
            username=blood_request.patient.emailaddress
        ).first()

        if patient_user:
            patient_msg = (
                f"Your blood request for {blood_request.blood_type} blood at "
                f"{blood_request.hospital_location.name if blood_request.hospital_location else 'the hospital'} "
            )
            if is_future_scheduled:
                patient_msg += (
                    "has been approved and scheduled. Donor and blood bank matching will start one day before the required date."
                )
            else:
                patient_msg += "has been approved. Searching for donors..."

            Notification.objects.create(
                user=patient_user,
                blood_request=blood_request,
                title="Blood Request Approved by Admin",
                message=patient_msg,
                type="blood_request_approved_by_admin",
            )

        try:
            send_branded_email(
                subject="RedDrop: Your blood request was approved",
                to=blood_request.patient.emailaddress,
                title="Blood Request Approved",
                lines=[
                    f"Hi {blood_request.patient.fullname},",
                    f"Your blood request for {blood_request.blood_type} blood has been approved.",
                    "Your request is scheduled and donor/blood bank matching will begin one day before your required date."
                    if is_future_scheduled else
                    "We are now searching for compatible donors only.",
                ],
                bullets=[
                    f"Blood Type: {blood_request.blood_type}",
                    f"Hospital: {blood_request.hospital_location.name if blood_request.hospital_location else 'N/A'}",
                    f"Required Date: {blood_request.required_date.strftime('%Y-%m-%d') if blood_request.required_date else 'ASAP'}",
                ],
                footer_note="We will keep updating your request as matching progresses.",
                from_email=settings.EMAIL_HOST_USER,
                fail_silently=True,
            )
        except Exception:
            pass

    if blood_request.created_by_hospital:
        Notification.objects.create(
            hospital=blood_request.created_by_hospital,
            blood_request=blood_request,
            title="Blood Request Approved",
            message=(
                f"Your request for {blood_request.blood_type} has been approved. "
                "Please find nearby donors now."
            ),
            type="blood_request_approved",
        )

    if not is_future_scheduled:
        escalation, created = BloodRequestEscalation.objects.get_or_create(
            blood_request=blood_request,
            defaults={"hospital": blood_request.created_by_hospital}
        )
        logger.info(
            f"Escalation record {'created' if created else 'exists'} "
            f"for request #{blood_request.id}"
        )

        try:
            from celery_task import orchestrate_tiered_notification
            orchestrate_tiered_notification.delay(blood_request.id)
            logger.info(f"Tiered notification started for request #{blood_request.id}")
        except Exception as exc:
            logger.error(f"Failed to start notifications for #{blood_request.id}: {exc}")
    else:
        logger.info(
            f"Request #{blood_request.id} queued for day-before matching (required in {days_until_required} days)."
        )

    return Response({
        "success": True,
        "message": "Blood request approved and scheduled for day-before matching." if is_future_scheduled else "Blood request approved. Tiered notifications started.",
    })

# ================= REJECT BLOOD REQUEST =================
@api_view(["POST"])
@permission_classes([AllowAny])
def admin_reject_blood_request(request, request_id):
    reason = (request.data.get("reason", "") or "").strip()
    try:
        blood_request = BloodRequest.objects.get(id=request_id)
    except BloodRequest.DoesNotExist:
        return Response(
            {"success": False, "message": "Blood request not found"},
            status=404
        )

    blood_request.status = "rejected"
    blood_request.rejection_reason = reason
    blood_request.rejected_at = timezone.now()

    blood_request.save()

    # Notify patient (in-app + email) when applicable
    if blood_request.patient:
        patient_user = User.objects.filter(username=blood_request.patient.emailaddress).first()
        if patient_user:
            Notification.objects.create(
                user=patient_user,
                blood_request=blood_request,
                title="Blood Request Rejected by Admin",
                message=(
                    f"Your blood request for {blood_request.blood_type} was rejected by admin."
                    + (f" Reason: {reason}" if reason else "")
                ),
                type="blood_request_rejected_by_admin",
            )
        try:
            send_branded_email(
                subject="RedDrop: Your blood request was rejected",
                to=blood_request.patient.emailaddress,
                title="Blood Request Rejected",
                lines=[
                    f"Hi {blood_request.patient.fullname},",
                    f"Your blood request for {blood_request.blood_type} was rejected by admin.",
                    f"Reason: {reason}" if reason else None,
                    "If you believe this is a mistake, please resubmit with the correct documents.",
                ],
                bullets=[
                    f"Blood Type: {blood_request.blood_type}",
                    f"Request ID: {blood_request.id}",
                ],
                footer_note="If you need support, please contact the RedDrop team.",
                from_email=settings.EMAIL_HOST_USER,
                fail_silently=True,
            )
        except Exception:
            pass

    # Admin/system log
    Notification.objects.create(
        title="Request Rejected",
        message=f"Request #{blood_request.id} was rejected",
        type="alert",
        blood_request=blood_request,
    )

    return Response({
        "success": True,
        "message": "Blood request rejected successfully"
    })


# ================= REJECT DONOR =================
@api_view(["POST"])
@permission_classes([AllowAny])
def admin_reject_donor_registration(request, donor_id):
    reason = (request.data.get("reason", "") or "").strip()
    try:
        donor = Donor.objects.get(id=donor_id)
    except Donor.DoesNotExist:
        return Response(
            {"success": False, "message": "Donor not found"},
            status=404
        )

    donor.is_approved = False
    donor.is_profile_completed = False
    donor.rejection_reason = reason
    donor.rejected_at = timezone.now()

    donor.save()

    donor_user = User.objects.filter(username=donor.email).first() if donor.email else None
    if donor_user:
        Notification.objects.create(
            user=donor_user,
            title="Donor Registration Rejected",
            message=(
                "Your donor registration was rejected by admin."
                + (f" Reason: {reason}" if reason else "")
                + " Please register again with the corrected details."
            ),
            type="donor_registration_rejected",
        )

    if donor.email:
        try:
            send_branded_email(
                subject="RedDrop: Your donor registration was rejected",
                to=donor.email,
                title="Donor Registration Rejected",
                lines=[
                    f"Hello {donor.first_name or 'Donor'},",
                    "Your donor registration was rejected by admin.",
                    f"Reason: {reason}" if reason else None,
                    "Please update your details and reapply if you believe this is a mistake.",
                ],
                bullets=[
                    f"Name: {donor.first_name or ''} {donor.last_name or ''}".strip(),
                    f"Email: {donor.email}",
                ],
                footer_note="Thank you for supporting the RedDrop community.",
                from_email=settings.EMAIL_HOST_USER,
                fail_silently=True,
            )
        except Exception:
            pass

    return Response({
        "success": True,
        "message": "Donor rejected successfully"
    })


# ================= APPROVE DONOR =================
@api_view(["POST"])
@permission_classes([AllowAny])
def admin_approve_donor_registration(request, donor_id):
    try:
        donor = Donor.objects.get(id=donor_id)
    except Donor.DoesNotExist:
        return Response(
            {"success": False, "message": "Donor not found"},
            status=404
        )

    if donor.is_approved:
        return Response({
            "success": True,
            "message": "Donor already approved"
        })

    donor.is_approved = True
    donor.rejection_reason = ""
    donor.rejected_at = None
    donor.save()

    if donor.email:
        send_branded_email(
            subject="RedDrop: Your donor registration was approved",
            to=donor.email,
            title="Donor Registration Approved",
            lines=[
                f"Hello {donor.first_name or 'Donor'},",
                "Great news! Your donor registration on RedDrop has been approved.",
                "You can now receive blood donation requests and help save lives.",
            ],
            bullets=[
                f"Donor: {donor.first_name or ''} {donor.last_name or ''}".strip(),
                f"Blood Type: {donor.blood_type or 'N/A'}",
                f"District: {donor.district or 'N/A'}",
            ],
            cta_text="Go to Donor Dashboard",
            cta_url="http://localhost:5500/donor_dashboard.html",
            footer_note="Thank you for being a hero and saving lives.",
            from_email="noreply@reddrop.com",
            fail_silently=True
        )
    return Response({
        "success": True,
        "message": "Donor approved successfully and email sent"
    })


# ================= LIST HOSPITALS =================
@api_view(["GET"])
@permission_classes([AllowAny])
def admin_list_hospitals(request):
    hospitals = Hospital.objects.all()
    data = []
    for h in hospitals:
        profile = getattr(h, "profile", None)
        data.append({
            "id": h.id,
            "name": h.name,
            "username": h.username,
            "password": h.plain_password or "",
            "active": h.is_active,
            "created_at": h.created_at.strftime("%Y-%m-%d"),
            "district": profile.district if profile else None,
            "address": profile.address if profile else None,
            "contact_number": profile.contact_number if profile else None,
            "registration_number": profile.registration_number if profile else None,
            "email": profile.email if profile else None,
        })
    return Response({
        "success": True,
        "data": data
    })


# ================= RESET HOSPITAL PASSWORD =================
@api_view(["POST"])
@permission_classes([AllowAny])
def admin_reset_hospital_password(request, hospital_id):
    password = request.data.get("password")
    if not password:
        return Response(
            {"success": False, "message": "Password required"},
            status=400
        )
    try:
        hospital = Hospital.objects.get(id=hospital_id)
    except Hospital.DoesNotExist:
        return Response(
            {"success": False, "message": "Hospital not found"},
            status=404
        )
    hospital.set_password(password)
    hospital.save()
    return Response({
        "success": True,
        "message": "Password reset successfully"
    })


# ================= TOGGLE HOSPITAL =================
@api_view(["POST"])
@permission_classes([AllowAny])
def admin_toggle_hospital(request, hospital_id):
    try:
        hospital = Hospital.objects.get(id=hospital_id)
    except Hospital.DoesNotExist:
        return Response(
            {"success": False, "message": "Hospital not found"},
            status=404
        )
    hospital.is_active = not hospital.is_active
    hospital.save()
    _send_hospital_status_email(hospital, hospital.is_active)
    return Response({
        "success": True,
        "active": hospital.is_active
    })


# ================= TOGGLE USER =================
@api_view(["POST"])
@permission_classes([AllowAny])
def admin_toggle_user(request, user_id):
    try:
        user = Patient.objects.get(id=user_id)
    except Patient.DoesNotExist:
        return Response(
            {"success": False, "message": "User not found"},
            status=404
        )

    reason = (request.data.get("reason") or "").strip()
    if not reason:
        return Response(
            {"success": False, "message": "Reason is required"},
            status=400
        )

    user.is_active = not user.is_active
    user.save(update_fields=["is_active"])

    # Keep matching donor record aligned when available
    donor = Donor.objects.filter(email=user.emailaddress).first()
    if donor:
        donor.is_approved = donor.is_approved and user.is_active
        donor.save(update_fields=["is_approved"])

    auth_user = User.objects.filter(username=user.emailaddress).first()
    status_word = "activated" if user.is_active else "deactivated"
    if auth_user:
        Notification.objects.create(
            user=auth_user,
            title=f"Account {status_word.title()} by Admin",
            message=f"Your account was {status_word} by admin. Reason: {reason}",
            type="alert",
        )

    _send_user_status_email(user, user.is_active, reason)

    return Response({
        "success": True,
        "active": user.is_active,
        "reason": reason
    })


# ================= CREATE HOSPITAL (MANUAL) =================
@api_view(["POST"])
@permission_classes([AllowAny])
def admin_create_hospital(request):
    name = request.data.get("name")
    username = request.data.get("username")
    password = request.data.get("password")
    district = request.data.get("district")
    contact_number = request.data.get("contact_number")
    registration_number = request.data.get("registration_number")
    email = request.data.get("email")

    if not all([name, username, password, district, contact_number, registration_number]):
        return Response(
            {"success": False, "message": "All required fields must be provided"},
            status=400
        )

    if Hospital.objects.filter(username=username).exists():
        return Response(
            {"success": False, "message": "Username already exists"},
            status=400
        )

    hospital = Hospital(name=name, username=username)
    hospital.set_password(password)
    hospital.save()

    HospitalProfile.objects.create(
        hospital=hospital,
        district=district,
        contact_number=contact_number,
        registration_number=registration_number,
        email=email
    )

    return Response({
        "success": True,
        "message": "Hospital created successfully"
    })


# ================= PROCESSED BLOOD REQUESTS =================
@api_view(["GET"])
@permission_classes([AllowAny])
def admin_processed_blood_requests(request):
    blood_requests = (
        BloodRequest.objects
        .filter(status__in=["approved", "rejected"])
        .select_related("patient")
        .order_by("-created_at")
    )
    data = []
    for r in blood_requests:
        patient = r.patient
        processed_dt = r.rejected_at if r.status == "rejected" and r.rejected_at else (r.donation_date or r.created_at)
        data.append({
            "id": r.id,
            "patient_name": patient.fullname if patient else "Unknown",
            "blood_type": r.blood_type,
            "hospital": r.hospital_location.name if r.hospital_location else None,
            "urgency": r.urgency,
            "status": r.status,
            "rejection_reason": r.rejection_reason or "",
            "rejected_at": r.rejected_at.isoformat() if r.rejected_at else None,
            "created_at": r.created_at.isoformat(),
            "processed_at": processed_dt.isoformat() if processed_dt else r.created_at.isoformat(),
            "processed_on": (
                processed_dt.strftime("%Y-%m-%d %H:%M")
                if processed_dt
                else r.created_at.strftime("%Y-%m-%d %H:%M")
            )
        })
    return Response({
        "success": True,
        "count": len(data),
        "data": data
    })


# ================= PROCESSED DONOR REGISTRATIONS =================
@api_view(["GET"])
@permission_classes([AllowAny])
def admin_processed_donor_registrations(request):
    donors = (
        Donor.objects
        .filter(Q(is_approved=True) | (Q(rejection_reason__isnull=False) & ~Q(rejection_reason="")))
        .order_by("-created_on")
    )
    data = []
    for d in donors:
        status_value = "approved" if d.is_approved else "rejected"
        data.append({
            "id": d.id,
            "name": f"{d.first_name or ''} {d.last_name or ''}".strip(),
            "blood_type": d.blood_type,
            "status": status_value,
            "rejection_reason": d.rejection_reason or "",
            "rejected_at": d.rejected_at.isoformat() if d.rejected_at else None,
            "processed_on": d.rejected_at.strftime("%Y-%m-%d %H:%M") if d.rejected_at else d.created_on.strftime("%Y-%m-%d %H:%M")
        })
    return Response({
        "success": True,
        "count": len(data),
        "data": data
    })


# ================= HOSPITAL REQUESTS =================
@api_view(["GET"])
@permission_classes([AllowAny])
def admin_hospital_requests(request):
    status_param = request.GET.get("status")
    qs = HospitalApplication.objects.all().order_by("-created_at")
    if status_param:
        qs = qs.filter(status=status_param)
    data = []
    for r in qs:
        data.append({
            "id": r.id,
            "hospital_name": r.hospital_name,
            "registration_number": r.registration_number,
            "hospital_type": r.hospital_type,
            "email": r.email,
            "phone": r.phone,
            "status": r.status,
            "rejection_reason": r.rejection_reason or "",
            "rejected_at": r.rejected_at.isoformat() if getattr(r, "rejected_at", None) else None,
        })
    return Response(data, status=status.HTTP_200_OK)


# ================= APPROVE HOSPITAL REQUEST =================
@api_view(["POST"])
@permission_classes([AllowAny])
def approve_hospital_request(request, pk):
    try:
        app = HospitalApplication.objects.get(id=pk, status="pending")
    except HospitalApplication.DoesNotExist:
        return Response(
            {"success": False, "message": "Hospital request not found"},
            status=status.HTTP_404_NOT_FOUND
        )

    username = request.data.get("username")
    password = request.data.get("password")

    if not username or not password:
        return Response(
            {"success": False, "message": "Username and password are required"},
            status=status.HTTP_400_BAD_REQUEST
        )

    if Hospital.objects.filter(username=username).exists():
        return Response(
            {"success": False, "message": "Username already exists"},
            status=status.HTTP_400_BAD_REQUEST
        )

    hospital = Hospital.objects.create(
        name=app.hospital_name,
        username=username,
        is_active=True
    )
    hospital.set_password(password)
    hospital.save()

    HospitalProfile.objects.create(
        hospital=hospital,
        district=app.address,
        contact_number=app.phone,
        registration_number=app.registration_number,
        email=app.email
    )

    app.status = "approved"
    app.approved_at = timezone.now()
    app.save()

    send_branded_email(
        subject="Hospital Registration Approved - RedDrop",
        to=app.email,
        title="Hospital Registration Approved",
        lines=[
            f"Hello {app.hospital_name},",
            "Your hospital registration request has been approved.",
            "Please log in and change your password after first login.",
        ],
        bullets=[
            f"Username: {username}",
            f"Password: {password}",
        ],
        cta_text="Open Hospital Login",
        cta_url="http://localhost:5500/hospital-login.html",
        footer_note="Please keep your credentials secure.",
        from_email=settings.EMAIL_HOST_USER,
        fail_silently=True,
    )
    return Response(
        {"success": True, "message": "Hospital approved successfully"},
        status=status.HTTP_200_OK
    )


# ================= REJECT HOSPITAL REQUEST =================
@api_view(["POST"])
@permission_classes([AllowAny])
def reject_hospital_request(request, pk):
    try:
        application = HospitalApplication.objects.get(id=pk, status="pending")
    except HospitalApplication.DoesNotExist:
        return Response(
            {"error": "Hospital request not found"},
            status=status.HTTP_404_NOT_FOUND
        )

    application.status = "rejected"
    application.rejection_reason = (request.data.get("reason", "") or "").strip()
    application.rejected_at = timezone.now()
    application.save()

    return Response(
        {"success": True, "message": "Hospital request rejected"},
        status=status.HTTP_200_OK
    )


# ================= HOSPITAL REQUEST DETAIL =================
@api_view(["GET"])
@permission_classes([AllowAny])
def hospital_request_detail(request, pk):
    h = HospitalApplication.objects.get(id=pk)
    return Response({
        "hospital_name": h.hospital_name,
        "hospital_type": h.hospital_type,
        "email": h.email,
        "phone": h.phone,
        "address": h.address,
        "bed_capacity": h.bed_capacity,
        "status": h.status,
        "rejection_reason": h.rejection_reason or "",
        "rejected_at": h.rejected_at.isoformat() if h.rejected_at else None,
        "registration_certificate": h.registration_certificate.url,
        "medical_license": h.medical_license.url,
        "id_proof": h.id_proof.url,
    })


# ================= ANALYTICS: BLOOD TYPE DISTRIBUTION =================
def get_date_range(request):
    """Helper to parse date range from request query params."""
    days = request.GET.get("days")
    from_date = request.GET.get("from")
    to_date = request.GET.get("to")
 
    now = timezone.now()
 
    if from_date and to_date:
        try:
            start = datetime.strptime(from_date, "%Y-%m-%d")
            end   = datetime.strptime(to_date,   "%Y-%m-%d")
            start = timezone.make_aware(start)
            end   = timezone.make_aware(end.replace(hour=23, minute=59, second=59))
            return start, end
        except ValueError:
            pass
 
    days = int(days) if days and days.isdigit() else 7
    start = now - timedelta(days=days)
    return start, now

@api_view(["GET"])
@permission_classes([AllowAny])
def api_blood_type_distribution(request):
    start, end = get_date_range(request)
    data = (
        BloodRequest.objects
        .filter(created_at__gte=start, created_at__lte=end)
        .values("blood_type")
        .annotate(count=Count("id"))
        .order_by("blood_type")
    )
    return Response({
        "labels": [d["blood_type"] for d in data],
        "values": [d["count"]      for d in data]
    })


# ================= ANALYTICS: REQUEST STATUS OVERVIEW =================
@api_view(["GET"])
@permission_classes([AllowAny])
def api_request_status_overview(request):
    start, end = get_date_range(request)
 
    # Determine granularity: daily for ≤30 days, weekly for ≤90, monthly otherwise
    delta = (end - start).days
 
    if delta <= 30:
        # Daily buckets
        labels, pending, approved, rejected = [], [], [], []
        cursor = start.date()
        end_d  = end.date()
        while cursor <= end_d:
            next_d = cursor + timedelta(days=1)
            labels.append(cursor.strftime("%d %b"))
            qs = BloodRequest.objects.filter(
                created_at__date=cursor
            )
            pending.append( qs.filter(status="pending").count())
            approved.append(qs.filter(status="approved").count())
            rejected.append(qs.filter(status="rejected").count())
            cursor = next_d
 
    elif delta <= 90:
        # Weekly buckets
        labels, pending, approved, rejected = [], [], [], []
        cursor = start
        while cursor < end:
            week_end = min(cursor + timedelta(days=7), end)
            labels.append(cursor.strftime("%d %b"))
            qs = BloodRequest.objects.filter(
                created_at__gte=cursor, created_at__lt=week_end
            )
            pending.append( qs.filter(status="pending").count())
            approved.append(qs.filter(status="approved").count())
            rejected.append(qs.filter(status="rejected").count())
            cursor = week_end
 
    else:
        # Monthly buckets (original logic)
        labels, pending, approved, rejected = [], [], [], []
        now_dt = timezone.now()
        months = max(1, delta // 30)
        for i in range(months - 1, -1, -1):
            month_start = (now_dt.replace(day=1) - relativedelta(months=i))
            month_end   = month_start + relativedelta(months=1)
            if month_start < start: month_start = start
            if month_end   > end:   month_end   = end
            labels.append(month_start.strftime("%b %Y"))
            qs = BloodRequest.objects.filter(
                created_at__gte=month_start, created_at__lt=month_end
            )
            pending.append( qs.filter(status="pending").count())
            approved.append(qs.filter(status="approved").count())
            rejected.append(qs.filter(status="rejected").count())
 
    return Response({
        "labels":   labels,
        "pending":  pending,
        "approved": approved,
        "rejected": rejected
    })


# ================= NOTIFICATIONS =================
def get_notifications(request):
    notifications = Notification.objects.filter(
        hospital__isnull=True,
        user__isnull=True,
    ).order_by("-created_at")[:10]

    data = [
        {
            "id": n.id,
            "title": n.title,
            "message": n.message,
            "type": n.type,
            "blood_request_id": n.blood_request_id,
            "created_at": n.created_at.strftime("%Y-%m-%d %H:%M"),
            "is_read": n.is_read
        }
        for n in notifications
    ]

    unread = Notification.objects.filter(
        hospital__isnull=True,
        user__isnull=True,
        is_read=False
    ).count()

    return JsonResponse({
        "notifications": data,
        "unread": unread
    })


@csrf_exempt
def mark_notification_read(request, notification_id):
    if request.method == "POST":
        notification = get_object_or_404(
            Notification,
            id=notification_id,
            hospital__isnull=True,
            user__isnull=True,
        )
        notification.is_read = True
        notification.save()
        return JsonResponse({"success": True})
    return JsonResponse({"error": "Invalid request"}, status=400)


# ================= MARK ALL NOTIFICATIONS READ =================
@api_view(["POST"])
@permission_classes([AllowAny])
def mark_all_notifications_read(request):
    Notification.objects.filter(
        hospital__isnull=True,
        user__isnull=True,
        is_read=False
    ).update(is_read=True)
    return Response({"success": True})


# ================= HOSPITAL AUDIT LOGS =================
@api_view(["GET"])
@permission_classes([AllowAny])
def admin_hospital_audit_logs(request):
    logs = HospitalAuditLog.objects.select_related("hospital").order_by("-created_at")[:200]
    data = []
    for log in logs:
        data.append({
            "hospital": log.hospital.name if log.hospital else "Application",
            "action": log.action,
            "description": log.description,
            "metadata": log.metadata,
            "ip_address": log.ip_address if hasattr(log, "ip_address") else None,
            "time": log.created_at
        })
    return Response({
        "logs": data,
        "active_hospitals": Hospital.objects.filter(is_active=True).count()
    })


# ================= USERS =================
@api_view(["GET"])
@permission_classes([AllowAny])
def admin_users(request):
    users = Patient.objects.all()
    data = []
    for u in users:
        donor = Donor.objects.filter(email=u.emailaddress).first()
        requests_count = BloodRequest.objects.filter(patient=u).count()
        
        # Count only donations where this user acted as a DONOR
        if donor:
            donor_donations_count = Donation.objects.filter(donor=donor).count()
        else:
            donor_donations_count = 0

        data.append({
            "id": u.id,
            "name": u.fullname,
            "email": u.emailaddress,
            "active": u.is_active,
            "blood_type": donor.blood_type if donor else None,
            "total_requests": requests_count,
            "total_donations": donor_donations_count,
            "availability": "Available" if donor else "Not Donor"
        })
    return Response(data)


# ================= USER DETAIL =================
@api_view(["GET"])
@permission_classes([AllowAny])
def admin_user_detail(request, user_id):
    try:
        user = Patient.objects.get(id=user_id)
    except Patient.DoesNotExist:
        return Response(
            {"success": False, "message": "User not found"},
            status=404
        )

    donor = Donor.objects.filter(email=user.emailaddress).first()
    blood_requests = BloodRequest.objects.filter(patient=user).select_related("hospital_location").order_by("-created_at")

    request_list = []
    donation_history = []

    def _abs(media_field):
        if not media_field:
            return None
        try:
            return request.build_absolute_uri(media_field.url)
        except Exception:
            return media_field.url

    for r in blood_requests:
        request_list.append({
            "id": r.id,
            "blood_type": r.blood_type,
            "units": r.units_required,
            "urgency": r.urgency,
            "reason": r.reason,
            "district": r.district,
            "required_date": r.required_date.isoformat() if r.required_date else None,
            "contact_name": r.contact_name,
            "contact_phone": r.contact_phone,
            "hospital": r.hospital_location.name if r.hospital_location else None,
            "status": r.status,
            "date": r.created_at.strftime("%Y-%m-%d"),
            "created_at": r.created_at.isoformat(),
            "donation_date": r.donation_date.isoformat() if r.donation_date else None,
            "hospital_doc": _abs(r.hospital_doc),
            "doctor_note": _abs(r.doctor_note),
        })
        if r.status == "completed":
            donation_history.append({
                "request_id": r.id,
                "blood_type": r.blood_type,
                "hospital": r.hospital_location.name if r.hospital_location else None,
                "status": "completed",
                "date": r.donation_date.strftime("%Y-%m-%d") if r.donation_date else None,
                "donation_date": r.donation_date.isoformat() if r.donation_date else None,
                "units": r.units_required,
            })

    last_donation = None
    completed = blood_requests.filter(status="completed").order_by("-donation_date").first()
    if completed and completed.donation_date:
        last_donation = completed.donation_date

    DONATION_GAP_DAYS = 56  # Whole blood donation gap

    eligibility = "Eligible"
    if last_donation:
        days_since = (timezone.now() - last_donation).days
        if days_since < DONATION_GAP_DAYS:
            eligibility = f"Not Eligible ({DONATION_GAP_DAYS - days_since} days remaining)"

    donor_info = None
    donor_donations = []
    donor_confirmations = []
    if donor:
        donor_info = {
            "id": donor.id,
            "first_name": donor.first_name,
            "last_name": donor.last_name,
            "blood_type": donor.blood_type,
            "phone": donor.phone_number,
            "email": donor.email,
            "gender": donor.gender,
            "date_of_birth": donor.date_of_birth.isoformat() if donor.date_of_birth else None,
            "address": donor.address,
            "city": donor.city,
            "state": donor.state,
            "zip_code": donor.zip_code,
            "latitude": donor.latitude,
            "longitude": donor.longitude,
            "location_updated_at": donor.location_updated_at.isoformat() if donor.location_updated_at else None,
            "emergency_contact_name": donor.emergency_contact_name,
            "emergency_contact_phone": donor.emergency_contact_phone,
            "weight": donor.weight,
            "has_diabetes": donor.has_diabetes,
            "has_hypertension": donor.has_hypertension,
            "has_heart_disease": donor.has_heart_disease,
            "no_medical_conditions": donor.no_medical_conditions,
            "approved": donor.is_approved,
            "is_profile_completed": donor.is_profile_completed,
            "created_on": donor.created_on.isoformat() if donor.created_on else None,
            "photo": _abs(donor.photo),
            "citizenship_id": _abs(donor.citizenship_id),
        }

        donor_donations = [
            {
                "id": d.id,
                "blood_type": d.blood_type,
                "hospital": d.hospital,
                "status": d.status,
                "date": d.date.isoformat() if d.date else None,
                "next_donation_date": d.next_donation_date.isoformat() if d.next_donation_date else None,
            }
            for d in Donation.objects.filter(donor=donor).order_by("-date")
        ]

        donor_confirmations = [
            {
                "id": c.id,
                "request_id": c.request_id,
                "patient_confirmed": c.patient_confirmed,
                "donor_confirmed": c.donor_confirmed,
                "donation_date": c.donation_date.isoformat() if c.donation_date else None,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in DonationConfirmation.objects.filter(donor=donor).order_by("-created_at")[:50]
        ]

    return Response({
        "id": user.id,
        "name": user.fullname,
        "email": user.emailaddress,
        "active": user.is_active,
        "created_on": user.created_on.isoformat() if user.created_on else None,
        "donor": donor_info,
        "is_donor": bool(donor),
        "last_donation_date": last_donation.strftime("%Y-%m-%d") if last_donation else None,
        "eligibility_status": eligibility,
        "requests": request_list,
        "donation_history": donation_history,
        "donations": donor_donations,
        "donation_confirmations": donor_confirmations,
        "total_requests": blood_requests.count(),
        "total_donations": len(donor_donations) if donor else len(donation_history),
    })


# ================= BLOOD INVENTORY =================
@api_view(["GET"])
@permission_classes([AllowAny])
def admin_blood_inventory(request):
    stocks = BloodStock.objects.filter(hospital__isnull=True)
    data = []
    for s in stocks:
        units = available_units(s)
        data.append({
            "blood_type": s.blood_type,
            "units": units,
            "expiry_date": s.expiry_date,
            "minimum_required": s.minimum_required,
            "last_updated": s.last_updated,
            "expired": bool(s.expiry_date and s.expiry_date < timezone.localdate()),
        })
    return Response(data)


@api_view(["GET"])
def admin_hospital_stock(request):
    stocks = BloodStock.objects.filter(
        hospital__isnull=False
    ).select_related("hospital")
    data = []
    for s in stocks:
        units = available_units(s)
        data.append({
            "hospital": s.hospital.name,
            "blood_type": s.blood_type,
            "units": units,
            "expiry_date": s.expiry_date,
            "minimum_required": s.minimum_required,
            "last_updated": s.last_updated,
            "expired": bool(s.expiry_date and s.expiry_date < timezone.localdate()),
        })

    return Response(data)


@api_view(["POST"])
@permission_classes([AllowAny])
def admin_add_inventory(request):
    blood_type = request.data.get("blood_type")
    units = int(request.data.get("units"))
    expiry_date = parse_date(request.data.get("expiry_date")) if request.data.get("expiry_date") else None

    stock, created = BloodStock.objects.get_or_create(
        hospital=None,
        blood_type=blood_type
    )
    stock.units += units
    stock.expiry_date = expiry_date
    stock.save()

    BloodStockHistory.objects.create(
        hospital=None,
        blood_type=blood_type,
        transaction_type="add",
        units=units,
        performed_by="Admin",
        expiry_date=expiry_date,
        new_balance=stock.units
    )
    return Response({"success": True})


@api_view(["POST"])
@permission_classes([AllowAny])
def admin_remove_inventory(request):
    blood_type = request.data.get("blood_type")
    units = int(request.data.get("units", 0))

    try:
        stock = BloodStock.objects.get(hospital=None, blood_type=blood_type)
    except BloodStock.DoesNotExist:
        return Response({"message": "Stock not found"}, status=404)

    if units > stock.units:
        return Response({"message": "Insufficient stock"}, status=400)

    with transaction.atomic():
        stock.units -= units
        stock.save()
        BloodStockHistory.objects.create(
            hospital=None,
            blood_type=blood_type,
            transaction_type="remove",
            units=units,
            reason="Admin removal",
            performed_by="Admin",
            new_balance=stock.units
        )
    return Response({"success": True})


@api_view(["POST"])
@permission_classes([AllowAny])
def admin_bulk_add_inventory(request):
    stock_data = request.data.get("stock", {})
    notes = request.data.get("notes")

    for blood_type, units in stock_data.items():
        units = int(units)
        if units <= 0:
            continue
        stock, _ = BloodStock.objects.get_or_create(
            hospital=None,
            blood_type=blood_type,
            defaults={"units": 0}
        )
        stock.units += units
        stock.save()
        BloodStockHistory.objects.create(
            hospital=None,
            blood_type=blood_type,
            transaction_type="add",
            units=units,
            source=notes,
            performed_by="Admin",
            new_balance=stock.units
        )
    return Response({"success": True})


@api_view(["GET"])
@permission_classes([AllowAny])
def admin_stock_movements(request):
    limit = int(request.GET.get("limit", 10))
    history = BloodStockHistory.objects.filter(
        hospital__isnull=True
    ).order_by("-timestamp")[:limit]
    data = []
    for h in history:
        data.append({
            "date": h.timestamp,
            "blood_type": h.blood_type,
            "expiry_date": h.expiry_date,
            "type": h.transaction_type,
            "units": h.units,
            "updated_by": h.performed_by,
            "notes": h.source or h.reason
        })
    return Response(data)


# ================= AUDIT / ACTIVITY LOGS =================
@api_view(["GET"])
@permission_classes([AllowAny])
def admin_activity_logs(request):
    role = request.GET.get("role")
    log_type = request.GET.get("type")
    date = request.GET.get("date")

    logs = Notification.objects.all().order_by("-created_at")

    if log_type and log_type != "all":
        logs = logs.filter(type=log_type)

    if date:
        logs = logs.filter(created_at__date=date)

    data = []
    for n in logs:
        role_type = "system"
        if n.user:
            donor = Donor.objects.filter(email=n.user.email).first()
            role_type = "donor" if donor else "patient"
        elif hasattr(n, "hospital") and n.hospital:
            role_type = "hospital"

        if role and role != "all":
            if role_type != role:
                continue

        data.append({
            "role": role_type,
            "type": n.type,
            "action": n.title,
            "message": n.message,
            "time": n.created_at
        })

    return Response(data)


def _donation_timeline_entry(notification, req=None, donor_name=None):
    """Normalize notification rows into timeline-friendly items."""
    ntype = (getattr(notification, "type", "") or "").lower()
    title = getattr(notification, "title", "") or ""
    message = getattr(notification, "message", "") or ""
    created_at = getattr(notification, "created_at", None)

    if ntype in {"blood_request_approved_by_admin", "blood_request_approved", "request_approved"}:
        return {
            "event": "Request Approved",
            "time": created_at.isoformat() if created_at else None,
            "by": "Admin",
            "details": message or title,
            "tone": "success",
        }

    if ntype in {"blood_request_rejected_by_admin", "request_rejected"}:
        return {
            "event": "Request Rejected",
            "time": created_at.isoformat() if created_at else None,
            "by": "Admin",
            "details": message or title,
            "tone": "danger",
        }

    if ntype == "donor_accept":
        return {
            "event": "Donor Accepted Request",
            "time": created_at.isoformat() if created_at else None,
            "by": donor_name or "Donor",
            "details": message or title,
            "tone": "info",
        }

    if ntype == "donor_request_rejected":
        return {
            "event": "Donor Declined Request",
            "time": created_at.isoformat() if created_at else None,
            "by": donor_name or "Donor",
            "details": message or title,
            "tone": "warning",
        }

    if ntype in {"completed", "request_completed", "donation_complete", "donation_completed"}:
        return {
            "event": "Donation Completed",
            "time": created_at.isoformat() if created_at else None,
            "by": "System",
            "details": message or title,
            "tone": "success",
        }

    if ntype == "donor_confirmation":
        return {
            "event": "Donor Confirmed Donation",
            "time": created_at.isoformat() if created_at else None,
            "by": donor_name or "Donor",
            "details": message or title,
            "tone": "info",
        }

    if ntype == "patient_confirmation":
        return {
            "event": "Patient Confirmed Receipt",
            "time": created_at.isoformat() if created_at else None,
            "by": "Patient",
            "details": message or title,
            "tone": "info",
        }

    return {
        "event": title or "Activity",
        "time": created_at.isoformat() if created_at else None,
        "by": "System",
        "details": message,
        "tone": "neutral",
    }


# ================= DONATION CAMPS: SERIALIZE HELPER =================
def _serialize_camp(camp):
    today = timezone.localdate()
    return {
        "id": camp.id,
        "title": camp.title,
        "description": camp.description,
        "hospital_name": camp.hospital_name,
        "date": str(camp.date),
        "start_time": str(camp.start_time),
        "end_time": str(camp.end_time),
        "location": camp.location,
        "is_urgent": camp.is_urgent,
        "is_past": camp.date < today,
        "is_approved": camp.is_approved,
        "is_rejected": getattr(camp, "is_rejected", False),
        "created_by": camp.created_by,
        "contact_number": camp.contact_number or "",   
        "map_link": camp.map_link or "", 
        "authorization_letter": camp.authorization_letter.url if camp.authorization_letter else "",
        "rejection_reason": getattr(camp, "rejection_reason", "") or "",
        "rejected_at": camp.rejected_at.isoformat() if getattr(camp, "rejected_at", None) else None,
    }


def _parse_and_validate_camp_date(date_value, existing_date=None):
    camp_date = parse_date(str(date_value)) if date_value else None
    if not camp_date:
        return None, Response(
            {"success": False, "message": "Camp date is required and must be a valid date."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    today = timezone.localdate()
    if camp_date < today and camp_date != existing_date:
        return None, Response(
            {"success": False, "message": "Camp date cannot be before today."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return camp_date, None


# ================= DONATION CAMPS: LIST + CREATE =================
@api_view(["GET", "POST"])
@permission_classes([AllowAny])
def admin_donation_camps(request):

    # �"��"� LIST �"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"�
    if request.method == "GET":
        camps = DonationCamp.objects.all().order_by("-date", "-id")
        return Response([_serialize_camp(c) for c in camps])

    # �"��"� CREATE �"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"�
    title      = request.data.get("title", "").strip()
    hospital   = request.data.get("hospital_name", "").strip()
    date_val   = request.data.get("date")
    start_time = request.data.get("start_time")
    end_time   = request.data.get("end_time")
    location   = request.data.get("location", "").strip()

    contact_number = request.data.get("contact_number", "").strip()
    map_link       = request.data.get("map_link", "").strip()
    authorization_letter = request.FILES.get("authorization_letter")
    camp_date, date_error = _parse_and_validate_camp_date(date_val)
    if date_error:
        return date_error

    screening = screen_uploaded_file(
        authorization_letter,
        upload_label="Authorization Letter",
        upload_type="camp_document",
    )

    if screening["verdict"] == "BLOCK":
        notify_suspicious_upload(
            title="Blocked Camp Document",
            message=(
                f'Donation camp "{title}" was blocked because the authorization letter looks suspicious or AI-generated. '
                f"Risk score: {screening['risk_score']}. Flags: {', '.join(screening['flags']) or 'None'}."
            ),
            upload_result=screening,
            metadata={"hospital_name": hospital, "location": location},
        )
        return Response(
            {
                "success": False,
                "message": "The uploaded authorization letter looks suspicious or AI-generated.",
                "screening": screening,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    missing = []
    if not title:      missing.append("title")
    if not hospital:   missing.append("hospital_name")
    if not start_time: missing.append("start_time")
    if not end_time:   missing.append("end_time")
    if not location:   missing.append("location")

    if missing:
        return Response(
            {"success": False, "message": f"Required fields missing: {', '.join(missing)}"},
            status=status.HTTP_400_BAD_REQUEST
        )

    camp = DonationCamp.objects.create(
        title=title,
        description=request.data.get("description", ""),
        hospital_name=hospital,
        date=camp_date,
        start_time=start_time,
        end_time=end_time,
        location=location,
        contact_number=contact_number,
        map_link=map_link,
        is_urgent=_parse_bool(request.data.get("is_urgent"), default=False),
        is_approved=False,
        created_by="admin",
        authorization_letter=authorization_letter,
    )

    camp.refresh_from_db()

    try:
        Notification.objects.create(
            title="New Donation Camp Created",
            message=f'"{camp.title}" on {camp.date} at {camp.location}',
            type="alert",
        )
    except:
        pass

    if screening["verdict"] == "REVIEW":
        notify_suspicious_upload(
            title="Suspicious Camp Document",
            message=(
                f'Donation camp "{camp.title}" uploaded a document that needs review. '
                f"Risk score: {screening['risk_score']}. Flags: {', '.join(screening['flags']) or 'None'}."
            ),
            upload_result=screening,
            metadata={"camp_id": camp.id, "title": camp.title},
        )

    return Response(_serialize_camp(camp), status=status.HTTP_201_CREATED)


# ================= DONATION CAMPS: DETAIL + UPDATE + DELETE =================
@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([AllowAny])
def admin_donation_camp_detail(request, camp_id):

    try:
        camp = DonationCamp.objects.get(id=camp_id)
    except DonationCamp.DoesNotExist:
        return Response({"success": False, "message": "Camp not found"}, status=404)

    if request.method == "GET":
        return Response(_serialize_camp(camp))

    if request.method == "DELETE":
        camp.delete()
        return Response({"success": True, "message": "Deleted"}, status=204)

    data = request.data
    uploaded_letter = request.FILES.get("authorization_letter")
    screening = screen_uploaded_file(
        uploaded_letter,
        upload_label="Authorization Letter",
        upload_type="camp_document",
    )

    if uploaded_letter and screening["verdict"] == "BLOCK":
        notify_suspicious_upload(
            title="Blocked Camp Document",
            message=(
                f'Donation camp "{camp.title}" update was blocked because the authorization letter looks suspicious or AI-generated. '
                f"Risk score: {screening['risk_score']}. Flags: {', '.join(screening['flags']) or 'None'}."
            ),
            upload_result=screening,
            metadata={"camp_id": camp.id, "title": camp.title},
        )
        return Response(
            {
                "success": False,
                "message": "The uploaded authorization letter looks suspicious or AI-generated.",
                "screening": screening,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # �"��"� PUT (FULL UPDATE) �"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"�
    if request.method == "PUT":
        incoming_date, date_error = _parse_and_validate_camp_date(data.get("date"), existing_date=camp.date)
        if date_error:
            return date_error

        camp.title         = data.get("title", "").strip()
        camp.description   = data.get("description", "")
        camp.hospital_name = data.get("hospital_name", "").strip()
        camp.date          = incoming_date
        camp.start_time    = data.get("start_time")
        camp.end_time      = data.get("end_time")
        camp.location      = data.get("location", "").strip()
        camp.contact_number = data.get("contact_number", "")
        camp.map_link       = data.get("map_link", "")
        camp.is_urgent     = _parse_bool(data.get("is_urgent"), default=False)
        if uploaded_letter:
            camp.authorization_letter = uploaded_letter

        camp.save()
        camp.refresh_from_db()

    # �"��"� PATCH (PARTIAL UPDATE) �"��"��"��"��"��"��"��"��"��"��"��"�
    elif request.method == "PATCH":
        if "date" in data:
            incoming_date, date_error = _parse_and_validate_camp_date(data.get("date"), existing_date=camp.date)
            if date_error:
                return date_error
            camp.date = incoming_date

        if "title" in data: camp.title = data["title"].strip()
        if "description" in data: camp.description = data["description"]
        if "hospital_name" in data: camp.hospital_name = data["hospital_name"].strip()
        if "start_time" in data: camp.start_time = data["start_time"]
        if "end_time" in data: camp.end_time = data["end_time"]
        if "location" in data: camp.location = data["location"].strip()

        if "contact_number" in data:
            camp.contact_number = data["contact_number"]

        if "map_link" in data:
            camp.map_link = data["map_link"]

        if "is_urgent" in data:
            camp.is_urgent = _parse_bool(data.get("is_urgent"), default=False)
        if uploaded_letter:
            camp.authorization_letter = uploaded_letter

        camp.save()
        camp.refresh_from_db()

    if uploaded_letter and screening["verdict"] == "REVIEW":
        notify_suspicious_upload(
            title="Suspicious Camp Document",
            message=(
                f'Donation camp "{camp.title}" uploaded a document that needs review. '
                f"Risk score: {screening['risk_score']}. Flags: {', '.join(screening['flags']) or 'None'}."
            ),
            upload_result=screening,
            metadata={"camp_id": camp.id, "title": camp.title},
        )

    return Response(_serialize_camp(camp))


# ================= PUBLIC DONATION CAMPS =================
@api_view(["GET"])
@permission_classes([AllowAny])
def public_donation_camps(request):
    today = timezone.localdate()
    camps = DonationCamp.objects.filter(date__gte=today, is_approved=True).order_by("date", "start_time")
    return Response([_serialize_camp(c) for c in camps])


@api_view(["GET"])
@permission_classes([AllowAny])
def admin_all_hospitals_stock(request):
    result = []
    unavailable_global = set()
    expiring_global = []
    today = timezone.localdate()

    # �"��"� Blood Bank (hospital=None) �"��"�
    bank_stocks = BloodStock.objects.filter(hospital__isnull=True)
    if bank_stocks.exists():
        stock_rows = []
        for s in bank_stocks:
            units = available_units(s)
            nearing_expiry = bool(units > 0 and is_nearing_expiry(s.expiry_date, days=5, today=today))
            if units <= 0:
                unavailable_global.add(s.blood_type)
            if nearing_expiry:
                expiring_global.append({
                    "location": "Blood Bank",
                    "blood_type": s.blood_type,
                    "units": units,
                    "expiry_date": s.expiry_date,
                })
            stock_rows.append(
                {
                    "blood_type": s.blood_type,
                    "units": units,
                    "expiry_date": s.expiry_date,
                    "last_updated": s.last_updated,
                    "expired": bool(s.expiry_date and s.expiry_date < timezone.localdate()),
                    "nearing_expiry": nearing_expiry,
                }
            )
        result.append({
            "hospital": {"id": None, "name": "Blood Bank", "district": "Central"},
            "stock": stock_rows
        })

    # �"��"� Active Hospitals �"��"�
    hospitals = Hospital.objects.filter(is_active=True)
    for h in hospitals:
        stocks = BloodStock.objects.filter(hospital=h)
        stock_rows = []
        for s in stocks:
            units = available_units(s)
            nearing_expiry = bool(units > 0 and is_nearing_expiry(s.expiry_date, days=5, today=today))
            if units <= 0:
                unavailable_global.add(s.blood_type)
            if nearing_expiry:
                expiring_global.append({
                    "location": h.name,
                    "blood_type": s.blood_type,
                    "units": units,
                    "expiry_date": s.expiry_date,
                })
            stock_rows.append(
                {
                    "blood_type": s.blood_type,
                    "units": units,
                    "expiry_date": s.expiry_date,
                    "last_updated": s.last_updated,
                    "expired": bool(s.expiry_date and s.expiry_date < timezone.localdate()),
                    "nearing_expiry": nearing_expiry,
                }
            )
        result.append({
            "hospital": {
                "id": h.id,
                "name": h.name,
                "district": h.profile.district if hasattr(h, "profile") else None
            },
            "stock": stock_rows
        })

    unavailable_list = sorted(unavailable_global)
    if unavailable_list:
        title = "Blood Stock Unavailable Alert"
        exists_today = Notification.objects.filter(
            hospital__isnull=True,
            user__isnull=True,
            type="system_alert",
            title=title,
            created_at__date=today,
        ).exists()
        if not exists_today:
            Notification.objects.create(
                title=title,
                message=(
                    "Unavailable blood types detected across blood bank/hospitals: "
                    f"{', '.join(unavailable_list)}."
                ),
                type="system_alert",
            )

    if expiring_global:
        title = "Blood Expiry Alert"
        exists_today = Notification.objects.filter(
            hospital__isnull=True,
            user__isnull=True,
            type="system_alert",
            title=title,
            created_at__date=today,
        ).exists()
        if not exists_today:
            types = ", ".join(sorted({r.get("blood_type") for r in expiring_global if r.get("blood_type")})) or "Unknown"
            Notification.objects.create(
                title=title,
                message=f"Blood units nearing expiry (within 5 days) detected: {types}.",
                type="system_alert",
            )

    return Response({
        "data": result,
        "scarcity_popup": {
            "show": bool(unavailable_list),
            "title": "Blood Not Available",
            "message": "These blood types are currently unavailable in stock.",
            "unavailable_blood_types": unavailable_list,
        },
        "expiry_popup": {
            "show": bool(expiring_global),
            "title": "Blood Expiry Alert",
            "message": "Some blood units are nearing expiry within 5 days.",
            "expiring_units": expiring_global,
        },
    })


# ================= PARTNER CREATE =================
@api_view(["POST"])
@permission_classes([AllowAny])
def create_camp_by_partner(request):

    camp = DonationCamp.objects.create(
        title=request.data.get("title"),
        description=request.data.get("description"),
        hospital_name=request.data.get("hospital_name"),
        date=request.data.get("date"),
        start_time=request.data.get("start_time"),
        end_time=request.data.get("end_time"),
        location=request.data.get("location"),
        contact_number=request.data.get("contact_number"),
        map_link=request.data.get("map_link"),
        is_urgent=_parse_bool(request.data.get("is_urgent"), default=False),
        is_approved=False,
        created_by="corporate",
        authorization_letter=request.FILES.get("authorization_letter"),  # ← new
    )

    Notification.objects.create(
        title="New Camp Submitted",
        message=f'"{camp.title}" waiting for approval - document attached',
        type="camp"
    )

    return Response({"success": True})

@api_view(["PATCH"])
@permission_classes([AllowAny])
def approve_camp(request, camp_id):
    try:
        camp = DonationCamp.objects.get(id=camp_id)
        camp.is_approved = True
        camp.is_rejected = False
        camp.rejection_reason = ""
        camp.rejected_at = None
        camp.save()

        return Response({"success": True, "message": "Camp approved"})
    except DonationCamp.DoesNotExist:
        return Response({"success": False, "message": "Not found"}, status=404)

    
@api_view(["POST", "DELETE"])
@permission_classes([AllowAny])
def reject_camp(request, camp_id):
    try:
        camp = DonationCamp.objects.get(id=camp_id)
        reason = (request.data.get("reason", "") or "").strip()
        camp.is_approved = False
        camp.is_rejected = True
        camp.rejection_reason = reason
        camp.rejected_at = timezone.now()
        camp.save(update_fields=["is_approved", "is_rejected", "rejection_reason", "rejected_at"])

        return Response({"success": True, "message": "Camp rejected"})
    except DonationCamp.DoesNotExist:
        return Response({"success": False}, status=404)


# ================= ESCALATION STATUS (LOCATION 9) =================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def admin_escalation_status(request, request_id):
    """
    Returns live escalation progress for a blood request.
    READ-ONLY - never starts a new task. Tasks are started only in
    admin_approve_blood_request().
    """
    from blood_requests.models import BloodRequest
    from adminpanel.models import BloodRequestEscalation
    import logging
    logger = logging.getLogger(__name__)
 
    try:
        blood_request = BloodRequest.objects.get(id=request_id)
    except BloodRequest.DoesNotExist:
        return Response({"error": "Blood request not found"}, status=404)
 
    # Access control: staff see all; patient sees own request only
    if not (getattr(request.user, "is_staff", False) or
            getattr(request.user, "is_superuser", False)):
        patient_email = getattr(
            getattr(blood_request, "patient", None), "emailaddress", None
        )
        if not patient_email or request.user.username != patient_email:
            return Response({"error": "Forbidden"}, status=403)
 
    # Get or create escalation record - but DO NOT start a new task here
    escalation, created = BloodRequestEscalation.objects.get_or_create(
        blood_request=blood_request,
        defaults={"hospital": blood_request.created_by_hospital}
    )
 
    if created:
        logger.info(
            f"Created missing escalation record for request #{request_id} "
            "(approve endpoint should have done this)"
        )
        # Only start notifications if the request is actually approved and
        # we somehow missed creating the escalation in admin_approve_blood_request
        if blood_request.status == "approved":
            try:
                from celery_task import orchestrate_tiered_notification
                orchestrate_tiered_notification.delay(blood_request.id)
            except Exception as exc:
                logger.error(f"Could not start notification for #{request_id}: {exc}")
 
    stock_found = bool((escalation.blood_bank_units or 0) > 0 or (escalation.hospital_stock_details or {}))
    no_match_found = bool(
        blood_request.status in {'no_match', 'incomplete'}
        or (
            escalation.completed_at
            and not escalation.success
            and not stock_found
            and not blood_request.accepted_donor_id
        )
    )

    return Response({
        "request_id": request_id,
        "status": "completed" if escalation.completed_at else "escalating",
        "tier_1": {
            "completed": escalation.tier_1_completed is not None,
            "donors_notified": escalation.tier_1_donor_count or 0,
        },
        "tier_2": {
            "completed": escalation.tier_2_completed is not None,
            "donors_notified": escalation.tier_2_donor_count or 0,
        },
        "tier_3": {
            "completed": escalation.tier_3_completed is not None,
            "donors_notified": escalation.tier_3_donor_count or 0,
        },
        "tier_4": {
            "completed": escalation.tier_4_completed is not None,
            "donors_notified": escalation.tier_4_donor_count or 0,
        },
        "stock_check": {
            "completed": escalation.blood_bank_checked is not None,
            "blood_bank_units": escalation.blood_bank_units or 0,
            "blood_bank_contact": {
                "contact_phone": getattr(settings, "BLOOD_BANK_CONTACT", ""),
                "contact_email": getattr(settings, "BLOOD_BANK_EMAIL", ""),
                "source_name": "Central Blood Bank",
            },
            "hospital_stock": escalation.hospital_stock_details or {},
        },
        "success": bool(escalation.success),
        "no_match_found": no_match_found,
        "final_message": (
    "No compatible donor or blood stock found after searching all tiers."
    if no_match_found else ""
),
        "total_donors_alerted": escalation.total_donors_alerted or 0,
        "completed_at": escalation.completed_at,
    })

# ================= NOTIFICATION LOGS (LOCATION 9) =================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def admin_notification_logs(request, request_id):
    """Get all notifications sent for a blood request"""
    # Access control mirrors escalation status endpoint
    try:
        escalation = BloodRequestEscalation.objects.get(blood_request_id=request_id)
        blood_request = escalation.blood_request
        if not (getattr(request.user, "is_staff", False) or getattr(request.user, "is_superuser", False)):
            patient_email = getattr(getattr(blood_request, "patient", None), "emailaddress", None)
            if not patient_email or request.user.username != patient_email:
                return Response({"error": "Forbidden"}, status=403)
    except BloodRequestEscalation.DoesNotExist:
        # Try to find the blood request and create escalation on-the-fly
        try:
            blood_request = BloodRequest.objects.get(id=request_id)
            # Access control check
            if not (getattr(request.user, "is_staff", False) or getattr(request.user, "is_superuser", False)):
                patient_email = getattr(getattr(blood_request, "patient", None), "emailaddress", None)
                if not patient_email or request.user.username != patient_email:
                    return Response({"error": "Forbidden"}, status=403)
            # Create escalation on-the-fly
            escalation = BloodRequestEscalation.objects.create(
                blood_request=blood_request,
                hospital=blood_request.hospital_location
            )
            logger.info(f"Created missing escalation record for request {request_id}")
            # Return the status response
            return Response({
                "request_id": request_id,
                "status": "escalating",
                "tier_1": {"completed": False, "donors_notified": 0},
                "tier_2": {"completed": False, "donors_notified": 0},
                "tier_3": {"completed": False, "donors_notified": 0},
                "tier_4": {"completed": False, "donors_notified": 0},
                "stock_check": {"completed": False, "blood_bank_units": 0, "hospital_stock": {}},
                "total_donors_alerted": 0,
                "completed_at": None
            })
        except BloodRequest.DoesNotExist:
            return Response({"error": "Blood request not found"}, status=404)

    logs = NotificationLog.objects.filter(
        blood_request_id=request_id
    ).order_by("-sent_at")

    data = []
    for log in logs:
        data.append({
            "id": log.id,
            "donor": log.donor.email if log.donor else "System",
            "tier": log.tier,
            "distance_km": log.distance_km,
            "type": log.notification_type,
            "status": log.status,
            "sent_at": log.sent_at,
            "error": log.error_message
        })
    return Response(data)


# ===============================================================
# ADD THESE VIEWS TO adminpanel/views.py
# Import requirements already exist in your views.py
# Just paste these functions at the bottom
# ===============================================================

from django.db.models import Count, Q, Avg
from django.db.models.functions import TruncDate, TruncMonth, TruncWeek
from datetime import timedelta
from django.utils import timezone
from collections import defaultdict


# �"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"�
# HELPER (already exists in your views.py)
# def get_date_range(request): ...  ← reuse it
# �"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"�


# ===============================================================
# 1. DONATION TRENDS OVER TIME
# GET /api/admin/analytics/donation-trends/
# ===============================================================
@api_view(["GET"])
@permission_classes([AllowAny])
def analytics_donation_trends(request):
    start, end = get_date_range(request)
    delta = (end - start).days

    labels, completed, approved, pending, rejected = [], [], [], [], []

    if delta <= 30:
        cursor = start.date()
        while cursor <= end.date():
            qs = BloodRequest.objects.filter(created_at__date=cursor)
            labels.append(cursor.strftime("%d %b"))
            completed.append(qs.filter(status="completed").count())
            approved.append(qs.filter(status="approved").count())
            pending.append(qs.filter(status="pending").count())
            rejected.append(qs.filter(status="rejected").count())
            cursor += timedelta(days=1)

    elif delta <= 90:
        cursor = start
        while cursor < end:
            week_end = min(cursor + timedelta(days=7), end)
            qs = BloodRequest.objects.filter(created_at__gte=cursor, created_at__lt=week_end)
            labels.append(cursor.strftime("%d %b"))
            completed.append(qs.filter(status="completed").count())
            approved.append(qs.filter(status="approved").count())
            pending.append(qs.filter(status="pending").count())
            rejected.append(qs.filter(status="rejected").count())
            cursor = week_end
    else:
        from dateutil.relativedelta import relativedelta
        months = max(1, delta // 30)
        now_dt = timezone.now()
        for i in range(months - 1, -1, -1):
            ms = (now_dt.replace(day=1) - relativedelta(months=i))
            me = ms + relativedelta(months=1)
            if ms < start: ms = start
            if me > end:   me = end
            qs = BloodRequest.objects.filter(created_at__gte=ms, created_at__lt=me)
            labels.append(ms.strftime("%b %Y"))
            completed.append(qs.filter(status="completed").count())
            approved.append(qs.filter(status="approved").count())
            pending.append(qs.filter(status="pending").count())
            rejected.append(qs.filter(status="rejected").count())

    total = sum(completed) + sum(approved) + sum(pending) + sum(rejected)
    fulfillment_rate = round((sum(completed) / total * 100), 1) if total else 0

    return Response({
        "labels": labels,
        "completed": completed,
        "approved": approved,
        "pending": pending,
        "rejected": rejected,
        "summary": {
            "total": total,
            "completed": sum(completed),
            "fulfillment_rate": fulfillment_rate,
        }
    })


# ===============================================================
# 2. BLOOD TYPE DEMAND VS SUPPLY
# GET /api/admin/analytics/demand-supply/
# ===============================================================
@api_view(["GET"])
@permission_classes([AllowAny])
def analytics_demand_supply(request):
    start, end = get_date_range(request)

    demand = {}
    for bt in BLOOD_TYPES:
        demand[bt] = BloodRequest.objects.filter(
            blood_type=bt,
            created_at__gte=start,
            created_at__lte=end
        ).count()

    # Supply from BloodStock (bank = hospital is None)
    supply = {}
    for bt in BLOOD_TYPES:
        units = [
            available_units(s)
            for s in BloodStock.objects.filter(blood_type=bt)
        ]
        supply[bt] = sum(units)

    # fulfilled = completed requests per blood type
    fulfilled = {}
    for bt in BLOOD_TYPES:
        fulfilled[bt] = BloodRequest.objects.filter(
            blood_type=bt,
            status="completed",
            created_at__gte=start,
            created_at__lte=end
        ).count()

    return Response({
        "labels": BLOOD_TYPES,
        "demand":    [demand.get(bt, 0)    for bt in BLOOD_TYPES],
        "supply":    [supply.get(bt, 0)    for bt in BLOOD_TYPES],
        "fulfilled": [fulfilled.get(bt, 0) for bt in BLOOD_TYPES],
    })


# ===============================================================
# 3. HOSPITAL PERFORMANCE STATS
# GET /api/admin/analytics/hospital-performance/
# ===============================================================
@api_view(["GET"])
@permission_classes([AllowAny])
def analytics_hospital_performance(request):
    start, end = get_date_range(request)

    hospitals = Hospital.objects.filter(is_active=True).prefetch_related("profile")

    data = []
    for h in hospitals:
        requests_qs = BloodRequest.objects.filter(
            hospital_location__name=h.name,
            created_at__gte=start,
            created_at__lte=end
        )
        total = requests_qs.count()
        completed = requests_qs.filter(status="completed").count()
        pending = requests_qs.filter(status="pending").count()
        approved = requests_qs.filter(status="approved").count()
        rejected = requests_qs.filter(status="rejected").count()

        rate = round((completed / total * 100), 1) if total else 0

        stock_units = [available_units(s) for s in BloodStock.objects.filter(hospital=h)]
        total_stock = sum(stock_units)

        data.append({
            "hospital": h.name,
            "district": h.profile.district if hasattr(h, "profile") else "-",
            "total_requests": total,
            "completed": completed,
            "pending": pending,
            "approved": approved,
            "rejected": rejected,
            "fulfillment_rate": rate,
            "total_stock": total_stock,
        })

    # Sort by total requests desc
    data.sort(key=lambda x: x["total_requests"], reverse=True)

    return Response({
        "hospitals": data,
        "summary": {
            "total_hospitals": len(data),
            "avg_fulfillment": round(
                sum(d["fulfillment_rate"] for d in data) / len(data), 1
            ) if data else 0,
        }
    })


# ===============================================================
# 4. DONOR ACTIVITY & RETENTION
# GET /api/admin/analytics/donor-activity/
# ===============================================================
@api_view(["GET"])
@permission_classes([AllowAny])
def analytics_donor_activity(request):
    start, end = get_date_range(request)

    # New donors registered in period
    new_donors = Donor.objects.filter(
        created_on__gte=start,
        created_on__lte=end
    ).count()

    # Approved donors
    approved_donors = Donor.objects.filter(is_approved=True).count()
    pending_donors  = Donor.objects.filter(is_approved=False, is_profile_completed=True).count()

    # Blood type breakdown of donors
    bt_breakdown = (
        Donor.objects.filter(is_approved=True)
        .values("blood_type")
        .annotate(count=Count("id"))
        .order_by("blood_type")
    )

    # Active donors (accepted at least one request in period)
    active_donors = BloodRequest.objects.filter(
        status__in=["completed", "approved"],
        created_at__gte=start,
        created_at__lte=end,
        accepted_donor__isnull=False
    ).values("accepted_donor").distinct().count()

    # Trend: new donors per period bucket
    delta = (end - start).days
    trend_labels, trend_counts = [], []

    if delta <= 30:
        cursor = start.date()
        while cursor <= end.date():
            trend_labels.append(cursor.strftime("%d %b"))
            trend_counts.append(
                Donor.objects.filter(created_on__date=cursor).count()
            )
            cursor += timedelta(days=1)
    else:
        from dateutil.relativedelta import relativedelta
        cursor = start
        while cursor < end:
            week_end = min(cursor + timedelta(days=7), end)
            trend_labels.append(cursor.strftime("%d %b"))
            trend_counts.append(
                Donor.objects.filter(
                    created_on__gte=cursor,
                    created_on__lt=week_end
                ).count()
            )
            cursor = week_end

    return Response({
        "summary": {
            "total_approved": approved_donors,
            "pending":        pending_donors,
            "new_in_period":  new_donors,
            "active_donors":  active_donors,
        },
        "blood_type_breakdown": {
            "labels": [d["blood_type"] for d in bt_breakdown],
            "values": [d["count"]      for d in bt_breakdown],
        },
        "trend": {
            "labels": trend_labels,
            "values": trend_counts,
        }
    })


# ===============================================================
# 5. REQUEST FULFILLMENT RATES
# GET /api/admin/analytics/fulfillment/
# ===============================================================
@api_view(["GET"])
@permission_classes([AllowAny])
def analytics_fulfillment(request):
    start, end = get_date_range(request)

    qs = BloodRequest.objects.filter(created_at__gte=start, created_at__lte=end)

    total     = qs.count()
    completed = qs.filter(status="completed").count()
    approved  = qs.filter(status="approved").count()
    pending   = qs.filter(status="pending").count()
    rejected  = qs.filter(status="rejected").count()

    rate = round((completed / total * 100), 1) if total else 0

    # By urgency
    urgency_data = (
        qs.values("urgency")
        .annotate(
            total=Count("id"),
            done=Count("id", filter=Q(status="completed"))
        )
        .order_by("urgency")
    )

    # By blood type
    bt_data = (
        qs.values("blood_type")
        .annotate(
            total=Count("id"),
            done=Count("id", filter=Q(status="completed"))
        )
        .order_by("blood_type")
    )

    # Funnel
    return Response({
        "summary": {
            "total":     total,
            "completed": completed,
            "approved":  approved,
            "pending":   pending,
            "rejected":  rejected,
            "rate":      rate,
        },
        "by_urgency": [
            {
                "urgency": d["urgency"] or "Unknown",
                "total":   d["total"],
                "completed": d["done"],
                "rate": round(d["done"] / d["total"] * 100, 1) if d["total"] else 0
            }
            for d in urgency_data
        ],
        "by_blood_type": [
            {
                "blood_type": d["blood_type"],
                "total":      d["total"],
                "completed":  d["done"],
                "rate": round(d["done"] / d["total"] * 100, 1) if d["total"] else 0
            }
            for d in bt_data
        ],
    })


# ===============================================================
# 6. GEOGRAPHIC / DISTRICT BREAKDOWN
# GET /api/admin/analytics/geographic/
# ===============================================================
@api_view(["GET"])
@permission_classes([AllowAny])
def analytics_geographic(request):
    start, end = get_date_range(request)

    # Requests by district
    district_requests = (
        BloodRequest.objects
        .filter(created_at__gte=start, created_at__lte=end)
        .exclude(district__isnull=True)
        .exclude(district__exact="")
        .values("district")
        .annotate(
            total=Count("id"),
            completed=Count("id", filter=Q(status="completed")),
            pending=Count("id", filter=Q(status="pending")),
        )
        .order_by("-total")[:15]
    )

    # Donors by city (Donor model has no district field — use city)
    donor_by_city = (
        Donor.objects.filter(is_approved=True)
        .exclude(city__isnull=True)
        .exclude(city__exact="")
        .values("city")
        .annotate(count=Count("id"))
        .order_by("-count")[:15]
    )

    # Fallback to state if city is also empty for all donors
    if not donor_by_city.exists():
        donor_by_city = (
            Donor.objects.filter(is_approved=True)
            .exclude(state__isnull=True)
            .exclude(state__exact="")
            .values("state")
            .annotate(count=Count("id"))
            .order_by("-count")[:15]
        )
        donors_by_district = [
            {"district": d["state"], "count": d["count"]}
            for d in donor_by_city
        ]
    else:
        donors_by_district = [
            {"district": d["city"], "count": d["count"]}
            for d in donor_by_city
        ]

    return Response({
        "requests_by_district": [
            {
                "district":  d["district"],
                "total":     d["total"],
                "completed": d["completed"],
                "pending":   d["pending"],
                "rate": round(d["completed"] / d["total"] * 100, 1) if d["total"] else 0
            }
            for d in district_requests
        ],
        "donors_by_district": donors_by_district,
    })


# ===============================================================
# 7. KPI SUMMARY (single endpoint for top cards)
# GET /api/admin/analytics/kpi/
# ===============================================================
@api_view(["GET"])
@permission_classes([AllowAny])
def analytics_kpi(request):
    start, end = get_date_range(request)

    # Previous period for delta calculation
    delta_days = (end - start).days
    prev_start = start - timedelta(days=delta_days)
    prev_end   = start

    def pct_change(current, previous):
        if previous == 0:
            return 100 if current > 0 else 0
        return round(((current - previous) / previous) * 100, 1)

    completed_statuses = ["completed", "donation_complete", "donation_approved", "request_completed", "donation_completed"]

    # Current period
    cur_requests  = BloodRequest.objects.filter(created_at__gte=start, created_at__lte=end).count()
    cur_completed = BloodRequest.objects.filter(created_at__gte=start, created_at__lte=end, status__in=completed_statuses).count()
    cur_donors    = Donor.objects.filter(created_on__gte=start, created_on__lte=end).count()
    cur_hospitals = Hospital.objects.filter(created_at__gte=start, created_at__lte=end).count()

    # Previous period
    prev_requests  = BloodRequest.objects.filter(created_at__gte=prev_start, created_at__lte=prev_end).count()
    prev_completed = BloodRequest.objects.filter(created_at__gte=prev_start, created_at__lte=prev_end, status__in=completed_statuses).count()
    prev_donors    = Donor.objects.filter(created_on__gte=prev_start, created_on__lte=prev_end).count()
    prev_hospitals = Hospital.objects.filter(created_at__gte=prev_start, created_at__lte=prev_end).count()

    rate     = round(cur_completed / cur_requests * 100, 1) if cur_requests else 0
    prev_rate= round(prev_completed / prev_requests * 100, 1) if prev_requests else 0

    return Response({
        "total_requests":    {"value": cur_requests,  "change": pct_change(cur_requests,  prev_requests)},
        "completed":         {"value": cur_completed, "change": pct_change(cur_completed, prev_completed)},
        "new_donors":        {"value": cur_donors,    "change": pct_change(cur_donors,    prev_donors)},
        "new_hospitals":     {"value": cur_hospitals, "change": pct_change(cur_hospitals, prev_hospitals)},
        "fulfillment_rate":  {"value": rate,           "change": pct_change(rate, prev_rate)},
        "total_approved_donors": Donor.objects.filter(is_approved=True).count(),
    })

@api_view(["GET"])
@permission_classes([AllowAny])
def admin_all_donations(request):

    # �"��"� Base queryset �" NO prefetch_related until we know the relation name �"��"�
    donations = BloodRequest.objects.select_related(
        'patient',
        'hospital_location',
        'accepted_donor',
    ).order_by('-created_at')

    # �"��"� Filters �"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"�
    status_f     = request.GET.get('status')
    blood_type_f = request.GET.get('blood_type')
    from_date    = request.GET.get('from')
    to_date      = request.GET.get('to')

    if status_f and status_f != 'all':
        donations = donations.filter(status=status_f)
    if blood_type_f and blood_type_f != 'all':
        donations = donations.filter(blood_type=blood_type_f)
    if from_date:
        donations = donations.filter(created_at__date__gte=from_date)
    if to_date:
        donations = donations.filter(created_at__date__lte=to_date)

    donation_ids = list(donations.values_list("id", flat=True))
    notification_map = {}
    donor_decline_map = {}
    if donation_ids:
        related_notifications = Notification.objects.filter(
            blood_request_id__in=donation_ids
        ).order_by("created_at")
        for n in related_notifications:
            notification_map[n.blood_request_id] = n
            if (n.type or "").lower() == "donor_request_rejected":
                donor_decline_map[n.blood_request_id] = True

    def _abs(field):
        try:
            return request.build_absolute_uri(field.url) if field else None
        except Exception:
            return None

    data = []
    for req in donations:

        # �"��"� patient �"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"�
        patient      = req.patient
        patient_name = patient.fullname if patient else "By Hospital"

        # �"��"� hospital �"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"�
        hosp          = req.hospital_location
        hospital_name = hosp.name     if hosp else None
        hospital_dist = hosp.district if hosp else None

        # �"��"� donor �"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"�
        donor = req.accepted_donor  # Donor model instance or None

        donor_id = donor_name = donor_blood_type = None
        donor_phone = donor_city = donor_email = None

        if donor:
            donor_id         = donor.id
            donor_name       = f"{donor.first_name or ''} {donor.last_name or ''}".strip()
            donor_blood_type = donor.blood_type
            donor_phone      = donor.phone_number
            donor_city       = donor.city
            donor_email      = donor.email

        latest_activity = notification_map.get(req.id)

        # �"��"� confirmation �" query DonationConfirmation directly �"��"��"��"��"��"��"��"��"��"��"��"��"��"��"�
        # Avoids any reverse-relation name guessing
        donor_confirmed   = False
        patient_confirmed = False
        conf_id           = None

        try:
            conf = DonationConfirmation.objects.filter(
                request=req
            ).order_by('-created_at').first()

            if conf is None:
                # try alternate field name
                conf = DonationConfirmation.objects.filter(
                    blood_request=req
                ).order_by('-created_at').first()

            if conf:
                donor_confirmed   = bool(conf.donor_confirmed)
                patient_confirmed = bool(conf.patient_confirmed)
                conf_id           = conf.id

        except Exception:
            pass

        data.append({
            "id":               req.id,
            "patient_name":     patient_name,
            "blood_type":       req.blood_type,
            "units":            req.units_required,
            "urgency":          req.urgency     or "",
            "reason":           req.reason      or "",
            "status":           req.status,
            "hospital":         hospital_name,
            "hospital_district":hospital_dist,
            "contact_name":     req.contact_name  or "",
            "contact_phone":    req.contact_phone or "",
            "required_date":    str(req.required_date) if req.required_date else None,
            "created_at":       req.created_at.isoformat()    if req.created_at    else None,
            "approved_at":      req.approved_at.isoformat()   if getattr(req, 'approved_at',  None) else None,
            "completed_at":     req.donation_date.isoformat() if req.donation_date else None,
            # source
            "source":           "donor" if donor else "blood_bank",
            # donor
            "donor_id":         donor_id,
            "donor_name":       donor_name,
            "donor_blood_type": donor_blood_type,
            "donor_phone":      donor_phone,
            "donor_city":       donor_city,
            "donor_email":      donor_email,
            # confirmation
            "donor_confirmed":   donor_confirmed,
            "patient_confirmed": patient_confirmed,
            "confirmation_id":   conf_id,
            # documents
            "hospital_doc":  _abs(req.hospital_doc),
            "doctor_note":   _abs(req.doctor_note),
            "latest_activity_type": latest_activity.type if latest_activity else None,
            "latest_activity_title": latest_activity.title if latest_activity else None,
            "latest_activity_message": latest_activity.message if latest_activity else None,
            "latest_activity_at": latest_activity.created_at.isoformat() if latest_activity else None,
            "has_donor_decline": bool(donor_decline_map.get(req.id)),
        })

    return JsonResponse({"data": data, "total": len(data)})


@api_view(["GET"])
@permission_classes([AllowAny])
def admin_donation_detail(request, donation_id):
    try:
        req = BloodRequest.objects.select_related(
            'patient', 'hospital_location', 'accepted_donor'
        ).get(id=donation_id)
    except BloodRequest.DoesNotExist:
        return JsonResponse({"error": "Not found"}, status=404)

    donor = req.accepted_donor

    # �"��"� confirmation �" direct query �"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"�
    conf = None
    try:
        conf = DonationConfirmation.objects.filter(
            request=req
        ).order_by('-created_at').first()

        if conf is None:
            conf = DonationConfirmation.objects.filter(
                blood_request=req
            ).order_by('-created_at').first()
    except Exception:
        pass

    # �"��"� donor block �"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"�
    donor_data = {}
    if donor:
        photo_url = None
        try:
            if donor.photo:
                photo_url = request.build_absolute_uri(donor.photo.url)
        except Exception:
            pass

        donor_data = {
            "id":         donor.id,
            "name":       f"{donor.first_name or ''} {donor.last_name or ''}".strip(),
            "blood_type": donor.blood_type,
            "phone":      donor.phone_number,
            "email":      donor.email,
            "city":       donor.city,
            "photo":      photo_url,
        }

    # �"��"� confirmation block �"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"�
    conf_data = None
    if conf:
        conf_data = {
            "donor_confirmed":   bool(conf.donor_confirmed),
            "patient_confirmed": bool(conf.patient_confirmed),
            "created_at":        conf.created_at.isoformat() if conf.created_at else None,
        }

    audit_logs = []
    try:
        audit_logs = list(
            Notification.objects.filter(blood_request=req)
            .order_by("created_at")
            .values("title", "message", "created_at", "type")
        )
    except Exception:
        pass

    timeline = []

    def add_timeline(event, time_value=None, by=None, details="", tone="neutral"):
        timeline.append({
            "event": event,
            "time": time_value.isoformat() if hasattr(time_value, "isoformat") else time_value,
            "by": by or "System",
            "details": details or "",
            "tone": tone,
        })

    add_timeline(
        "Request Created",
        req.created_at,
        by=req.patient.fullname if req.patient else "Hospital",
        details=f"{req.blood_type} - {req.units_required} unit(s)",
        tone="neutral",
    )

    donor_display_name = donor_data.get("name") if donor_data else None
    donor_display_name = donor_display_name or (donor.first_name if donor else None) or "Donor"
    seen_complete = False

    for log in audit_logs:
        log_type = (log.get("type") or "").lower()
        if log_type in {"alert", "audit", "system", "security_alert", "system_alert"}:
            continue

        log_time = log.get("created_at")
        log_details = log.get("message", "") or log.get("title", "")

        if log_type in {"blood_request_approved_by_admin", "blood_request_approved", "request_approved"}:
            add_timeline("Request Approved", log_time, by="Admin", details=log_details, tone="success")
        elif log_type in {"blood_request_rejected_by_admin", "request_rejected"}:
            add_timeline("Request Rejected", log_time, by="Admin", details=log_details, tone="danger")
        elif log_type == "donor_accept":
            add_timeline("Donor Accepted Request", log_time, by=donor_display_name, details=log_details, tone="info")
        elif log_type == "donor_request_rejected":
            add_timeline("Donor Declined Request", log_time, by=donor_display_name, details=log_details, tone="warning")
        elif log_type in {"completed", "request_completed", "donation_complete", "donation_completed"}:
            add_timeline("Donation Completed", log_time, by="System", details=log_details, tone="success")
            seen_complete = True

    if conf and conf.donor_confirmed:
        add_timeline(
            "Donor Confirmed Donation",
            conf.created_at,
            by=donor_display_name,
            details="Donation confirmed by donor.",
            tone="info",
        )

    if conf and conf.patient_confirmed:
        add_timeline(
            "Patient Confirmed Receipt",
            conf.created_at,
            by=req.patient.fullname if req.patient else "Patient",
            details="Patient confirmed receipt.",
            tone="info",
        )

    if req.status == "completed" and not seen_complete:
        add_timeline(
            "Donation Completed",
            req.donation_date or getattr(req, "updated_at", None),
            by="System",
            details="Donation marked complete.",
            tone="success",
        )

    return JsonResponse({
        "id": req.id,
        "timeline": timeline,
        "audit_logs": audit_logs,
        "donor": donor_data,
        "confirmation": conf_data,
    })

    # �"��"� timeline �"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"�
    timeline = []

    if req.created_at:
        timeline.append({
            "event": "Request Created",
            "time":  req.created_at.isoformat(),
            "by":    req.patient.fullname if req.patient else "Hospital",
        })

    if req.status in ('approved', 'completed', 'rejected'):
        approved_at = getattr(req, 'approved_at', None)
        timeline.append({
            "event": f"Request {req.status.title()}",
            "time":  approved_at.isoformat() if approved_at else None,
            "by":    "Admin",
        })

    if donor:
        timeline.append({
            "event": "Donor Accepted Request",
            "time":  None,
            "by":    donor.first_name or "Donor",
        })

    if conf and conf.donor_confirmed:
        timeline.append({
            "event": "Donor Confirmed Donation",
            "time":  None,
            "by":    donor_data.get("name", "Donor"),
        })

    if conf and conf.patient_confirmed:
        timeline.append({
            "event": "Patient Confirmed Receipt",
            "time":  None,
            "by":    req.patient.fullname if req.patient else "Patient",
        })

    if req.status == 'completed':
        timeline.append({
            "event": "Donation Completed",
            "time":  req.donation_date.isoformat() if req.donation_date else None,
            "by":    "System",
        })

    # �"��"� audit trail from Notification �"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"��"�
    audit_logs = []
    try:
        audit_logs = list(
            Notification.objects.filter(blood_request=req)
            .order_by('created_at')
            .values('title', 'message', 'created_at', 'type')
        )
    except Exception:
        pass

    return JsonResponse({
        "id":           req.id,
        "timeline":     timeline,
        "audit_logs":   audit_logs,
        "donor":        donor_data,
        "confirmation": conf_data,
    })


@api_view(["POST"])
@permission_classes([AllowAny])
def admin_complete_donation(request, donation_id):
    try:
        req = BloodRequest.objects.get(id=donation_id)
    except BloodRequest.DoesNotExist:
        return JsonResponse({"error": "Not found"}, status=404)

    req.status = 'completed'
    if not req.donation_date:
        req.donation_date = timezone.now()
    req.save()

    try:
        patient_name = req.patient.fullname if req.patient else "patient"
        Notification.objects.create(
            title="Blood Request Completed",
            message=f"Blood request #{donation_id} for {patient_name} marked complete by admin.",
            type="completed",
            is_read=False,
            blood_request=req,
        )
    except Exception:
        pass

    return JsonResponse({"success": True, "message": "Marked as completed"})


