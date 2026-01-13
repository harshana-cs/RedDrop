from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from register_donor.models import Donor


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
