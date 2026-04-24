from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count
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
from rest_framework import status
from .notifications import is_donor_eligible, get_compatible_donors, send_donor_alert

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

    qs = (
        BloodRequest.objects
        .filter(patient=patient)
        .select_related("hospital_location", "escalation")
        .order_by("-created_at")
    )
    data = []
    for r in qs:
        esc = getattr(r, "escalation", None)
        stock_found = bool(
            esc and (
                (esc.blood_bank_units or 0) > 0 or bool(esc.hospital_stock_details)
            )
        )
        completion_source = None
        if r.status == "completed":
            if r.accepted_donor_id:
                completion_source = "donor"
            elif stock_found:
                completion_source = "blood_bank"

        data.append({
            "id": r.id,
            "blood_type": r.blood_type,
            "units_required": r.units_required,
            "urgency": r.urgency,
            "district": r.district,
            "hospital_name": r.hospital_location.name if r.hospital_location else None,
            "status": r.status,
            "fulfilled": r.fulfilled,
            "patient_confirmed": r.patient_confirmed,
            "accepted_donor_id": r.accepted_donor_id,
            "stock_found": stock_found,
            "completion_source": completion_source,
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
    """
    Create a new blood request.
    Returns JSON response with 201 status.
    Does NOT redirect - returns JSON only.
    """
    print("\n" + "="*60)
    print("🔵 API CREATE REQUEST STARTED")
    print("="*60)
    
    print("DATA  :", dict(request.data))
    print("FILES :", request.FILES)
    
    try:
        # ========================================
        # STEP 1: Get Patient
        # ========================================
        print("\n📍 STEP 1: Getting patient...")
        patient = Patient.objects.filter(
            emailaddress=request.user.username
        ).first()
 
        if not patient:
            print("❌ Patient not found")
            return Response(
                {"success": False, "message": "Patient not found"},
                status=403
            )
        
        print(f"✅ Patient found: {patient.fullname}")
 
        # ========================================
        # STEP 2: Get Hospital & District
        # ========================================
        print("\n📍 STEP 2: Getting hospital and district...")
        hospital_name = request.data.get("hospital")
        district      = request.data.get("district")
 
        if not hospital_name or not district:
            print(f"❌ Missing: hospital={hospital_name}, district={district}")
            return Response(
                {"message": "Hospital and district are required"},
                status=400
            )
        
        print(f"✅ Hospital: {hospital_name}, District: {district}")
 
        # ========================================
        # STEP 3: Get or Create Hospital Location
        # ========================================
        print("\n📍 STEP 3: Getting hospital location...")
        hospital_location = HospitalLocation.objects.filter(
            name=hospital_name, district=district
        ).first()
 
        if not hospital_location:
            print("   Hospital location not found, creating...")
            hospital_location = HospitalLocation.objects.create(
                name=hospital_name, 
                district=district,
                latitude=None, 
                longitude=None
            )
            print(f"✅ Created hospital location ID: {hospital_location.id}")
            
            # Background geocoding (async)
            import threading
            def geocode_later(loc_id, name, district):
                try:
                    from .utils import get_coordinates_from_osm
                    lat, lon = get_coordinates_from_osm(name, district)
                    HospitalLocation.objects.filter(id=loc_id).update(
                        latitude=lat, longitude=lon
                    )
                    print(f"✅ Geocoded later: {lat}, {lon}")
                except Exception as e:
                    print(f"⚠️ Background OSM failed: {e}")
            
            threading.Thread(
                target=geocode_later,
                args=(hospital_location.id, hospital_name, district),
                daemon=True
            ).start()
        else:
            print(f"✅ Hospital location found ID: {hospital_location.id}")
 
        # ========================================
        # STEP 4: Validate Data with Serializer
        # ========================================
        print("\n📍 STEP 4: Running serializer...")
        serializer = BloodRequestSerializer(data=request.data)
 
        print("   Validating serializer...")
        if not serializer.is_valid():
            print(f"❌ Serializer errors: {serializer.errors}")
            return Response(serializer.errors, status=400)
        
        print("✅ Serializer validation passed")
 
        # ========================================
        # STEP 5: Save Blood Request
        # ========================================
        print("\n📍 STEP 5: Saving blood request to database...")
        blood_request = serializer.save(
            patient=patient,
            hospital_location=hospital_location,
        )
        print(f"✅ Blood request saved! ID: {blood_request.id}")
        print(f"   Blood Type: {blood_request.blood_type}")
        print(f"   Units: {blood_request.units_required}")
        print(f"   Status: {blood_request.status}")
 
        # ========================================
        # STEP 6: Create Notification
        # ========================================
        print("\n📍 STEP 6: Creating notification...")
        try:
            notification = Notification.objects.create(
                title="New Blood Request",
                message=f"{patient.fullname} requested {blood_request.blood_type} blood at {hospital_name}",
                type="blood_request",
                blood_request=blood_request,
                user=request.user,
                hospital=None,
            )
            print(f"✅ Notification created ID: {notification.id}")
        except Exception as e:
            print(f"⚠️ Notification failed (non-fatal): {e}")
 
        # ========================================
        # STEP 7: Return JSON Response (NOT redirect!)
        # ========================================
        print("\n📍 STEP 7: Preparing response...")
        response_data = {
            "success": True,
            "message": "Blood request submitted successfully",
            "id": blood_request.id,
            "status": "pending_review",
            "blood_type": blood_request.blood_type,
            "hospital": hospital_name
        }
        print(f"✅ Response data: {response_data}")
        print(f"\n🟢 About to return HTTP 201 (Created)")
        print("="*60)
        
        # ✅ THIS IS THE CORRECT RETURN - NO REDIRECT!
        return Response(response_data, status=status.HTTP_201_CREATED)
 
    except Exception as e:
        print(f"\n❌ EXCEPTION CAUGHT: {str(e)}")
        import traceback
        traceback.print_exc()
        print("="*60)
        return Response(
            {"message": str(e)},
            status=500
        )
    
    # This line should NEVER be reached
    print("🔴 CODE REACHED END - THIS SHOULD NOT HAPPEN!")
# =========================================================
# API – PATIENT CONFIRM RECEIPT
# =========================================================
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_patient_confirm_receipt(request, request_id):
    patient = Patient.objects.filter(emailaddress=request.user.username).first()
    if not patient:
        return Response({"message": "Patient not found"}, status=403)
 
    blood_request = get_object_or_404(
        BloodRequest, id=request_id, patient=patient, status="approved"
    )
 
    if blood_request.patient_confirmed:
        return Response({"message": "Already confirmed"}, status=400)
 
    if not blood_request.accepted_donor:
        return Response(
            {"success": False, "message": "No donor has accepted this request yet."},
            status=400,
        )
 
    # ── Generate OTP ───────────────────────────────────────────────
    import random
    from datetime import timedelta
    otp = str(random.randint(1000, 9999))
 
    blood_request.patient_confirmed = True
    blood_request.otp = otp
    blood_request.otp_expires_at = timezone.now() + timedelta(hours=24)
    blood_request.save()
 
    from donor.models import DonationConfirmation
    DonationConfirmation.objects.update_or_create(
        request=blood_request,
        defaults={
            "donor": blood_request.accepted_donor,
            "patient_confirmed": True,
            "donor_confirmed": False,
        },
    )
 
    # ── Email OTP to the accepted donor ────────────────────────────
    donor = blood_request.accepted_donor
    if donor and donor.email:
        try:
            from django.core.mail import send_mail
            from django.conf import settings
            send_mail(
                subject="RedDrop: Your Donation OTP — Please Verify",
                message=(
                    f"Hi {donor.first_name or 'Donor'},\n\n"
                    f"The patient has confirmed receipt of blood for request "
                    f"#{blood_request.id} ({blood_request.blood_type}).\n\n"
                    f"Your verification OTP is:\n\n"
                    f"    {otp}\n\n"
                    f"Please open your RedDrop donor dashboard, go to\n"
                    f"History → Donation History → Pending Confirmation\n"
                    f"and enter this OTP to complete the donation record.\n\n"
                    f"This OTP expires in 24 hours.\n\n"
                    f"Thank you for saving a life! ❤️\n"
                    f"— RedDrop Team"
                ),
                from_email=settings.EMAIL_HOST_USER,
                recipient_list=[donor.email],
                fail_silently=True,
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"OTP email failed for donor {donor.email}: {e}")
 
    # ── In-app notification to donor (optional but helpful) ────────
    try:
        from django.contrib.auth.models import User
        from adminpanel.models import Notification
        donor_user = User.objects.filter(
            email__iexact=donor.email
        ).first() if donor else None
        if donor_user:
            Notification.objects.create(
                user=donor_user,
                blood_request=blood_request,
                title="Donation OTP Ready",
                message=(
                    f"The patient confirmed receipt. Your OTP is {otp}. "
                    "Enter it in your donor dashboard to complete verification."
                ),
                type="donation_otp",
            )
    except Exception:
        pass
 
    return Response({"success": True, "confirmation_code": otp})


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

    compatible_donor_bloods = get_compatible_donors(required_blood)

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
        .filter(status="approved", fulfilled=False)
        .select_related("patient")
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
        blood_request = n.blood_request

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
            "is_accepted": blood_request.fulfilled if blood_request else False,
        })

    return Response(data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_patient_notification_mark_read(request, notification_id):
    Notification.objects.filter(id=notification_id, user=request.user).update(is_read=True)
    return Response({"success": True})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_patient_notifications_mark_all_read(request):
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return Response({"success": True})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_patient_confirm_bank_fulfillment(request, request_id):
    """
    Completion path when the blood bank / hospital stock route was used.
    Only allowed when stock has been found in escalation tracking.
    """
    patient = Patient.objects.filter(emailaddress=request.user.username).first()
    if not patient:
        return Response({"success": False, "message": "Patient not found"}, status=403)

    blood_request = get_object_or_404(
        BloodRequest,
        id=request_id,
        patient=patient,
        status="approved",
    )

    from adminpanel.models import BloodRequestEscalation

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

    # Admin/system log entry
    try:
        Notification.objects.create(
            title="Request Completed (Blood Bank)",
            message=f"Request #{blood_request.id} completed via blood bank / hospital stock.",
            type="request_completed",
            blood_request=blood_request,
        )
    except Exception:
        pass

    return Response({"success": True, "message": "Request marked as completed."})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_request_status(request, request_id):
    blood_request = get_object_or_404(BloodRequest, id=request_id)
    
    donor_data = None
    if blood_request.accepted_donor:
        d = blood_request.accepted_donor
        distance = None
        if (d.latitude and d.longitude and
            blood_request.hospital_location and
            blood_request.hospital_location.latitude):
            distance = haversine(
                blood_request.hospital_location.latitude,
                blood_request.hospital_location.longitude,
                d.latitude,
                d.longitude
            )
        donor_data = {
            "name": f"{d.first_name} {d.last_name}".strip(),
            "blood_type": d.blood_type,
            "phone": d.phone_number,
            "distance_km": round(distance, 2) if distance else None,
        }

    return Response({
        "request_id": blood_request.id,
        "status": blood_request.status,
        "fulfilled": blood_request.fulfilled,
        "blood_type": blood_request.blood_type,
        "hospital": blood_request.hospital_location.name if blood_request.hospital_location else None,
        "accepted_donor": donor_data,   # ✅ added
    })
