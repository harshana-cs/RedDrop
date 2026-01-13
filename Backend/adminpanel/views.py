from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.conf import settings

from blood_requests.models import BloodRequest
from register_donor.models import Donor
from loginsignup.models import Patient


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
    requests = (
        BloodRequest.objects
        .filter(status="pending")
        .select_related("patient")   # ✅ ONLY patient
    )

    data = []

    for r in requests:
        patient = r.patient

        data.append({
            "id": r.id,

            # ✅ Name from Patient model (NOT User)
            "patient_name": (
                f"{patient.fullname}"
                if patient else "Unknown"
            ),

            "blood_type": r.blood_type,
            "hospital": r.hospital,
            "urgency": r.urgency,
            "units": r.units_required,
            "district": r.district,
            "contact": r.contact_phone,
            "date": r.required_date.strftime("%Y-%m-%d") if r.required_date else None,

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
            "created_on": d.created_on.strftime("%Y-%m-%d") if d.created_on else None,

            # Documents
            "citizenship_id": d.citizenship_id.url if d.citizenship_id else None,
            "photo": d.photo.url if d.photo else None,
        })

    return Response({
        "success": True,
        "count": len(data),
        "data": data
    })

@api_view(["POST"])
@permission_classes([AllowAny])
def admin_approve_blood_request(request, request_id):
    try:
        blood_request = BloodRequest.objects.get(id=request_id)
    except BloodRequest.DoesNotExist:
        return Response(
            {"success": False, "message": "Blood request not found"},
            status=404
        )

    blood_request.status = "approved"
    blood_request.save()

    return Response({
        "success": True,
        "message": "Blood request approved successfully"
    })
@api_view(["POST"])
@permission_classes([AllowAny])
def admin_reject_blood_request(request, request_id):
    reason = request.data.get("reason", "")

    try:
        blood_request = BloodRequest.objects.get(id=request_id)
    except BloodRequest.DoesNotExist:
        return Response(
            {"success": False, "message": "Blood request not found"},
            status=404
        )

    blood_request.status = "rejected"

    # Optional: save rejection reason if field exists
    if hasattr(blood_request, "rejection_reason"):
        blood_request.rejection_reason = reason

    blood_request.save()

    return Response({
        "success": True,
        "message": "Blood request rejected successfully"
    })
@api_view(["POST"])
@permission_classes([AllowAny])
def admin_reject_donor_registration(request, donor_id):
    reason = request.data.get("reason", "")

    try:
        donor = Donor.objects.get(id=donor_id)
    except Donor.DoesNotExist:
        return Response(
            {"success": False, "message": "Donor not found"},
            status=404
        )

    donor.is_approved = False
    donor.is_profile_completed = False  # optional but safe

    if hasattr(donor, "rejection_reason"):
        donor.rejection_reason = reason

    donor.save()

    return Response({
        "success": True,
        "message": "Donor rejected successfully"
    })

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

    donor.is_approved = True
    donor.save()

    return Response({
        "success": True,
        "message": "Donor approved successfully"
    })
