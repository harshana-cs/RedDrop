
from django.db import transaction
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
import jwt
import traceback
from django.conf import settings
from blood_requests.views import is_donor_eligible, BLOOD_COMPATIBILITY,haversine
from .models import Hospital, HospitalApplication
from blood_requests.models import BloodRequest
from blood_stock.models import BloodStock, BloodStockHistory
from blood_stock.stock_utils import (
    BLOOD_TYPES,
    available_units,
    is_nearing_expiry,
    notify_stock_expiry_for_hospital,
    notify_stock_scarcity_for_hospital,
    stock_state,
)
from hospital.auth import get_hospital_from_token
import time
from adminpanel.models import Notification
from common.email_utils import send_branded_email
from adminpanel.models import HospitalAuditLog
from blood_requests.models import HospitalLocation
from blood_requests.utils import get_coordinates_from_osm
from register_donor.models import Donor
from donor.models import Donation
from adminpanel.models import BloodRequestEscalation

from datetime import date

MIN_GAP_DAYS = 56


def get_last_verified_donation_date(donor):
    last_verified = (
        Donation.objects.filter(donor=donor, status="verified")
        .order_by("-date")
        .first()
    )
    return last_verified.date if last_verified else None

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
        HospitalAuditLog.objects.create(
    hospital=None,
    action="hospital_application",
    description=f"{application.hospital_name} submitted hospital registration",
    metadata={
        "registration_number": application.registration_number,
        "email": application.email
    }
)
        Notification.objects.create(
    title="New Hospital Application",
    message=f"{application.hospital_name} submitted a registration request",
    type="hospital"
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
    HospitalAuditLog.objects.create(
    hospital=hospital,
    action="login",
    description=f"{hospital.name} logged into hospital dashboard",
    metadata={
        "username": hospital.username
    }
)
    return Response({
        "success": True,
        "token": token
    })


# ======================================================
# HOSPITAL PROFILE (JWT PROTECTED)
# ======================================================
@api_view(["GET", "PUT"])
@authentication_classes([])
@permission_classes([AllowAny])
def hospital_profile(request):

    hospital = get_hospital_from_token(request)
    if not hospital:
        return Response({"detail": "Unauthorized"}, status=401)

    # Get the approved hospital application
    application = HospitalApplication.objects.filter(
        registration_number=hospital.profile.registration_number,
        status="approved"
    ).first()

    profile = hospital.profile

    # =========================
    # GET PROFILE
    # =========================
    if request.method == "GET":

        HospitalAuditLog.objects.create(
            hospital=hospital,
            action="profile_view",
            description=f"{hospital.name} viewed hospital profile"
        )

        return Response({
            "hospital_id": hospital.id,
            "name": hospital.name,
            "username": hospital.username,

            # Registration data from HospitalApplication
            "registration_number": application.registration_number if application else profile.registration_number,
            "hospital_type": application.hospital_type if application else profile.hospital_type,
            "bed_capacity": application.bed_capacity if application else profile.bed_capacity,
            "year_established": application.year_established if application else profile.year_established,
            "blood_bank_type": application.blood_bank_type if application else profile.blood_bank_type,
            "website": application.website if application else profile.website,
            "email": application.email if application else profile.email,
            "contact_number": application.phone if application else profile.contact_number,
            "address": application.address if application else profile.address,
            "latitude": float(hospital.location.latitude) if hospital.location and hospital.location.latitude else None,
            "longitude": float(hospital.location.longitude) if hospital.location and hospital.location.longitude else None,
        })

    # =========================
    # UPDATE PROFILE
    # =========================
    if request.method == "PUT":

        profile.contact_number = request.data.get(
            "contact_number", profile.contact_number
        )

        profile.email = request.data.get(
            "email", profile.email
        )

        profile.address = request.data.get(
            "address", profile.address
        )

        profile.save()

        HospitalAuditLog.objects.create(
            hospital=hospital,
            action="profile_update",
            description=f"{hospital.name} updated hospital profile"
        )

        return Response({
            "success": True,
            "message": "Profile updated successfully"
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
    HospitalAuditLog.objects.create(
    hospital=hospital,
    action="dashboard_view",
    description=f"{hospital.name} opened hospital dashboard"
)

    req_qs = BloodRequest.objects.filter(created_by_hospital=hospital)
    total_requests = req_qs.count()
    approved_requests = req_qs.filter(status="approved").count()
    pending_requests = req_qs.filter(status="pending").count()
    completed_requests = req_qs.filter(status="completed").count()

    stock_qs = BloodStock.objects.filter(hospital=hospital)
    stock_map = {s.blood_type: s for s in stock_qs}
    stock_by_type = {}
    scarce_types = []
    unavailable_types = []
    expiring_rows = []
    critical_stock = 0
    total_stock = 0
    today = timezone.localdate()

    for bt in BLOOD_TYPES:
        stock = stock_map.get(bt)
        state = stock_state(stock)
        stock_by_type[bt] = state["units"]
        total_stock += state["units"]
        if state["scarcity"]:
            scarce_types.append(bt)
        if state["unavailable"]:
            unavailable_types.append(bt)
        if 0 < state["units"] < 5:
            critical_stock += 1
        if stock and state["units"] > 0 and is_nearing_expiry(stock.expiry_date, days=5, today=today):
            expiring_rows.append({
                "blood_type": bt,
                "units": state["units"],
                "expiry_date": stock.expiry_date,
            })

    notify_stock_scarcity_for_hospital(hospital, scarce_types, unavailable_types)
    notify_stock_expiry_for_hospital(hospital, expiring_rows, days=5)

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
        "completed_requests": completed_requests,
        "total_stock": total_stock,
        "critical_stock": critical_stock,
        "stock_by_type": stock_by_type,
        "recent_activity": activity_data,
        "scarcity_popup": {
            "show": bool(unavailable_types or scarce_types),
            "title": "Blood Stock Alert",
            "message": "Some blood types are low or unavailable. Please restock/rotate stock urgently.",
            "unavailable_blood_types": unavailable_types,
            "scarce_blood_types": scarce_types,
        },
        "expiry_popup": {
            "show": bool(expiring_rows),
            "title": "Blood Expiry Alert",
            "message": "Some blood units are nearing expiry within 5 days. Please use or rotate stock.",
            "expiring_units": expiring_rows,
        },
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

    qs = BloodRequest.objects.filter(created_by_hospital=hospital)

    if status_filter and status_filter != "all":
        qs = qs.filter(status=status_filter)

    qs = qs.select_related("patient", "created_by_hospital").order_by("-created_at")

    data = []

    for r in qs:
        data.append({
            "id": r.id,
           "patient_name": r.patient.fullname if r.patient else r.patient_name,
"hospital_name": r.created_by_hospital.name if r.created_by_hospital else None,

            "blood_type": r.blood_type,
            "units": r.units_required,
            "urgency": r.urgency,
            "status": r.status,
            "created_at": r.created_at,
        })

    return Response(data)


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

    data = []
    stock_map = {s.blood_type: s for s in BloodStock.objects.filter(hospital=hospital)}
    for bt in BLOOD_TYPES:
        stock = stock_map.get(bt)

        data.append({
            "blood_type": bt,
            "units": available_units(stock),
            "minimum_required": stock.minimum_required if stock else 10,
            "last_updated": stock.last_updated if stock else None,
            "expiry_date": stock.expiry_date if stock else None,
            "expired": bool(stock and stock.expiry_date and stock.expiry_date < timezone.localdate()),
        })

    return Response(data)


# ======================================================
# DONORS (JWT PROTECTED)
# ======================================================
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def hospital_donors(request):
    hospital = get_hospital_from_token(request)
    if not hospital:
        return Response({"detail": "Unauthorized"}, status=401)

    # Need hospital location to calculate distances
    hospital_location = hospital.location
    if not hospital_location or not hospital_location.latitude or not hospital_location.longitude:
        # Try to geocode if missing
        address = (hospital.profile.address or "").strip()
        lat, lon = get_coordinates_from_osm(hospital.name, address)
        if lat and lon:
            hospital_location, created = HospitalLocation.objects.get_or_create(
                name=hospital.name,
                district=address,
                defaults={"latitude": lat, "longitude": lon},
            )
            if not created and (hospital_location.latitude is None):
                hospital_location.latitude = lat
                hospital_location.longitude = lon
                hospital_location.save(update_fields=["latitude", "longitude"])
            hospital.location = hospital_location
            hospital.save(update_fields=["location"])
        else:
            return Response({"detail": "Hospital location not available"}, status=400)

    hosp_lat = hospital_location.latitude
    hosp_lon = hospital_location.longitude

    donors = Donor.objects.filter(is_approved=True)

    result = []
    for donor in donors:
        if not donor.latitude or not donor.longitude:
            continue

        distance = haversine(hosp_lat, hosp_lon, donor.latitude, donor.longitude)

        last_donation = get_last_verified_donation_date(donor)
        if last_donation is None:
            is_available = True  
        else:
            days_since = (date.today() - last_donation).days
            is_available = days_since >= MIN_GAP_DAYS
        result.append({
    "id": donor.id,
    "name": f"{donor.first_name} {donor.last_name}",
    "blood_type": donor.blood_type,
    "phone": donor.phone_number,
    "email": donor.email,
    "latitude": float(donor.latitude),
    "longitude": float(donor.longitude),
    "distance_km": round(distance, 2),
    "availability": "Available" if is_available else "Unavailable",
    "is_available": is_available,
    "last_donation": last_donation.isoformat() if last_donation else None,
    "city": donor.city if hasattr(donor, 'city') else None,
    "address": donor.address if hasattr(donor, 'address') else None,
})

    result.sort(key=lambda x: x["distance_km"])
    return Response(result)


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

# ======================================================
# CREATE BLOOD REQUEST (HOSPITAL SIDE)
# ======================================================
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def hospital_create_blood_request(request):

    hospital = get_hospital_from_token(request)

    if not hospital:
        return Response({"detail": "Unauthorized"}, status=401)

    try:
        blood_type = request.data.get("blood_type")
        units = request.data.get("units")

        if not blood_type or not units:
            return Response(
                {"error": "Blood type and units are required"},
                status=400
            )

        if not hospital.location:
            # Get hospital address and normalize to match unique constraint values.
            address = (hospital.profile.address or "").strip()

            lat, lon = get_coordinates_from_osm(hospital.name, address)

            hospital_location, created = HospitalLocation.objects.get_or_create(
                name=hospital.name,
                district=address,
                defaults={"latitude": lat, "longitude": lon},
            )

            if not created and (hospital_location.latitude is None or hospital_location.longitude is None):
                hospital_location.latitude = lat
                hospital_location.longitude = lon
                hospital_location.save(update_fields=["latitude", "longitude"])

            hospital.location = hospital_location
            hospital.save(update_fields=["location"])

        # Create blood request
        new_request = BloodRequest.objects.create(
            patient=None,
            patient_name=request.data.get("patient_name"),

            created_by_hospital=hospital,
            blood_type=blood_type,
            units_required=int(units),
            urgency=request.data.get("urgency") or "Normal",
            hospital_location=hospital.location,
            district=hospital.location.district,
            required_date=timezone.now().date(),
            reason=request.data.get("notes") or "Hospital Request",
            contact_name=hospital.name,
            contact_phone=hospital.profile.contact_number,
            hospital_doc=request.FILES.get("hospital_doc"),
            doctor_note=request.FILES.get("doctor_note"),
        )
        HospitalAuditLog.objects.create(
    hospital=hospital,
    action="blood_request_create",
    description=f"{hospital.name} created blood request for {units} units of {blood_type}",
    metadata={
        "blood_type": blood_type,
        "units": units,
        "urgency": request.data.get("urgency"),
        "request_id": new_request.id
    }
)
        Notification.objects.create(
            title="New Hospital Blood Request",
            message=f"{hospital.name} requested {units} units of {blood_type}",
            type="blood_request",
            hospital=None,  # Admin/global notification
            user=None,
            blood_request=new_request
        )

        return Response({
            "success": True,
            "id": new_request.id
        })

    except Exception as e:
        traceback.print_exc()
        return Response(
            {"success": False, "error": str(e)},
            status=400
        )
    
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def hospital_notifications(request):

    hospital = get_hospital_from_token(request)

    if not hospital:
        return Response({"detail": "Unauthorized"}, status=401)

    notifications = Notification.objects.filter(
        hospital=hospital
    ).order_by("-created_at")

    data = []

    for n in notifications:
      data.append({
        "id": n.id,
        "title": n.title,
        "message": n.message,
        "type": n.type,
        "request_id": n.blood_request.id if n.blood_request else None,
        "is_read": n.is_read,
        "created_at": n.created_at
})

    return Response(data)

@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def hospital_request_donors(request, request_id):

    hospital = get_hospital_from_token(request)
    if not hospital:
        return Response({"detail": "Unauthorized"}, status=401)

    blood_request = BloodRequest.objects.filter(
        id=request_id,
        created_by_hospital=hospital
    ).first()

    if not blood_request:
        return Response({"error": "Request not found"}, status=404)

    hospital_location = blood_request.hospital_location

    if not hospital_location:
        return Response({"error": "Hospital location missing"}, status=400)

    request_lat = hospital_location.latitude
    request_lon = hospital_location.longitude

    required_blood = blood_request.blood_type

    compatible_bloods = [
        donor_blood
        for donor_blood, receivers in BLOOD_COMPATIBILITY.items()
        if required_blood in receivers
    ]

    donors = Donor.objects.filter(
        is_approved=True,
        blood_type__in=compatible_bloods
    )

    matched = []

    for donor in donors:

        if not donor.latitude or not donor.longitude:
            continue

        distance = haversine(
            request_lat,
            request_lon,
            donor.latitude,
            donor.longitude
        )

        last_donation = get_last_verified_donation_date(donor)
        if last_donation is None:
            is_available = True
        else:
            days_since = (date.today() - last_donation).days
            is_available = days_since >= MIN_GAP_DAYS

        matched.append({
    "id": donor.id,
    "name": f"{donor.first_name} {donor.last_name}",
    "blood_type": donor.blood_type,
    "distance_km": round(distance, 2),
    "phone": donor.phone_number,
    "email": donor.email,
    "latitude": float(donor.latitude),
    "longitude": float(donor.longitude),
    "availability": "Available" if is_available else "Unavailable",
    "is_available": is_available,
    "last_donation": last_donation.isoformat() if last_donation else None,
    "city": donor.city if hasattr(donor, 'city') else None,
    "address": donor.address if hasattr(donor, 'address') else None,
})

    matched.sort(key=lambda x: x["distance_km"])

    return Response({
        "request_id": blood_request.id,
        "blood_type": required_blood,
        "hospital": hospital.name,
        "donors": matched[:10]
    })

@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def mark_notification_read(request, notification_id):

    hospital = get_hospital_from_token(request)

    if not hospital:
        return Response({"detail": "Unauthorized"}, status=401)

    notification = Notification.objects.filter(
        id=notification_id,
        hospital=hospital
    ).first()

    if not notification:
        return Response({"error": "Notification not found"}, status=404)

    notification.is_read = True
    notification.save()

    return Response({"success": True})


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def mark_all_notifications_read(request):

    hospital = get_hospital_from_token(request)
    if not hospital:
        return Response({"detail": "Unauthorized"}, status=401)

    Notification.objects.filter(
        hospital=hospital,
        is_read=False
    ).update(is_read=True)

    return Response({"success": True, "message": "All notifications marked as read"})


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def hospital_request_escalation_status(request, request_id):
    hospital = get_hospital_from_token(request)
    if not hospital:
        return Response({"detail": "Unauthorized"}, status=401)

    blood_request = BloodRequest.objects.filter(
        id=request_id,
        created_by_hospital=hospital
    ).first()
    if not blood_request:
        return Response({"error": "Request not found"}, status=404)

    escalation, _ = BloodRequestEscalation.objects.get_or_create(
        blood_request=blood_request,
        defaults={"hospital": hospital}
    )

    stock_found = bool((escalation.blood_bank_units or 0) > 0 or (escalation.hospital_stock_details or {}))
    no_match_found = bool(
        blood_request.status in {"no_match", "incomplete"}
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
            "We tried all donor tiers and stock checks, but no donor or stock was found yet."
            if no_match_found else ""
        ),
        "total_donors_alerted": escalation.total_donors_alerted or 0,
        "completed_at": escalation.completed_at,
    })


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def hospital_confirm_donor_receipt(request, request_id):
    hospital = get_hospital_from_token(request)
    if not hospital:
        return Response({"detail": "Unauthorized"}, status=401)

    blood_request = BloodRequest.objects.filter(
        id=request_id,
        created_by_hospital=hospital,
        status="approved",
    ).first()
    if not blood_request:
        return Response({"success": False, "message": "Approved request not found."}, status=404)

    if blood_request.patient_confirmed:
        return Response({"success": False, "message": "OTP already generated for this request."}, status=400)

    if not blood_request.accepted_donor:
        return Response(
            {"success": False, "message": "No donor has accepted this request yet."},
            status=400,
        )

    import random
    from datetime import timedelta
    from donor.models import DonationConfirmation

    otp = str(random.randint(1000, 9999))
    blood_request.patient_confirmed = True
    blood_request.otp = otp
    blood_request.otp_expires_at = timezone.now() + timedelta(hours=24)
    blood_request.save(update_fields=["patient_confirmed", "otp", "otp_expires_at"])

    DonationConfirmation.objects.update_or_create(
        request=blood_request,
        defaults={
            "donor": blood_request.accepted_donor,
            "patient_confirmed": True,
            "donor_confirmed": False,
        },
    )

    donor = blood_request.accepted_donor
    if donor and donor.email:
        try:
            send_branded_email(
                subject="RedDrop: Your Donation OTP - Please Verify",
                to=donor.email,
                title="Donation OTP Ready",
                lines=[
                    f"Hi {donor.first_name or 'Donor'},",
                    f"The hospital has confirmed blood handover for request #{blood_request.id} ({blood_request.blood_type}).",
                    "Use the OTP below to complete verification.",
                ],
                highlight_label="Verification OTP",
                highlight_value=otp,
                highlight_note="This OTP expires in 24 hours.",
                bullets=[
                    "Open your RedDrop donor dashboard",
                    "Enter the OTP to finish donation verification",
                ],
                cta_text="Open Donor Dashboard",
                cta_url="http://localhost:5500/donor_dashboard.html",
                footer_note="Thank you for helping save a life.",
                from_email=settings.EMAIL_HOST_USER,
                fail_silently=True,
            )
        except Exception:
            pass

    try:
        from django.contrib.auth.models import User
        donor_user = User.objects.filter(email__iexact=donor.email).first() if donor else None
        if donor_user:
            Notification.objects.create(
                user=donor_user,
                blood_request=blood_request,
                title="Donation OTP Ready",
                message=f"Hospital confirmed receipt. Your OTP is {otp}. Enter it in your donor dashboard.",
                type="donation_otp",
            )
    except Exception:
        pass

    return Response({"success": True, "confirmation_code": otp})


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def hospital_confirm_bank_fulfillment(request, request_id):
    hospital = get_hospital_from_token(request)
    if not hospital:
        return Response({"detail": "Unauthorized"}, status=401)

    blood_request = BloodRequest.objects.filter(
        id=request_id,
        created_by_hospital=hospital,
        status="approved",
    ).first()
    if not blood_request:
        return Response({"success": False, "message": "Approved request not found."}, status=404)

    esc = BloodRequestEscalation.objects.filter(blood_request=blood_request).first()
    has_stock = bool(
        esc
        and (
            (esc.blood_bank_units or 0) > 0
            or bool(esc.hospital_stock_details)
        )
    )
    if not has_stock:
        return Response(
            {"success": False, "message": "No blood bank / hospital stock has been confirmed for this request yet."},
            status=400,
        )

    blood_request.status = "completed"
    blood_request.donation_date = timezone.now()
    blood_request.fulfilled = True
    blood_request.patient_confirmed = True
    blood_request.otp = None
    blood_request.otp_expires_at = None
    blood_request.save()

    try:
        Notification.objects.create(
            title="Request Completed (Hospital Stock)",
            message=f"Hospital request #{blood_request.id} completed via blood bank / nearby hospital stock.",
            type="request_completed",
            blood_request=blood_request,
        )
    except Exception:
        pass

    return Response({"success": True, "message": "Request marked as completed."})
