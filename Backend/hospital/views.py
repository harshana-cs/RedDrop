
from django.db import transaction
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from django.db.models import Sum
import jwt
from django.conf import settings

from .models import Hospital, HospitalApplication
from blood_requests.models import BloodRequest
from blood_stock.models import BloodStock, BloodStockHistory
from hospital.auth import get_hospital_from_token
import time


# ======================================================
# HOSPITAL REGISTRATION (PUBLIC)
# ======================================================
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def hospital_register(request):
    data = request.data
    files = request.FILES

    required_fields = [
        "hospital_name", "registration_number", "hospital_type",
        "contact_person", "designation", "email", "phone", "address"
    ]

    for field in required_fields:
        if not data.get(field):
            return Response(
                {"success": False, "error": f"{field} is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

    if HospitalApplication.objects.filter(
        registration_number=data.get("registration_number")
    ).exists():
        return Response(
            {"success": False, "error": "Registration number already exists"},
            status=status.HTTP_400_BAD_REQUEST
        )

    with transaction.atomic():
        application = HospitalApplication.objects.create(
            hospital_name=data.get("hospital_name"),
            registration_number=data.get("registration_number"),
            hospital_type=data.get("hospital_type"),
            bed_capacity=data.get("bed_capacity") or None,
            year_established=data.get("year_established") or None,
            blood_bank_type=data.get("blood_bank_type") or None,

            contact_person=data.get("contact_person"),
            designation=data.get("designation"),
            email=data.get("email"),
            phone=data.get("phone"),
            address=data.get("address"),
            website=data.get("website") or None,

            has_emergency=data.get("has_emergency") == "true",
            has_icu=data.get("has_icu") == "true",
            has_operation_theater=data.get("has_operation_theater") == "true",
            has_blood_storage=data.get("has_blood_storage") == "true",
            has_blood_testing=data.get("has_blood_testing") == "true",
            hosts_donation_camp=data.get("hosts_donation_camp") == "true",

            registration_certificate=files.get("registration_certificate"),
            medical_license=files.get("medical_license"),
            blood_bank_license=files.get("blood_bank_license"),
            id_proof=files.get("id_proof"),
            authority_letter=files.get("authority_letter"),
        )

    return Response(
        {"success": True, "application_id": application.id},
        status=status.HTTP_201_CREATED
    )


# ======================================================
# HOSPITAL LOGIN (JWT)
# ======================================================
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def hospital_login(request):
    username = request.data.get("username")
    password = request.data.get("password")

    if not username or not password:
        return Response({"error": "Username and password required"}, status=400)

    try:
        hospital = Hospital.objects.get(username=username, is_active=True)
    except Hospital.DoesNotExist:
        return Response({"error": "Invalid credentials"}, status=401)

    if not hospital.check_password(password):
        return Response({"error": "Invalid credentials"}, status=401)

    payload = {
    "hospital_id": hospital.id,
    "iat": int(time.time()),
    "exp": int(time.time()) + (60 * 60 * 12),  # 12 hours
}

    token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
    return Response({
        "success": True,
        "token": token
    })


# ======================================================
# HOSPITAL PROFILE (JWT PROTECTED)
# ======================================================
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def hospital_profile(request):
    hospital = get_hospital_from_token(request)
    if not hospital:
        return Response({"detail": "Unauthorized"}, status=401)

    profile = hospital.profile

    return Response({
        "hospital_id": hospital.id,
        "name": hospital.name,
        "username": hospital.username,
        "district": profile.district,
        "contact_number": profile.contact_number,
        "email": profile.email,
        "registration_number": profile.registration_number,
        "hospital_type": profile.hospital_type,
        "bed_capacity": profile.bed_capacity,
    })


# ======================================================
# HOSPITAL DASHBOARD (JWT PROTECTED)
# ======================================================
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def hospital_dashboard(request):
    hospital = get_hospital_from_token(request)
    if not hospital:
        return Response({"detail": "Unauthorized"}, status=401)

    total_requests = BloodRequest.objects.filter(hospital=hospital).count()
    approved_requests = BloodRequest.objects.filter(hospital=hospital, status="approved").count()
    pending_requests = BloodRequest.objects.filter(hospital=hospital, status="pending").count()

    stock_qs = BloodStock.objects.filter(hospital=hospital)

    total_stock = stock_qs.aggregate(total=Sum("units"))["total"] or 0
    critical_stock = stock_qs.filter(units__lt=5).count()

    stock_by_type = {s.blood_type: s.units for s in stock_qs}

    recent_activity = BloodStockHistory.objects.filter(
        hospital=hospital
    ).order_by("-timestamp")[:5]

    activity_data = [
        {
            "type": "stock_add" if a.transaction_type == "add" else "stock_remove",
            "description": f"{a.transaction_type.upper()} {a.units} units of {a.blood_type}",
            "timestamp": a.timestamp,
        }
        for a in recent_activity
    ]

    return Response({
        "total_requests": total_requests,
        "approved_requests": approved_requests,
        "pending_requests": pending_requests,
        "total_stock": total_stock,
        "critical_stock": critical_stock,
        "stock_by_type": stock_by_type,
        "recent_activity": activity_data,
    })


# ======================================================
# BLOOD REQUESTS (JWT PROTECTED)
# ======================================================
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def hospital_blood_requests(request):
    hospital = get_hospital_from_token(request)
    if not hospital:
        return Response({"detail": "Unauthorized"}, status=401)

    status_filter = request.GET.get("status")

    qs = BloodRequest.objects.filter(hospital=hospital)
    if status_filter:
        qs = qs.filter(status=status_filter)

    return Response([
        {
            "id": r.id,
            "patient_name": r.patient.fullname if r.patient else "Unknown",
            "blood_type": r.blood_type,
            "units": r.units_required,
            "urgency": r.urgency,
            "status": r.status,
            "created_at": r.created_at,
        }
        for r in qs.order_by("-created_at")
    ])


# ======================================================
# BLOOD STOCK (JWT PROTECTED)
# ======================================================
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def hospital_blood_stock(request):
    hospital = get_hospital_from_token(request)
    if not hospital:
        return Response({"detail": "Unauthorized"}, status=401)

    BLOOD_TYPES = ["A+","A-","B+","B-","AB+","AB-","O+","O-"]

    data = []
    for bt in BLOOD_TYPES:
        stock = BloodStock.objects.filter(
            hospital=hospital, blood_type=bt
        ).first()

        data.append({
            "blood_type": bt,
            "units": stock.units if stock else 0,
            "minimum_required": stock.minimum_required if stock else 10,
            "last_updated": stock.last_updated if stock else None,
        })

    return Response(data)


# ======================================================
# DONORS (JWT PROTECTED)
# ======================================================
@api_view(["GET"])
@authentication_classes([])
def hospital_donors(request):
    hospital = get_hospital_from_token(request)
    if not hospital:
        return Response({"detail": "Unauthorized"}, status=401)

    return Response([])


# ======================================================
# STOCK HISTORY (JWT PROTECTED)
# ======================================================
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def hospital_stock_history(request):
    hospital = get_hospital_from_token(request)
    if not hospital:
        return Response({"detail": "Unauthorized"}, status=401)

    history = BloodStockHistory.objects.filter(
        hospital=hospital
    ).order_by("-timestamp")

    return Response([
        {
            "blood_type": h.blood_type,
            "transaction_type": h.transaction_type,
            "units": h.units,
            "source": h.source,
            "reason": h.reason,
            "performed_by": h.performed_by,
            "new_balance": h.new_balance,
            "timestamp": h.timestamp,
        }
        for h in history
    ])
