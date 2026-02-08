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
        hospital=blood_request.hospital,
        blood_type=blood_request.blood_type,
        date=timezone.now().date(),
        status="verified",
        next_donation_date=timezone.now().date() + timedelta(days=MIN_GAP_DAYS)
    )

    # 🔥 EXPIRE OTP **ONLY NOW**
    blood_request.status = "completed"
    blood_request.fulfilled = True
    blood_request.otp = None           # ← OTP invalidated here
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