from django.utils import timezone
# from  import donor
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from datetime import timedelta
from register_donor.models import Donor
from blood_requests.models import BloodRequest
from adminpanel.models import DonationCamp
from adminpanel.models import Notification  
from common.email_utils import send_branded_email
from adminpanel.sms import send_sms
from .models import Donation, DonationConfirmation
from django.db.models import Count, Max
from django.contrib.auth.models import User


MIN_GAP_DAYS = 56
from donor.models import Donation, DonationConfirmation
from .serializers import (
    DonorProfileSerializer,
    DonationSerializer,
    DonationCampSerializer,
)

# ===============================
# DONOR PROFILE
# ===============================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_donor_profile(request):
    donor = Donor.objects.filter(email=request.user.email).first()

    if not donor:
        return Response({"error": "Donor not found"}, status=404)

    return Response({
        "first_name": donor.first_name,
        "last_name": donor.last_name,
        "email": donor.email,
        "blood_type": donor.blood_type,
        "is_approved": donor.is_approved,
        "profile_completed": donor.is_profile_completed,
    })


# ===============================
# DASHBOARD STATS
# ===============================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_donor_dashboard_stats(request):
    donor = Donor.objects.filter(email=request.user.email).first()
    if not donor:
        return Response({"error": "Donor not found"}, status=404)

    total = Donation.objects.filter(donor=donor).count()
    verified = Donation.objects.filter(donor=donor, status="verified").count()
    pending = Donation.objects.filter(donor=donor, status="pending").count()

    return Response({
        "total_donations": total,
        "verified_donations": verified,
        "pending_donations": pending,
        "next_eligible_days": 56,
        "is_approved": donor.is_approved,
    })


# ===============================
# DONOR FULL PROFILE
# ===============================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def donor_profile(request):
    donor = get_object_or_404(Donor, email=request.user.email)
    serializer = DonorProfileSerializer(donor)
    return Response(serializer.data)


# ===============================
# DONATION HISTORY
# ===============================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def donation_history(request):
    donor = get_object_or_404(Donor, email=request.user.email)
    donations = Donation.objects.filter(donor=donor).order_by("-date")
    serializer = DonationSerializer(donations, many=True)
    return Response({
    "donations": serializer.data
})



# ===============================
# DONATION CAMPS
# ===============================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def donation_camps(request):
    camps = DonationCamp.objects.all().order_by("date")
    serializer = DonationCampSerializer(camps, many=True)
    return Response(serializer.data)



# ===============================
# DONOR PENDING CONFIRMATIONS
# ===============================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_pending_confirmations(request):
    donor = Donor.objects.filter(email=request.user.email).first()
    if not donor:
        return Response([])

    confirmations = DonationConfirmation.objects.filter(
        donor=donor,
        patient_confirmed=True,
        donor_confirmed=False
    )

    data = [{
        "confirmation_id": c.id,
        "request_id": c.request.id,
        "blood_type": c.request.blood_type,
        "district": c.request.district,
        "hospital": c.request.hospital_location.name if c.request.hospital_location else None,
    } for c in confirmations]

    return Response(data)


# ===============================
# DONOR CONFIRM VIA OTP (FIXED)
# ===============================
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_donor_confirm(request):
    donor = get_object_or_404(
        Donor,
        email=request.user.email,
        is_approved=True
    )

    otp = request.data.get("otp")
    if not otp:
        return Response(
            {"success": False, "message": "OTP is required"},
            status=400
        )

    # 🔎 Find confirmation strictly by OTP
    confirmation = (
        DonationConfirmation.objects
        .select_related("request")
        .filter(
            patient_confirmed=True,
            donor_confirmed=False,
            request__otp=otp
        )
        .first()
    )

    if not confirmation:
        return Response(
            {"success": False, "message": "Invalid or already used OTP"},
            status=400
        )

    blood_request = confirmation.request

    # 🔒 Prevent OTP reuse
    if blood_request.otp is None:
        return Response(
            {"success": False, "message": "OTP already used"},
            status=400
        )

    # ✅ CONFIRM DONATION
    confirmation.donor = donor
    confirmation.donor_confirmed = True
    confirmation.donation_date = timezone.now()
    confirmation.save()

    # Use the patient receipt-confirmed date for donation history/certificate date.
    receipt_confirmed_dt = confirmation.created_at or timezone.now()
    receipt_confirmed_date = timezone.localtime(receipt_confirmed_dt).date()

    # ✅ CREATE DONATION HISTORY
    Donation.objects.create(
        donor=donor,
        hospital=blood_request.hospital_location.name if blood_request.hospital_location else "",
        blood_type=blood_request.blood_type,
        date=receipt_confirmed_date,
        status="verified",
        next_donation_date=receipt_confirmed_date + timedelta(days=MIN_GAP_DAYS)
    )

    # 🔥 EXPIRE OTP **ONLY NOW**
    blood_request.status = "completed"
    blood_request.fulfilled = True
    # 🔔 ADMIN LOG
    Notification.objects.create(
    title="Request Completed",
    message=f"Request #{blood_request.id} completed successfully",
    type="request_completed"
)
    blood_request.otp = None           
    blood_request.otp_expires_at = None
    blood_request.save()

    try:
        donor_name = donor.first_name or "Donor"
        if donor.email:
            send_branded_email(
                subject="RedDrop: Your donation has been completed",
                to=donor.email,
                title="Donation Completed",
                lines=[
                    f"Hi {donor_name},",
                    "Thank you for confirming your donation by OTP.",
                    "Your donation has been completed successfully in RedDrop.",
                    "Your support has helped save lives.",
                ],
                highlight_label="Status",
                highlight_value="Completed",
                highlight_note="Your donation record is now verified and stored in RedDrop.",
                footer_note="Thank you for being part of RedDrop and helping patients in need.",
            )

        if getattr(donor, "phone_number", None):
            send_sms(
                donor.phone_number,
                "RedDrop: Thank you for donating. You saved lives.",
            )
    except Exception:
        pass

    return Response({
        "success": True,
        "message": "Blood donation verified successfully ❤️"
    })

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_donor_eligibility(request):
    donor = get_object_or_404(Donor, email=request.user.email)

    # Get last verified donation
    last_donation = (
        Donation.objects
        .filter(donor=donor, status="verified")
        .order_by("-date")
        .first()
    )

    today = timezone.now().date()

    # If donor has never donated
    if not last_donation:
        return Response({
            "cooldown_active": False,
            "next_eligible_date": today,
            "days_remaining": 0,
            "minimum_gap_days": MIN_GAP_DAYS
        })

    next_eligible_date = last_donation.date + timedelta(days=MIN_GAP_DAYS)
    days_remaining = (next_eligible_date - today).days

    cooldown_active = days_remaining > 0

    return Response({
        "cooldown_active": cooldown_active,
        "last_donation_date": last_donation.date,
        "next_eligible_date": next_eligible_date,
        "days_remaining": max(days_remaining, 0),
        "minimum_gap_days": MIN_GAP_DAYS
    })

# ===============================
# DONOR ACCEPT BLOOD REQUEST
# ===============================
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_donor_accept_request(request):

    donor = Donor.objects.filter(email=request.user.email).first()
    if not donor:
        return Response({"error": "Donor not found"}, status=404)

    request_id = request.data.get("request_id")
    if not request_id:
        return Response({"error": "Request ID required"}, status=400)

    blood_request = get_object_or_404(BloodRequest, id=request_id)

    # 🚫 prevent multiple donors
    if blood_request.fulfilled:
        return Response(
            {"success": False, "message": "Another donor already accepted this request"},
            status=400
        )

    last_verified = (
        Donation.objects
        .filter(donor=donor, status="verified")
        .order_by("-date")
        .first()
    )
    if last_verified:
        days_since = (timezone.now().date() - last_verified.date).days
        if days_since < MIN_GAP_DAYS:
            return Response(
                {
                    "success": False,
                    "message": f"You are not eligible yet. Please wait {MIN_GAP_DAYS - days_since} more day(s).",
                },
                status=400,
            )

    # ✅ assign donor + lock request
    blood_request.accepted_donor = donor
    blood_request.fulfilled = True
    blood_request.save()

    from django.contrib.auth.models import User
    patient_email = blood_request.patient.emailaddress if blood_request.patient else None
    patient_user = User.objects.filter(username=patient_email).first() if patient_email else None

    if patient_user:
        # ✅ Guard: notify patient only once
        already_notified = Notification.objects.filter(
            user=patient_user,
            blood_request=blood_request,
            type="donor_accept"
        ).exists()

        if not already_notified:
            Notification.objects.create(
                user=patient_user,
                blood_request=blood_request,
                title="Donor Accepted Your Request",
                message=(
                    f"{donor.first_name} ({donor.blood_type}) accepted your request at "
                    f"{blood_request.hospital_location.name}. Contact: {donor.phone_number}"
                ),
                type="donor_accept"
            )

        # ✅ Guard: admin log only once
        admin_log_exists = Notification.objects.filter(
            blood_request=blood_request,
            type="donor_accept",
            user__isnull=True
        ).exists()

        if not admin_log_exists:
            Notification.objects.create(
                title="Donor Accepted Request",
                message=f"{donor.first_name} ({donor.blood_type}) accepted request #{blood_request.id}",
                type="donor_accept"
                # no user= field → admin only
            )
    else:
        print("Patient user not found for request:", blood_request.id)

    request_hospital = blood_request.created_by_hospital
    if request_hospital:
        hospital_notified = Notification.objects.filter(
            hospital=request_hospital,
            blood_request=blood_request,
            type="donor_accept"
        ).exists()

        if not hospital_notified:
            Notification.objects.create(
                hospital=request_hospital,
                blood_request=blood_request,
                title="Donor Accepted Request",
                message=(
                    f"{donor.first_name} ({donor.blood_type}) accepted request #{blood_request.id}. "
                    f"Contact: {donor.phone_number}"
                ),
                type="donor_accept"
            )

    return Response({
        "success": True,
        "message": "You accepted the donation request"
    })

# ===============================
# DONOR NOTIFICATIONS
# ===============================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_donor_notifications(request):
    donor = Donor.objects.filter(email=request.user.email).first()

    if not donor:
        return Response([])

    notifications = Notification.objects.filter(
        user=request.user
    ).order_by("-created_at")

    return Response([
        {
            "id": n.id,
            "title": n.title,
            "message": n.message,
            "type": n.type,   # ✅ ADD THIS
            "request_id": n.blood_request.id if n.blood_request else None,
            "is_read": n.is_read,
            "created_at": n.created_at
        }
        for n in notifications
    ])


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_donor_notification_mark_read(request, notification_id):
    Notification.objects.filter(id=notification_id, user=request.user).update(is_read=True)
    return Response({"success": True})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_donor_notifications_mark_all_read(request):
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return Response({"success": True})

def get_approved_donors_basic():
    donors = Donor.objects.filter(is_approved=True)

    result = []
    for donor in donors:
        result.append({
            "name": f"{donor.first_name or ''} {donor.last_name or ''}".strip(),
            "city": donor.city,
            "address": donor.address,
            "blood_type": donor.blood_type
        })

    return result
from django.http import JsonResponse

def approved_donors_basic_view(request):
    data = get_approved_donors_basic()
    return JsonResponse(data, safe=False)

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def all_donors(request):
    """
    GET /blood_requests/api/all-donors/
    Returns all approved donors.
    Each donor object matches the shape expected by the frontend
    (name, email, phone, blood_type, district/location,
     last_donation_date, is_eligible).
    """
    donors = Donor.objects.filter(is_approved=True).order_by("-created_on")
 
    data = []
    for donor in donors:
        # Calculate days since last donation if available
        last_donation_date = None
        days_since         = None
        is_eligible        = True  # default: never donated → eligible
 
        # If your Donation model has a FK to Donor, you can do:
        #   last = donor.donation_set.filter(status="completed").order_by("-donation_date").first()
        # For now we expose the raw field if it exists on the model,
        # otherwise leave it None. Swap the block below once your
        # Donation model is wired up.
        try:
            last = (
                Donation.objects
                .filter(donor=donor, status__in=["completed", "verified"])
                .order_by("-date")
                .first()
            )
            if last:
                last_donation_date = last.date.isoformat()
                days_since = (timezone.now().date() - last.date).days
                is_eligible = days_since >= 56
        except Exception:
            # Donation model not available yet — skip silently
            pass
 
        data.append({
            "id":                 donor.id,
            "name":               f"{donor.first_name or ''} {donor.last_name or ''}".strip(),
            "email":              donor.email or "",
            "phone":              donor.phone_number or "",
            "blood_type":         donor.blood_type or "",
            # 'district' maps to city in your model
            "district":           donor.city or donor.state or "",
            "location":           donor.address or "",
            "last_donation_date": last_donation_date,
            "days_since_last":    days_since,
            "is_eligible":        is_eligible,
            "is_approved":        donor.is_approved,
        })
 
    return Response({"donors": data, "total": len(data)})

# ===============================
# DONOR DECLINE BLOOD REQUEST
# ===============================
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_donor_decline_request(request):
    donor = Donor.objects.filter(email=request.user.email).first()
    if not donor:
        return Response({"error": "Donor not found"}, status=404)

    request_id = request.data.get("request_id")
    if not request_id:
        return Response({"error": "Request ID required"}, status=400)

    blood_request = get_object_or_404(BloodRequest, id=request_id)

    # Logic: If a donor declines, we ensure the request is NOT fulfilled 
    # so it remains visible to other potential donors.
    blood_request.accepted_donor = None
    blood_request.fulfilled = False
    blood_request.save()

    # --- Notifications ---
    from django.contrib.auth.models import User
    patient_user = None
    if blood_request.patient:
        patient_user = User.objects.filter(username=blood_request.patient.emailaddress).first()

    # 1. Notify the Patient (Optional, but good for UX)
    if patient_user:
        Notification.objects.create(
            user=patient_user,
            blood_request=blood_request,
            title="Donor Declined Request",
            message=f"A potential donor ({donor.blood_type}) has declined the request. It remains open for others.",
            type="donor_request_rejected"
        )

    # 2. System/Admin Log
    Notification.objects.create(
        title="Donor Declined Request",
        message=f"Donor {donor.first_name} declined request #{blood_request.id}",
        type="donor_request_rejected",
        blood_request=blood_request
        # user=None means it's a system/admin log
    )

    return Response({
        "success": True, 
        "message": "You have declined the request. It is now available for other donors."
    })


# ===============================
# CERTIFICATE + LEADERBOARD APIs
# ===============================
def _request_user_email(request):
    return (request.user.email or request.user.username or "").strip().lower()


def _certificate_serial(donation):
    return f"RDC-{donation.date.strftime('%Y%m%d')}-{donation.id:06d}"


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_donation_certificate(request, donation_id):
    """
    Returns certificate data payload for a specific donation.
    Frontend can use this payload with any custom certificate design.
    """
    donation = get_object_or_404(Donation.objects.select_related("donor"), id=donation_id)

    user_email = _request_user_email(request)
    donor_email = (donation.donor.email or "").strip().lower() if donation.donor else ""
    is_owner = donor_email and donor_email == user_email
    is_admin = bool(request.user.is_staff or request.user.is_superuser)

    if not (is_owner or is_admin):
        return Response({"success": False, "message": "Forbidden"}, status=403)

    donor_name = f"{donation.donor.first_name or ''} {donation.donor.last_name or ''}".strip()
    payload = {
        "success": True,
        "certificate": {
            "serial_number": _certificate_serial(donation),
            "issued_at": timezone.now().isoformat(),
            "title": "Blood Donation Certificate",
            "recipient_name": donor_name or "Donor",
            "blood_type": donation.blood_type,
            "hospital": donation.hospital,
            "donation_date": donation.date.isoformat() if donation.date else None,
            "certificate_date": donation.date.isoformat() if donation.date else None,
            "donation_id": donation.id,
            "status": donation.status,
        }
    }
    return Response(payload)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_donor_leaderboard(request):
    """
    Donor leaderboard by count of verified donations.
    Optional filters: ?year=YYYY&month=MM
    """
    year = request.GET.get("year")
    month = request.GET.get("month")

    qs = Donation.objects.filter(status="verified")
    if year and str(year).isdigit():
        qs = qs.filter(date__year=int(year))
    if month and str(month).isdigit():
        qs = qs.filter(date__month=int(month))

    rows = (
        qs.values("donor")
        .annotate(total_donations=Count("id"), latest_donation=Max("date"))
        .order_by("-total_donations", "-latest_donation", "donor")
    )

    donor_ids = [r["donor"] for r in rows if r.get("donor")]
    donor_map = {
        d.id: d for d in Donor.objects.filter(id__in=donor_ids)
    }

    me_email = _request_user_email(request)
    leaderboard = []
    my_rank = None
    for idx, row in enumerate(rows, start=1):
        donor = donor_map.get(row["donor"])
        if not donor:
            continue
        name = f"{donor.first_name or ''} {donor.last_name or ''}".strip() or "Donor"
        item = {
            "rank": idx,
            "donor_id": donor.id,
            "name": name,
            "blood_type": donor.blood_type or "",
            "city": donor.city or donor.state or "",
            "total_donations": row["total_donations"],
            "latest_donation": row["latest_donation"].isoformat() if row["latest_donation"] else None,
        }
        leaderboard.append(item)
        if (donor.email or "").strip().lower() == me_email:
            my_rank = idx

    return Response({
        "success": True,
        "year": int(year) if year and str(year).isdigit() else None,
        "month": int(month) if month and str(month).isdigit() else None,
        "leaderboard": leaderboard[:100],
        "my_rank": my_rank,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_leaderboard_certificate(request):
    """
    Certificate payload for leaderboard achievement.
    Rules:
    - donor must be in top 3
    - donor must have at least 1 verified donation in selected period
    Optional filters: ?year=YYYY&month=MM
    """
    year = request.GET.get("year")
    month = request.GET.get("month")

    qs = Donation.objects.filter(status="verified")
    if year and str(year).isdigit():
        qs = qs.filter(date__year=int(year))
    if month and str(month).isdigit():
        qs = qs.filter(date__month=int(month))

    rows = (
        qs.values("donor")
        .annotate(total_donations=Count("id"), latest_donation=Max("date"))
        .order_by("-total_donations", "-latest_donation", "donor")
    )

    me_email = _request_user_email(request)
    my_row = None
    my_rank = None
    donor_obj = None
    for idx, row in enumerate(rows, start=1):
        donor = Donor.objects.filter(id=row["donor"]).first()
        if donor and (donor.email or "").strip().lower() == me_email:
            my_row = row
            my_rank = idx
            donor_obj = donor
            break

    if not my_row or not donor_obj:
        return Response({
            "success": False,
            "eligible": False,
            "message": "No verified donations found for leaderboard period.",
        }, status=404)

    eligible = my_rank <= 3 and my_row["total_donations"] > 0
    if not eligible:
        return Response({
            "success": True,
            "eligible": False,
            "rank": my_rank,
            "total_donations": my_row["total_donations"],
            "message": "Leaderboard certificate is available for top 3 donors.",
        })

    donor_name = f"{donor_obj.first_name or ''} {donor_obj.last_name or ''}".strip() or "Donor"
    period = f"{year}-{str(month).zfill(2)}" if year and month else (str(year) if year else "All Time")
    serial = f"RDL-{period.replace('-', '')}-{donor_obj.id:06d}-{my_rank}"

    return Response({
        "success": True,
        "eligible": True,
        "certificate": {
            "serial_number": serial,
            "issued_at": timezone.now().isoformat(),
            "title": "Donor Leaderboard Achievement Certificate",
            "recipient_name": donor_name,
            "rank": my_rank,
            "period": period,
            "total_donations": my_row["total_donations"],
            "latest_donation": my_row["latest_donation"].isoformat() if my_row["latest_donation"] else None,
        }
    })
from django.core.files.storage import default_storage
from reportlab.lib.pagesizes import landscape, letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from io import BytesIO
from io import BytesIO
from django.http import FileResponse

import os
import random

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_download_donation_certificate(request, donation_id):
    """
    Download donation certificate as PDF using ReportLab
    """
    donation = get_object_or_404(Donation.objects.select_related("donor"), id=donation_id)
    
    user_email = _request_user_email(request)
    donor_email = (donation.donor.email or "").strip().lower() if donation.donor else ""
    is_owner = donor_email and donor_email == user_email
    is_admin = bool(request.user.is_staff or request.user.is_superuser)

    if not (is_owner or is_admin):
        return Response({"success": False, "message": "Forbidden"}, status=403)

    try:
        # Create PDF buffer
        pdf_buffer = BytesIO()
        pagesize = landscape(letter)
        width, height = pagesize
        
        # Create canvas with buffer
        c = canvas.Canvas(pdf_buffer, pagesize=pagesize)
        
        # Colors
        red_color = colors.HexColor("#B91C1C")
        gold_color = colors.HexColor("#FCD34D")
        dark_text = colors.HexColor("#1f2937")
        
        # Draw decorative border
        c.setLineWidth(2)
        c.setStrokeColor(red_color)
        c.rect(0.5*inch, 0.5*inch, width - 1*inch, height - 1*inch)
        
        # Draw corner decorations
        corner_size = 0.3*inch
        c.setLineWidth(3)
        c.setStrokeColor(red_color)
        
        # Top-left corner
        c.line(0.5*inch, height - 0.5*inch, 0.5*inch + corner_size, height - 0.5*inch)
        c.line(0.5*inch, height - 0.5*inch, 0.5*inch, height - 0.5*inch - corner_size)
        
        # Top-right corner
        c.line(width - 0.5*inch, height - 0.5*inch, width - 0.5*inch - corner_size, height - 0.5*inch)
        c.line(width - 0.5*inch, height - 0.5*inch, width - 0.5*inch, height - 0.5*inch - corner_size)
        
        # Bottom-left corner
        c.line(0.5*inch, 0.5*inch, 0.5*inch + corner_size, 0.5*inch)
        c.line(0.5*inch, 0.5*inch, 0.5*inch, 0.5*inch + corner_size)
        
        # Bottom-right corner
        c.line(width - 0.5*inch, 0.5*inch, width - 0.5*inch - corner_size, 0.5*inch)
        c.line(width - 0.5*inch, 0.5*inch, width - 0.5*inch, 0.5*inch + corner_size)
        
        # Title
        c.setFont("Helvetica-Bold", 48)
        c.setFillColor(red_color)
        c.drawCentredString(width/2, height - 1.5*inch, "CERTIFICATE OF HONOR")
        
        # Subtitle
        c.setFont("Helvetica", 12)
        c.setFillColor(dark_text)
        c.drawCentredString(width/2, height - 1.9*inch, "In Recognition of Generosity")
        
        # Decorative line
        c.setLineWidth(2)
        c.setStrokeColor(gold_color)
        c.line(1.5*inch, height - 2.2*inch, width - 1.5*inch, height - 2.2*inch)
        
        # Body text
        c.setFont("Helvetica", 16)
        c.setFillColor(dark_text)
        c.drawCentredString(width/2, height - 2.8*inch, "This certifies that")
        
        # Donor name (underlined)
        c.setFont("Helvetica-Bold", 32)
        c.setFillColor(red_color)
        donor_name = f"{donation.donor.first_name or ''} {donation.donor.last_name or ''}".strip()
        c.drawCentredString(width/2, height - 3.4*inch, donor_name)
        
        c.setStrokeColor(gold_color)
        c.setLineWidth(2)
        c.line((width/2) - 2.5*inch, height - 3.6*inch, (width/2) + 2.5*inch, height - 3.6*inch)
        
        # Details section
        c.setFont("Helvetica", 14)
        c.setFillColor(dark_text)
        y_pos = height - 4.3*inch
        
        c.drawCentredString(width/2, y_pos, "has generously donated blood through")
        y_pos -= 0.3*inch
        
        c.setFont("Helvetica-Bold", 14)
        c.drawCentredString(width/2, y_pos, "RedDrop Blood Donation Service")
        y_pos -= 0.6*inch
        
        # Donation details in boxes
        c.setFont("Helvetica", 11)
        box_width = 2*inch
        box_height = 0.6*inch
        
        details = [
            ("Date", donation.date.strftime("%B %d, %Y") if donation.date else "N/A"),
            ("Blood Type", donation.blood_type or "N/A"),
            ("Hospital", donation.hospital or "N/A"),
        ]
        
        x_positions = [1*inch, (width/2) - box_width/2, width - 3*inch]
        
        for idx, (label, value) in enumerate(details):
            x = x_positions[idx]
            c.setStrokeColor(red_color)
            c.setLineWidth(1)
            c.rect(x, y_pos - box_height, box_width, box_height, fill=0)
            
            c.setFont("Helvetica-Bold", 9)
            c.setFillColor(red_color)
            c.drawString(x + 0.1*inch, y_pos - 0.2*inch, label.upper())
            
            c.setFont("Helvetica", 11)
            c.setFillColor(dark_text)
            c.drawString(x + 0.1*inch, y_pos - 0.45*inch, str(value)[:25])
        
        y_pos -= 1*inch
        
        # Signature lines
        c.setFont("Helvetica", 10)
        c.setFillColor(dark_text)
        
        sig_y = y_pos - 0.5*inch
        sig_x1 = 1.5*inch
        sig_x2 = width - 2*inch
        
        # Left signature
        c.setLineWidth(1)
        c.setStrokeColor(dark_text)
        c.line(sig_x1, sig_y, sig_x1 + 1.5*inch, sig_y)
        left_signatures = ["Dr. S. Pradhan", "Dr. R. Karki", "Dr. A. Shrestha", "Dr. N. Bista"]
        c.setFont("Helvetica-Oblique", 12)
        c.setFillColor(colors.HexColor("#374151"))
        c.drawString(sig_x1 + 0.1*inch, sig_y + 0.08*inch, random.choice(left_signatures))
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(dark_text)
        c.drawString(sig_x1, sig_y - 0.25*inch, "Medical Director")
        
        # Right signature
        c.line(sig_x2, sig_y, sig_x2 + 1.5*inch, sig_y)
        right_signatures = ["A. Gautam", "K. Singh", "M. Adhikari", "P. Thapa", "R. Rana"]
        c.setFont("Helvetica-Oblique", 12)
        c.setFillColor(colors.HexColor("#374151"))
        c.drawString(sig_x2 + 0.1*inch, sig_y + 0.08*inch, random.choice(right_signatures))
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(dark_text)
        c.drawString(sig_x2, sig_y - 0.25*inch, "Authorized Officer")
        
        # Serial number
        serial = _certificate_serial(donation)
        c.setFont("Helvetica", 9)
        c.setFillColor(colors.HexColor("#666666"))
        c.drawString(1*inch, 0.8*inch, f"Serial: {serial}")
        
        # Heart seal
        c.setFont("Helvetica", 48)
        c.setFillColor(red_color)
        c.drawString(width - 1.8*inch, 0.5*inch, "❤")
        
        # ✅ CRITICAL: Save the canvas first
        c.save()
        
        # ✅ Reset buffer position for reading
        pdf_buffer.seek(0)
        
        filename = f"RedDrop_Certificate_{donation.id}.pdf"
        
        # ✅ Return the file response
        return FileResponse(
            pdf_buffer,
            as_attachment=True,
            filename=filename,
            content_type='application/pdf'
        )
        
    except Exception as e:
        import traceback
        print(f"Certificate Error: {str(e)}")
        print(traceback.format_exc())
        return Response({
            "success": False,
            "message": f"Error generating certificate: {str(e)}"
        }, status=500)

