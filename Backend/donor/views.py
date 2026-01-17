from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from register_donor.models import Donor
from blood_requests.models import BloodRequest
from adminpanel.models import DonationCamp

from .models import Donation, DonationConfirmation
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
    return Response(serializer.data)


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
# COMPATIBLE DONORS (PATIENT SIDE)
# ===============================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_compatible_donors(request, blood_type):
    donors = Donor.objects.filter(blood_type=blood_type, is_approved=True)

    data = [{
        "name": f"{d.first_name} {d.last_name}",
        "blood_type": d.blood_type,
        "district": d.city,
        "phone": d.phone_number,
    } for d in donors]

    return Response(data)


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
# DONOR CONFIRM VIA OTP
# ===============================
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_donor_confirm(request):
    donor = get_object_or_404(Donor, email=request.user.email, is_approved=True)

    request_id = request.data.get("request_id")
    otp = request.data.get("otp")

    if not request_id or not otp:
        return Response(
            {"message": "Request ID and OTP required"},
            status=400
        )

    blood_request = get_object_or_404(
        BloodRequest,
        id=request_id,
        assigned_donor=donor,
        status="approved"
    )

    if not blood_request.patient_confirmed:
        return Response(
            {"message": "Patient has not confirmed receipt yet"},
            status=400
        )

    if blood_request.otp != otp:
        return Response({"message": "Invalid OTP"}, status=400)

    if blood_request.otp_expires_at < timezone.now():
        return Response({"message": "OTP expired"}, status=400)

    # ✅ Update confirmation
    confirmation = get_object_or_404(
        DonationConfirmation,
        request=blood_request,
        donor=donor
    )
    confirmation.donor_confirmed = True
    confirmation.donation_date = timezone.now() 
    confirmation.save()

    # ✅ Create Donation record
    Donation.objects.create(
        donor=donor,
        hospital=blood_request.hospital,
        blood_type=blood_request.blood_type,
        date=timezone.now().date(),
        status="verified",
        next_donation_date=timezone.now().date() + timezone.timedelta(days=56)
    )

    # ✅ Finalize request
    blood_request.status = "completed"
    blood_request.fulfilled = True
    blood_request.otp = None
    blood_request.otp_expires_at = None
    blood_request.save()

    return Response({
        "success": True,
        "message": "Blood donation verified successfully ❤️"
    })
