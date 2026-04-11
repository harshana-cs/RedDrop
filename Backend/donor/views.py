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
from .models import Donation, DonationConfirmation


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
        "hospital": c.request.hospital,
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

    # ✅ CREATE DONATION HISTORY
    Donation.objects.create(
        donor=donor,
        hospital=blood_request.hospital_location,
        blood_type=blood_request.blood_type,
        date=timezone.now().date(),
        status="verified",
        next_donation_date=timezone.now().date() + timedelta(days=MIN_GAP_DAYS)
    )

    # 🔥 EXPIRE OTP **ONLY NOW**
    blood_request.status = "completed"
    blood_request.fulfilled = True
    # 🔔 ADMIN LOG
    Notification.objects.create(
    title="Request Completed",
    message=f"Request #{blood_request.id} completed successfully",
    type="completed"
)
    blood_request.otp = None           
    blood_request.otp_expires_at = None
    blood_request.save()

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

    # ✅ assign donor + lock request
    blood_request.accepted_donor = donor
    blood_request.fulfilled = True
    blood_request.save()

    from django.contrib.auth.models import User
    patient_user = User.objects.filter(
        username=blood_request.patient.emailaddress
    ).first()

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
        print("Patient user not found:", blood_request.patient.emailaddress)

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

    if not donor or not donor.is_approved:
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

from .models import Donor

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
    patient_user = User.objects.filter(
        username=blood_request.patient.emailaddress
    ).first()

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