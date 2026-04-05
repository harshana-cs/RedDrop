from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count
# from Backend import hospital
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from .forms import BloodRequestForm
from .models import BloodRequest
from .serializers import BloodRequestSerializer
import random
from loginsignup.models import Patient
from donor.models import DonationConfirmation
from django.utils import timezone
from register_donor.models import Donor
from datetime import timedelta
from math import radians, sin, cos, sqrt, atan2
from .models import HospitalLocation
from adminpanel.models import Notification
from .utils import get_coordinates_from_osm

from .models import HospitalLocation

from django.contrib.auth.models import User

from rest_framework.decorators import api_view, permission_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

def haversine(lat1, lon1, lat2, lon2):
    if None in [lat1, lon1, lat2, lon2]:
        return None  # prevent crash

    from math import radians, sin, cos, sqrt, atan2

    R = 6371

    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)

    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))

    return R * c

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
# =========================================================
# API – PATIENT DASHBOARD & HISTORY
# =========================================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_user_requests(request):
    patient = Patient.objects.filter(
        emailaddress=request.user.username
    ).first()

    if not patient:
        return Response(
            {"success": False, "message": "Patient not found"},
            status=403
        )

    qs = BloodRequest.objects.filter(
        patient=patient
    ).order_by("-created_at")
    data = []
    for r in qs:
        data.append({
            "id": r.id,
            "blood_type": r.blood_type,
            "units_required": r.units_required,
            "urgency": r.urgency,
            "district": r.district,
            "hospital_name": r.hospital_location.name if r.hospital_location else None,  # ✅ FIXED
            "status": r.status,
            "created_at": r.created_at,
            "donation_date": r.donation_date,
        })

    # 📊 Stats
    total = qs.count()
    approved = qs.filter(status="approved").count()
    pending = qs.filter(status="pending").count()
    completed = qs.filter(status="completed").count()

    most_requested = (
        qs.values("blood_type")
        .annotate(total=Count("blood_type"))
        .order_by("-total")
        .first()
    )

    success_rate = round((completed / total) * 100) if total else 0

    return Response({
        "success": True,
        "patient_name": patient.fullname,
        "stats": {
            "total": total,
            "approved": approved,
            "pending": pending,
            "completed": completed,
            "most_requested_group": (
                most_requested["blood_type"] if most_requested else None
            ),
            "most_requested_count": (
                most_requested["total"] if most_requested else 0
            ),
            "success_rate": success_rate
        },
        "data": data 
    })

# =========================================================
# API – CREATE BLOOD REQUEST
# =========================================================

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_create_request(request):
    print("DATA  :", dict(request.data))
    print("FILES :", request.FILES)
    try:
        patient = Patient.objects.filter(
            emailaddress=request.user.username
        ).first()

        if not patient:
            return Response({"success": False, "message": "Patient not found"}, status=403)

        hospital_name = request.data.get("hospital")
        district      = request.data.get("district")

        if not hospital_name or not district:
            return Response({"message": "Hospital and district are required"}, status=400)

        hospital_location = HospitalLocation.objects.filter(
            name=hospital_name, district=district
        ).first()

        if not hospital_location:
            print("Calling OSM...")
            try:
                lat, lon = get_coordinates_from_osm(hospital_name, district)
                print(f"OSM result: {lat}, {lon}")
            except Exception as e:
                print(f"OSM FAILED: {e}")
                lat, lon = None, None

            hospital_location = HospitalLocation.objects.create(
                name=hospital_name, district=district,
                latitude=lat, longitude=lon
            )

        print("Running serializer...")
        serializer = BloodRequestSerializer(data=request.data)

        print("Validating...")
        if not serializer.is_valid():
            print("ERRORS:", serializer.errors)
            return Response(serializer.errors, status=400)

        print("Saving...")
        blood_request = serializer.save(
            patient=patient,
            hospital_location=hospital_location,
        )
        print("Saved! ID:", blood_request.id)

        try:
            Notification.objects.create(
                title="New Blood Request",
                message=f"{patient.fullname} requested {blood_request.blood_type} blood at {hospital_name}",
                type="blood_request",
                blood_request=blood_request,
                user=None,
                hospital=None,
            )
            print("Notification created.")
        except Exception as e:
            print(f"Notification failed (non-fatal): {e}")

        return Response({"success": True, "message": "Blood request submitted successfully"}, status=201)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({"message": str(e)}, status=500)
# =========================================================
# API – PATIENT CONFIRM RECEIPT (ONLY CONFIRMATION)
# =========================================================
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_patient_confirm_receipt(request, request_id):
    patient = Patient.objects.filter(
        emailaddress=request.user.username
    ).first()

    if not patient:
        return Response({"message": "Patient not found"}, status=403)

    blood_request = get_object_or_404(
        BloodRequest,
        id=request_id,
        patient=patient,
        status="approved"
    )

    if blood_request.patient_confirmed:
        return Response(
            {"message": "Already confirmed"},
            status=400
        )

    # 🔐 Generate OTP
    otp = str(random.randint(1000, 9999))

    # ✅ Store OTP (NO TIME EXPIRY)
    blood_request.patient_confirmed = True
    blood_request.fulfilled = False
    blood_request.otp = otp
    blood_request.otp_expires_at = None   # 🔥 IMPORTANT
    blood_request.save()

    # ✅ Create / update confirmation
    DonationConfirmation.objects.update_or_create(
        request=blood_request,
        defaults={
            "patient_confirmed": True,
            "donor_confirmed": False
        }
    )

    return Response({
        "success": True,
        "confirmation_code": otp
    })



# =========================================================
# API – CHECK APPROVED REQUEST (FOR DONORS TAB)
# =========================================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_patient_approved_request(request):
    patient = Patient.objects.filter(
        emailaddress=request.user.username
    ).first()

    if not patient:
        return Response({"approved": False}, status=403)

    approved_request = BloodRequest.objects.filter(
        patient=patient,
        status="approved"
    ).order_by("-created_at").first()

    if not approved_request:
        return Response({"approved": False})

    return Response({
        "approved": True,
        "request_id": approved_request.id,
        "blood_type": approved_request.blood_type,
        "district": approved_request.district
    })
def normalize_district(text):
    if not text:
        return ""

    text = text.lower()

    remove_words = [
        "district", "municipality", "metro", "metropolitan",
        "sub-metropolitan", "rural", "city"
    ]

    for word in remove_words:
        text = text.replace(word, "")

    return text.strip()
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_compatible_donors_for_patient(request):
    patient = Patient.objects.filter(
        emailaddress=request.user.username
    ).first()

    if not patient:
        return Response({"success": False}, status=403)

    blood_request = BloodRequest.objects.filter(
        patient=patient,
        status="approved"
    ).order_by("-created_at").first()

    if not blood_request:
        return Response({"success": True, "donors": []})

    hospital = blood_request.hospital_location

    if not hospital or not hospital.latitude or not hospital.longitude:
        return Response({
            "success": False,
            "message": "Hospital location not available"
        })

    request_lat = hospital.latitude
    request_lon = hospital.longitude

    required_blood = blood_request.blood_type

    compatible_donor_bloods = [
        donor_blood
        for donor_blood, receivers in BLOOD_COMPATIBILITY.items()
        if required_blood in receivers
    ]

    donors_qs = Donor.objects.filter(
        is_approved=True,
        blood_type__in=compatible_donor_bloods
    )

    matched_donors = []

    for donor in donors_qs:

        if not donor.latitude or not donor.longitude:
            continue

        if not is_donor_eligible(donor):
            continue

        distance = haversine(
            request_lat,
            request_lon,
            donor.latitude,
            donor.longitude
        )

        if distance <= 15:
            matched_donors.append({
                "id": donor.id,
                "name": f"{donor.first_name} {donor.last_name}".strip(),
                "blood_type": donor.blood_type,
                "distance_km": round(distance, 2),
                "phone": donor.phone_number,
                "email": donor.email,
            })

    matched_donors.sort(key=lambda x: x["distance_km"])

    return Response({
        "success": True,
        "request": {
            "id": blood_request.id,
            "blood_type": required_blood,
            "hospital": hospital.name,
        },
        "donors": matched_donors[:5]
    })

@api_view(["GET"])
@permission_classes([AllowAny])
def public_blood_requests(request):

    requests = (
        BloodRequest.objects
        .filter(status="pending")
        .select_related("patient")   # optimize query
    )

    data = []

    for r in requests:
        patient = r.patient

        data.append({
            "patient_name": (
                f"{patient.fullname}"
                if patient else "By Hospital"
            ),
            "blood_type": r.blood_type,
            "units": r.units_required,
            "hospital_name": r.hospital_location.name if r.hospital_location else None,
            "urgency": r.urgency,
        })

    return Response(data)

from donor.models import Donation
from datetime import timedelta
from django.utils import timezone

MIN_GAP_DAYS = 56

def is_donor_eligible(donor):

    last_donation = (
        Donation.objects
        .filter(donor=donor, status="verified")
        .order_by("-date")
        .first()
    )

    if not last_donation:
        return True

    next_allowed = last_donation.date + timedelta(days=MIN_GAP_DAYS)

    return timezone.now().date() >= next_allowed



from django.core.mail import send_mail
from django.conf import settings
def send_donor_alert(donor, blood_request, distance):

    subject = "Urgent Blood Donation Needed Near You"

    message = f"""
Hello {donor.first_name},

A blood donation request has been approved near your location.

Blood Group Needed: {blood_request.blood_type}
Hospital: {blood_request.hospital_location.name}
District: {blood_request.district}

Distance from you: {round(distance,2)} km

If you are willing to donate, please contact the patient:

Contact Person: {blood_request.contact_name}
Phone: {blood_request.contact_phone}

Thank you for being a life saver ❤️

RedDrop Blood Donation System
"""

    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [donor.email],
        fail_silently=True
    )
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_patient_notifications(request):
    notifications = Notification.objects.filter(
        user=request.user
    ).select_related(
        "blood_request__accepted_donor",
        "blood_request__hospital_location"
    ).order_by("-created_at")

    data = []

    for n in notifications:
        donor = None
        distance = None
        blood_request = n.blood_request  # ✅ use local variable

        if blood_request and blood_request.accepted_donor:
            donor = blood_request.accepted_donor

            if (donor.latitude and donor.longitude and
                blood_request.hospital_location and
                blood_request.hospital_location.latitude):
                distance = haversine(
                    blood_request.hospital_location.latitude,
                    blood_request.hospital_location.longitude,
                    donor.latitude,
                    donor.longitude
                )

        data.append({
            "id": n.id,
            "title": n.title,
            "message": n.message,
            "type": n.type,
            "request_id": blood_request.id if blood_request else None,
            "is_read": n.is_read,
            "created_at": str(n.created_at),
            "donor_name": f"{donor.first_name} {donor.last_name}".strip() if donor else None,
            "donor_phone": donor.phone_number if donor else None,
            "distance": round(distance, 2) if distance else None,
            # ✅ fulfilled=True means donor accepted
            "is_accepted": blood_request.fulfilled if blood_request else False,
        })

    return Response(data)

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_request_status(request, request_id):
    blood_request = get_object_or_404(BloodRequest, id=request_id)
    return Response({
        "request_id": blood_request.id,
        "status": blood_request.status,
        "fulfilled": blood_request.fulfilled,
        "blood_type": blood_request.blood_type,
        "hospital": blood_request.hospital_location.name if blood_request.hospital_location else None,
    })