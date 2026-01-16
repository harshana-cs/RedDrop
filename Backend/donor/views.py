from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from register_donor.models import Donor
from .serializers import DonorProfileSerializer, DonationSerializer, DonationCampSerializer
from .models import Donation
from adminpanel.models import DonationCamp


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_donor_profile(request):
    donor = Donor.objects.filter(email=request.user.username).first()

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


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_donor_dashboard_stats(request):
    donor = Donor.objects.filter(email=request.user.username).first()

    if not donor:
        return Response({"error": "Donor not found"}, status=404)

    # 🚫 NO donation logic yet
    return Response({
        "total_donations": 0,
        "verified_donations": 0,
        "pending_donations": 0,
        "next_eligible_days": 56,
        "is_approved": donor.is_approved,
    })

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def donor_profile(request):
    email = request.user.email

    try:
        donor = Donor.objects.get(email=email)
        serializer = DonorProfileSerializer(donor)
        return Response(serializer.data)
    except Donor.DoesNotExist:
        return Response({"error": "Donor not found"}, status=404)

# ===============================
# DONATION HISTORY
# ===============================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def donation_history(request):
    try:
        donor = Donor.objects.get(email=request.user.email)
        donations = Donation.objects.filter(donor=donor).order_by("-date")
        serializer = DonationSerializer(donations, many=True)
        return Response(serializer.data)
    except Donor.DoesNotExist:
        return Response({"error": "Donor not found"}, status=404)

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def donation_camps(request):
    camps = DonationCamp.objects.all().order_by("date")
    serializer = DonationCampSerializer(camps, many=True)
    return Response(serializer.data)
