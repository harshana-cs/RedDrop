from datetime import timedelta
from urllib import request
from django.conf import settings
from django.core.mail import send_mail
from django.db.models import Count
from django.utils import timezone
from django.utils.timezone import datetime, now
from .models import DonationCamp
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from blood_requests.models import BloodRequest
from hospital.models import Hospital, HospitalProfile, HospitalApplication
from register_donor.models import Donor
from loginsignup.models import Patient
from register_donor.models import Donor
from rest_framework.decorators import api_view
from rest_framework.response import Response
from blood_stock.models import BloodStock, BloodStockHistory
from django.db import transaction
from django.contrib.auth.models import User
from math import radians, sin, cos, sqrt, atan2
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from django.utils import timezone
from dateutil.relativedelta import relativedelta
from .models import HospitalAuditLog, Notification
import random
import requests
# Add this with your other imports at the top
from blood_requests.views import is_donor_eligible
# Add this near the top of adminpanel/views.py
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

# ================= HELPER =================
def fetch_hospital_coordinates(hospital_name):
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": f"{hospital_name} Nepal",
        "format": "json",
        "limit": 1
    }
    headers = {"User-Agent": "reddrop-system"}
    response = requests.get(url, params=params, headers=headers)
    data = response.json()
    if data:
        lat = float(data[0]["lat"])
        lon = float(data[0]["lon"])
        return lat, lon
    return None, None


def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c


def send_sms(phone_number, message):
    """Send SMS via Sparrow SMS Nepal"""
    try:
        response = requests.post(
    "http://api.sparrowsms.com/v2/sms/",
    data={
        "token": settings.SMS_TOKEN.strip(),
        "from": settings.SMS_FROM.strip(),
        "to": str(phone_number).strip(),
        "text": message,
    },
    timeout=5
)
        result = response.json()
        print(f"SMS to {phone_number}: {result}")
        return result.get("response_code") == 200
    except Exception as e:
        print(f"SMS failed for {phone_number}: {e}")
        return False


def send_donor_alert(donor, blood_request, distance):

    # ✅ SMS — keep under 160 chars
    sms_message = (
    f"Blood needed near you. Please login and accept if you want to donate. "
    f"- RedDrop"
)

    if donor.phone_number:
        send_sms(donor.phone_number, sms_message)

    # ✅ Email — shorter than before
    subject = f"RedDrop: {blood_request.blood_type} blood needed near you"

    message = f"""Hi {donor.first_name},

{blood_request.blood_type} blood is urgently needed near you.

Hospital : {blood_request.hospital_location.name}
District : {blood_request.district}
Distance : {round(distance, 1)} km
Contact  : {blood_request.contact_phone}

Login to donate:
http://localhost:5500/donor_dashboard.html

Thank you for saving lives.
— RedDrop Team"""

    send_mail(
        subject,
        message,
        settings.EMAIL_HOST_USER,
        [donor.email],
        fail_silently=True
    )


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
    blood_requests = (
        BloodRequest.objects
        .filter(status="pending")
        .select_related("patient")
    )
    data = []
    for r in blood_requests:
        patient = r.patient
        data.append({
            "id": r.id,
            "patient_name": f"{patient.fullname}" if patient else "By Hospital",
            "blood_type": r.blood_type,
            "hospital": r.hospital_location.name if r.hospital_location else None,
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

    if blood_request.status.lower() != "pending":
        return Response(
            {"success": False, "message": "Request already processed"},
            status=400
        )

    blood_request.status = "approved"
    blood_request.patient_confirmed = False
    blood_request.fulfilled = False
    blood_request.save()

    hospital = blood_request.hospital_location

    # ✅ FIX 1: If hospital has no coordinates, try to fetch them now
    if hospital and (not hospital.latitude or not hospital.longitude):
        lat, lon = fetch_hospital_coordinates(hospital.name)
        if lat and lon:
            hospital.latitude = lat
            hospital.longitude = lon
            hospital.save()
            print(f"✅ Fetched coordinates for {hospital.name}: {lat}, {lon}")
        else:
            print(f"❌ Could not fetch coordinates for hospital: {hospital.name}")

    if hospital and hospital.latitude and hospital.longitude:
        compatible_groups = [
            donor_blood
            for donor_blood, receivers in BLOOD_COMPATIBILITY.items()
            if blood_request.blood_type in receivers
        ]

        # ✅ FIX 2: Removed latitude/longitude filter to catch ALL approved donors
        # We'll check distance manually and skip donors with no coords
        donors = Donor.objects.filter(
            is_approved=True,
            blood_type__in=compatible_groups,
        )

        # ✅ FIX 3: Safe patient exclusion (patient could be None)
        if blood_request.patient:
            donors = donors.exclude(email=blood_request.patient.emailaddress)

        print(f"=== APPROVAL DEBUG for Request #{blood_request.id} ===")
        print(f"Hospital: {hospital.name} | lat: {hospital.latitude} | lon: {hospital.longitude}")
        print(f"Compatible blood groups: {compatible_groups}")
        print(f"Total approved compatible donors: {donors.count()}")

        alerted_count = 0

        for donor in donors:

            # ✅ FIX 4: Skip donors with no coordinates but log it
            if not donor.latitude or not donor.longitude:
                print(f"  ⚠️ Donor {donor.email} has no coordinates — skipping")
                continue

            # ✅ skip donors in cooldown period
            if not is_donor_eligible(donor):
                print(f"  ⏳ Donor {donor.email} is in cooldown — skipping")
                continue

            distance = haversine(
                hospital.latitude,
                hospital.longitude,
                donor.latitude,
                donor.longitude
            )

            print(f"  Donor: {donor.email} | blood: {donor.blood_type} | distance: {round(distance, 2)} km")

            if distance <= 15:
                print(f"  ✅ Sending alert to {donor.email}")

                # ✅ FIX 5: Wrap send_donor_alert in try/except so one failure
                # doesn't stop other donors from being notified
                try:
                    send_donor_alert(donor, blood_request, distance)
                    alerted_count += 1
                except Exception as e:
                    print(f"  ❌ Alert failed for {donor.email}: {e}")

                donor_user = User.objects.filter(email__iexact=donor.email).first()
                if donor_user:
                    already_notified = Notification.objects.filter(
                        user=donor_user,
                        blood_request=blood_request,
                        type="blood_request"
                    ).exists()

                    if not already_notified:
                        Notification.objects.create(
                            user=donor_user,
                            blood_request=blood_request,
                            title="Blood Donation Needed",
                            message=(
                                f"{blood_request.blood_type} blood needed at "
                                f"{hospital.name} ({round(distance, 1)} km away). "
                                f"Can you donate?"
                            ),
                            type="blood_request"
                        )
                else:
                    print(f"  ⚠️ No Django User found for donor email: {donor.email}")

        print(f"=== Total donors alerted: {alerted_count} ===")

    else:
        print(f"❌ Hospital missing or has no coordinates — NO donors alerted!")

    # ✅ Admin-only log
    Notification.objects.create(
        title="Blood Request Approved",
        message=(
            f"Request #{blood_request.id} for {blood_request.blood_type} at "
            f"{hospital.name if hospital else 'Unknown'} approved"
        ),
        type="blood_request"
    )

    return Response({
        "success": True,
        "message": "Blood request approved successfully"
    })
# ================= REJECT BLOOD REQUEST =================
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

    if hasattr(blood_request, "rejection_reason"):
        blood_request.rejection_reason = reason

    blood_request.save()

    Notification.objects.create(
        title="Request Rejected",
        message=f"Request #{blood_request.id} was rejected",
        type="alert"
    )

    return Response({
        "success": True,
        "message": "Blood request rejected successfully"
    })


# ================= REJECT DONOR =================
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
    donor.is_profile_completed = False

    if hasattr(donor, "rejection_reason"):
        donor.rejection_reason = reason

    donor.save()

    return Response({
        "success": True,
        "message": "Donor rejected successfully"
    })


# ================= APPROVE DONOR =================
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

    if donor.is_approved:
        return Response({
            "success": True,
            "message": "Donor already approved"
        })

    donor.is_approved = True
    donor.save()

    if donor.email:
        send_mail(
            subject="🎉 You are now an approved blood donor!",
            message=(
                f"Hello {donor.first_name},\n\n"
                "Great news! Your donor registration on RedDrop has been approved.\n\n"
                "You can now receive blood donation requests and help save lives.\n\n"
                "Thank you for being a hero ❤️\n"
                "— RedDrop Team"
            ),
            from_email="noreply@reddrop.com",
            recipient_list=[donor.email],
            fail_silently=True
        )

    return Response({
        "success": True,
        "message": "Donor approved successfully and email sent"
    })


# ================= LIST HOSPITALS =================
@api_view(["GET"])
@permission_classes([AllowAny])
def admin_list_hospitals(request):
    hospitals = Hospital.objects.all()
    data = []
    for h in hospitals:
        profile = getattr(h, "profile", None)
        data.append({
            "id": h.id,
            "name": h.name,
            "username": h.username,
            "active": h.is_active,
            "created_at": h.created_at.strftime("%Y-%m-%d"),
            "district": profile.district if profile else None,
            "contact_number": profile.contact_number if profile else None,
            "registration_number": profile.registration_number if profile else None,
            "email": profile.email if profile else None,
        })
    return Response({
        "success": True,
        "data": data
    })


# ================= RESET HOSPITAL PASSWORD =================
@api_view(["POST"])
@permission_classes([AllowAny])
def admin_reset_hospital_password(request, hospital_id):
    password = request.data.get("password")
    if not password:
        return Response(
            {"success": False, "message": "Password required"},
            status=400
        )
    try:
        hospital = Hospital.objects.get(id=hospital_id)
    except Hospital.DoesNotExist:
        return Response(
            {"success": False, "message": "Hospital not found"},
            status=404
        )
    hospital.set_password(password)
    hospital.save()
    return Response({
        "success": True,
        "message": "Password reset successfully"
    })


# ================= TOGGLE HOSPITAL =================
@api_view(["POST"])
@permission_classes([AllowAny])
def admin_toggle_hospital(request, hospital_id):
    try:
        hospital = Hospital.objects.get(id=hospital_id)
    except Hospital.DoesNotExist:
        return Response(
            {"success": False, "message": "Hospital not found"},
            status=404
        )
    hospital.is_active = not hospital.is_active
    hospital.save()
    return Response({
        "success": True,
        "active": hospital.is_active
    })


# ================= CREATE HOSPITAL (MANUAL) =================
@api_view(["POST"])
@permission_classes([AllowAny])
def admin_create_hospital(request):
    name = request.data.get("name")
    username = request.data.get("username")
    password = request.data.get("password")
    district = request.data.get("district")
    contact_number = request.data.get("contact_number")
    registration_number = request.data.get("registration_number")
    email = request.data.get("email")

    if not all([name, username, password, district, contact_number, registration_number]):
        return Response(
            {"success": False, "message": "All required fields must be provided"},
            status=400
        )

    if Hospital.objects.filter(username=username).exists():
        return Response(
            {"success": False, "message": "Username already exists"},
            status=400
        )

    hospital = Hospital(name=name, username=username)
    hospital.set_password(password)
    hospital.save()

    HospitalProfile.objects.create(
        hospital=hospital,
        district=district,
        contact_number=contact_number,
        registration_number=registration_number,
        email=email
    )

    return Response({
        "success": True,
        "message": "Hospital created successfully"
    })


# ================= PROCESSED BLOOD REQUESTS =================
@api_view(["GET"])
@permission_classes([AllowAny])
def admin_processed_blood_requests(request):
    blood_requests = (
        BloodRequest.objects
        .filter(status__in=["approved", "rejected"])
        .select_related("patient")
        .order_by("-created_at")
    )
    data = []
    for r in blood_requests:
        patient = r.patient
        data.append({
            "id": r.id,
            "patient_name": patient.fullname if patient else "Unknown",
            "blood_type": r.blood_type,
            "hospital": r.hospital_location.name if r.hospital_location else None,
            "urgency": r.urgency,
            "status": r.status,
            "processed_on": (
                r.donation_date.strftime("%Y-%m-%d %H:%M")
                if r.donation_date
                else r.created_at.strftime("%Y-%m-%d %H:%M")
            )
        })
    return Response({
        "success": True,
        "count": len(data),
        "data": data
    })


# ================= PROCESSED DONOR REGISTRATIONS =================
@api_view(["GET"])
@permission_classes([AllowAny])
def admin_processed_donor_registrations(request):
    donors = Donor.objects.filter(is_approved=True).order_by("-created_on")
    data = []
    for d in donors:
        data.append({
            "id": d.id,
            "name": f"{d.first_name or ''} {d.last_name or ''}".strip(),
            "blood_type": d.blood_type,
            "status": "approved",
            "processed_on": d.created_on.strftime("%Y-%m-%d %H:%M")
        })
    return Response({
        "success": True,
        "count": len(data),
        "data": data
    })


# ================= HOSPITAL REQUESTS =================
@api_view(["GET"])
@permission_classes([AllowAny])
def admin_hospital_requests(request):
    status_param = request.GET.get("status")
    qs = HospitalApplication.objects.all().order_by("-created_at")
    if status_param:
        qs = qs.filter(status=status_param)
    data = []
    for r in qs:
        data.append({
            "id": r.id,
            "hospital_name": r.hospital_name,
            "registration_number": r.registration_number,
            "hospital_type": r.hospital_type,
            "email": r.email,
            "phone": r.phone,
            "status": r.status,
        })
    return Response(data, status=status.HTTP_200_OK)


# ================= APPROVE HOSPITAL REQUEST =================
@api_view(["POST"])
@permission_classes([AllowAny])
def approve_hospital_request(request, pk):
    try:
        app = HospitalApplication.objects.get(id=pk, status="pending")
    except HospitalApplication.DoesNotExist:
        return Response(
            {"success": False, "message": "Hospital request not found"},
            status=status.HTTP_404_NOT_FOUND
        )

    username = request.data.get("username")
    password = request.data.get("password")

    if not username or not password:
        return Response(
            {"success": False, "message": "Username and password are required"},
            status=status.HTTP_400_BAD_REQUEST
        )

    if Hospital.objects.filter(username=username).exists():
        return Response(
            {"success": False, "message": "Username already exists"},
            status=status.HTTP_400_BAD_REQUEST
        )

    hospital = Hospital.objects.create(
        name=app.hospital_name,
        username=username,
        is_active=True
    )
    hospital.set_password(password)
    hospital.save()

    HospitalProfile.objects.create(
        hospital=hospital,
        district=app.address,
        contact_number=app.phone,
        registration_number=app.registration_number,
        email=app.email
    )

    app.status = "approved"
    app.approved_at = timezone.now()
    app.save()

    send_mail(
        subject="🏥 Hospital Registration Approved – RedDrop",
        message=(
            f"Dear {app.hospital_name},\n\n"
            "Your hospital registration request has been approved.\n\n"
            f"Login Credentials:\n"
            f"Username: {username}\n"
            f"Password: {password}\n\n"
            "You can now log in and manage blood requests on RedDrop.\n\n"
            "— RedDrop Team"
        ),
        from_email=settings.EMAIL_HOST_USER,
        recipient_list=[app.email],
        fail_silently=True,
    )

    return Response(
        {"success": True, "message": "Hospital approved successfully"},
        status=status.HTTP_200_OK
    )


# ================= REJECT HOSPITAL REQUEST =================
@api_view(["POST"])
@permission_classes([AllowAny])
def reject_hospital_request(request, pk):
    try:
        application = HospitalApplication.objects.get(id=pk, status="pending")
    except HospitalApplication.DoesNotExist:
        return Response(
            {"error": "Hospital request not found"},
            status=status.HTTP_404_NOT_FOUND
        )

    application.status = "rejected"
    application.rejected_at = timezone.now()
    application.save()

    return Response(
        {"success": True, "message": "Hospital request rejected"},
        status=status.HTTP_200_OK
    )


# ================= HOSPITAL REQUEST DETAIL =================
@api_view(["GET"])
@permission_classes([AllowAny])
def hospital_request_detail(request, pk):
    h = HospitalApplication.objects.get(id=pk)
    return Response({
        "hospital_name": h.hospital_name,
        "hospital_type": h.hospital_type,
        "email": h.email,
        "phone": h.phone,
        "address": h.address,
        "bed_capacity": h.bed_capacity,
        "registration_certificate": h.registration_certificate.url,
        "medical_license": h.medical_license.url,
        "id_proof": h.id_proof.url,
    })


# ================= ANALYTICS: BLOOD TYPE DISTRIBUTION =================
def get_date_range(request):
    """Helper to parse date range from request query params."""
    days = request.GET.get("days")
    from_date = request.GET.get("from")
    to_date = request.GET.get("to")
 
    now = timezone.now()
 
    if from_date and to_date:
        try:
            start = datetime.strptime(from_date, "%Y-%m-%d")
            end   = datetime.strptime(to_date,   "%Y-%m-%d")
            start = timezone.make_aware(start)
            end   = timezone.make_aware(end.replace(hour=23, minute=59, second=59))
            return start, end
        except ValueError:
            pass
 
    days = int(days) if days and days.isdigit() else 7
    start = now - timedelta(days=days)
    return start, now
@api_view(["GET"])
@permission_classes([AllowAny])
def api_blood_type_distribution(request):
    start, end = get_date_range(request)
    data = (
        BloodRequest.objects
        .filter(created_at__gte=start, created_at__lte=end)
        .values("blood_type")
        .annotate(count=Count("id"))
        .order_by("blood_type")
    )
    return Response({
        "labels": [d["blood_type"] for d in data],
        "values": [d["count"]      for d in data]
    })


# ================= ANALYTICS: REQUEST STATUS OVERVIEW =================
@api_view(["GET"])
@permission_classes([AllowAny])
def api_request_status_overview(request):
    start, end = get_date_range(request)
 
    # Determine granularity: daily for ≤30 days, weekly for ≤90, monthly otherwise
    delta = (end - start).days
 
    if delta <= 30:
        # Daily buckets
        labels, pending, approved, rejected = [], [], [], []
        cursor = start.date()
        end_d  = end.date()
        while cursor <= end_d:
            next_d = cursor + timedelta(days=1)
            labels.append(cursor.strftime("%d %b"))
            qs = BloodRequest.objects.filter(
                created_at__date=cursor
            )
            pending.append( qs.filter(status="pending").count())
            approved.append(qs.filter(status="approved").count())
            rejected.append(qs.filter(status="rejected").count())
            cursor = next_d
 
    elif delta <= 90:
        # Weekly buckets
        labels, pending, approved, rejected = [], [], [], []
        cursor = start
        while cursor < end:
            week_end = min(cursor + timedelta(days=7), end)
            labels.append(cursor.strftime("%d %b"))
            qs = BloodRequest.objects.filter(
                created_at__gte=cursor, created_at__lt=week_end
            )
            pending.append( qs.filter(status="pending").count())
            approved.append(qs.filter(status="approved").count())
            rejected.append(qs.filter(status="rejected").count())
            cursor = week_end
 
    else:
        # Monthly buckets (original logic)
        labels, pending, approved, rejected = [], [], [], []
        now_dt = timezone.now()
        months = max(1, delta // 30)
        for i in range(months - 1, -1, -1):
            month_start = (now_dt.replace(day=1) - relativedelta(months=i))
            month_end   = month_start + relativedelta(months=1)
            if month_start < start: month_start = start
            if month_end   > end:   month_end   = end
            labels.append(month_start.strftime("%b %Y"))
            qs = BloodRequest.objects.filter(
                created_at__gte=month_start, created_at__lt=month_end
            )
            pending.append( qs.filter(status="pending").count())
            approved.append(qs.filter(status="approved").count())
            rejected.append(qs.filter(status="rejected").count())
 
    return Response({
        "labels":   labels,
        "pending":  pending,
        "approved": approved,
        "rejected": rejected
    })


# ================= NOTIFICATIONS =================
def get_notifications(request):
    notifications = Notification.objects.filter(
        hospital__isnull=True
    ).order_by("-created_at")[:10]

    data = [
        {
            "id": n.id,
            "title": n.title,
            "message": n.message,
            "type": n.type,
            "created_at": n.created_at.strftime("%Y-%m-%d %H:%M"),
            "is_read": n.is_read
        }
        for n in notifications
    ]

    unread = Notification.objects.filter(
        hospital__isnull=True,
        is_read=False
    ).count()

    return JsonResponse({
        "notifications": data,
        "unread": unread
    })


@csrf_exempt
def mark_notification_read(request, notification_id):
    if request.method == "POST":
        notification = get_object_or_404(Notification, id=notification_id)
        notification.is_read = True
        notification.save()
        return JsonResponse({"success": True})
    return JsonResponse({"error": "Invalid request"}, status=400)


# ================= MARK ALL NOTIFICATIONS READ =================
@api_view(["POST"])
@permission_classes([AllowAny])
def mark_all_notifications_read(request):
    Notification.objects.filter(
        hospital__isnull=True,
        is_read=False
    ).update(is_read=True)
    return Response({"success": True})


# ================= HOSPITAL AUDIT LOGS =================
@api_view(["GET"])
@permission_classes([AllowAny])
def admin_hospital_audit_logs(request):
    logs = HospitalAuditLog.objects.select_related("hospital").order_by("-created_at")[:200]
    data = []
    for log in logs:
        data.append({
            "hospital": log.hospital.name if log.hospital else "Application",
            "action": log.action,
            "description": log.description,
            "metadata": log.metadata,
            "ip_address": log.ip_address if hasattr(log, "ip_address") else None,
            "time": log.created_at
        })
    return Response({
        "logs": data,
        "active_hospitals": Hospital.objects.filter(is_active=True).count()
    })


# ================= USERS =================
@api_view(["GET"])
@permission_classes([AllowAny])
def admin_users(request):
    users = Patient.objects.all()
    data = []
    for u in users:
        donor = Donor.objects.filter(email=u.emailaddress).first()
        requests_count = BloodRequest.objects.filter(patient=u).count()
        donations_count = BloodRequest.objects.filter(
            patient=u, status="completed"
        ).count()
        data.append({
            "id": u.id,
            "name": u.fullname,
            "email": u.emailaddress,
            "blood_type": donor.blood_type if donor else None,
            "total_requests": requests_count,
            "total_donations": donations_count,
            "availability": "Available" if donor else "Not Donor"
        })
    return Response(data)


# ================= USER DETAIL =================
@api_view(["GET"])
@permission_classes([AllowAny])
def admin_user_detail(request, user_id):
    try:
        user = Patient.objects.get(id=user_id)
    except Patient.DoesNotExist:
        return Response(
            {"success": False, "message": "User not found"},
            status=404
        )

    donor = Donor.objects.filter(email=user.emailaddress).first()
    blood_requests = BloodRequest.objects.filter(patient=user)

    request_list = []
    donation_history = []

    for r in blood_requests:
        request_list.append({
            "id": r.id,
            "blood_type": r.blood_type,
            "units": r.units_required,
            "hospital": r.hospital_location.name if r.hospital_location else None,
            "status": r.status,
            "date": r.created_at.strftime("%Y-%m-%d")
        })
        if r.status == "completed":
            donation_history.append({
                "blood_type": r.blood_type,
                "hospital": r.hospital_location.name if r.hospital_location else None,
                "date": r.donation_date.strftime("%Y-%m-%d") if r.donation_date else None
            })

    last_donation = None
    completed = blood_requests.filter(status="completed").order_by("-donation_date").first()
    if completed and completed.donation_date:
        last_donation = completed.donation_date

    eligibility = "Eligible"
    if last_donation:
        days_since = (timezone.now() - last_donation).days
        if days_since < 90:
            eligibility = f"Not Eligible ({90 - days_since} days remaining)"

    return Response({
        "id": user.id,
        "name": user.fullname,
        "email": user.emailaddress,
        "created_on": user.created_on.strftime("%Y-%m-%d"),
        "donor": {
            "blood_type": donor.blood_type if donor else None,
            "phone": donor.phone_number if donor else None,
            "city": donor.city if donor else None,
            "approved": donor.is_approved if donor else False
        },
        "last_donation_date": last_donation.strftime("%Y-%m-%d") if last_donation else None,
        "eligibility_status": eligibility,
        "requests": request_list,
        "donation_history": donation_history
    })


# ================= BLOOD INVENTORY =================
@api_view(["GET"])
@permission_classes([AllowAny])
def admin_blood_inventory(request):
    stocks = BloodStock.objects.filter(hospital__isnull=True)
    data = []
    for s in stocks:
        data.append({
            "blood_type": s.blood_type,
            "units": s.units,
            "minimum_required": s.minimum_required,
            "last_updated": s.last_updated
        })
    return Response(data)


@api_view(["GET"])
def admin_hospital_stock(request):
    stocks = BloodStock.objects.filter(
        hospital__isnull=False
    ).select_related("hospital")
    data = []
    for s in stocks:
        data.append({
            "hospital": s.hospital.name,
            "blood_type": s.blood_type,
            "units": s.units,
            "minimum_required": s.minimum_required,
            "last_updated": s.last_updated
        })
    return Response(data)


@api_view(["POST"])
@permission_classes([AllowAny])
def admin_add_inventory(request):
    blood_type = request.data.get("blood_type")
    units = int(request.data.get("units"))
    expiry_date = request.data.get("expiry_date")

    stock, created = BloodStock.objects.get_or_create(
        hospital=None,
        blood_type=blood_type
    )
    stock.units += units
    stock.save()

    BloodStockHistory.objects.create(
        hospital=None,
        blood_type=blood_type,
        transaction_type="add",
        units=units,
        performed_by="Admin",
        expiry_date=expiry_date,
        new_balance=stock.units
    )
    return Response({"success": True})


@api_view(["POST"])
@permission_classes([AllowAny])
def admin_remove_inventory(request):
    blood_type = request.data.get("blood_type")
    units = int(request.data.get("units", 0))

    try:
        stock = BloodStock.objects.get(hospital=None, blood_type=blood_type)
    except BloodStock.DoesNotExist:
        return Response({"message": "Stock not found"}, status=404)

    if units > stock.units:
        return Response({"message": "Insufficient stock"}, status=400)

    with transaction.atomic():
        stock.units -= units
        stock.save()
        BloodStockHistory.objects.create(
            hospital=None,
            blood_type=blood_type,
            transaction_type="remove",
            units=units,
            reason="Admin removal",
            performed_by="Admin",
            new_balance=stock.units
        )
    return Response({"success": True})


@api_view(["POST"])
@permission_classes([AllowAny])
def admin_bulk_add_inventory(request):
    stock_data = request.data.get("stock", {})
    notes = request.data.get("notes")

    for blood_type, units in stock_data.items():
        units = int(units)
        if units <= 0:
            continue
        stock, _ = BloodStock.objects.get_or_create(
            hospital=None,
            blood_type=blood_type,
            defaults={"units": 0}
        )
        stock.units += units
        stock.save()
        BloodStockHistory.objects.create(
            hospital=None,
            blood_type=blood_type,
            transaction_type="add",
            units=units,
            source=notes,
            performed_by="Admin",
            new_balance=stock.units
        )
    return Response({"success": True})


@api_view(["GET"])
@permission_classes([AllowAny])
def admin_stock_movements(request):
    limit = int(request.GET.get("limit", 10))
    history = BloodStockHistory.objects.filter(
        hospital__isnull=True
    ).order_by("-timestamp")[:limit]
    data = []
    for h in history:
        data.append({
            "date": h.timestamp,
            "blood_type": h.blood_type,
            "type": h.transaction_type,
            "units": h.units,
            "updated_by": h.performed_by,
            "notes": h.source or h.reason
        })
    return Response(data)


# ================= AUDIT / ACTIVITY LOGS =================
@api_view(["GET"])
@permission_classes([AllowAny])
def admin_activity_logs(request):
    role = request.GET.get("role")
    log_type = request.GET.get("type")
    date = request.GET.get("date")

    logs = Notification.objects.all().order_by("-created_at")

    if log_type and log_type != "all":
        logs = logs.filter(type=log_type)

    if date:
        logs = logs.filter(created_at__date=date)

    data = []
    for n in logs:
        role_type = "system"
        if n.user:
            donor = Donor.objects.filter(email=n.user.email).first()
            role_type = "donor" if donor else "patient"
        elif hasattr(n, "hospital") and n.hospital:
            role_type = "hospital"

        if role and role != "all":
            if role_type != role:
                continue

        data.append({
            "role": role_type,
            "type": n.type,
            "action": n.title,
            "message": n.message,
            "time": n.created_at
        })

    return Response(data)


# ================= DONATION CAMPS: SERIALIZE HELPER =================
def _serialize_camp(camp):
    today = timezone.localdate()
    return {
        "id": camp.id,
        "title": camp.title,
        "description": camp.description,
        "hospital_name": camp.hospital_name,
        "date": str(camp.date),
        "start_time": str(camp.start_time),
        "end_time": str(camp.end_time),
        "location": camp.location,
        "is_urgent": camp.is_urgent,
        "is_past": camp.date < today,

        # 🔥 ADD THESE TWO (THIS FIXES YOUR PROBLEM)
        "is_approved": camp.is_approved,
        "created_by": camp.created_by,
        "contact_number": camp.contact_number or "",   
        "map_link": camp.map_link or "", 
    }


# ================= DONATION CAMPS: LIST + CREATE =================
# ================= DONATION CAMPS: LIST + CREATE =================
@api_view(["GET", "POST"])
@permission_classes([AllowAny])
def admin_donation_camps(request):

    # ── LIST ──────────────────────────────────────────────────
    if request.method == "GET":
        camps = DonationCamp.objects.all().order_by("-date", "-id")
        return Response([_serialize_camp(c) for c in camps])

    # ── CREATE ────────────────────────────────────────────────
    title      = request.data.get("title", "").strip()
    hospital   = request.data.get("hospital_name", "").strip()
    date_val   = request.data.get("date")
    start_time = request.data.get("start_time")
    end_time   = request.data.get("end_time")
    location   = request.data.get("location", "").strip()

    # ✅ NEW FIELDS
    contact_number = request.data.get("contact_number", "").strip()
    map_link       = request.data.get("map_link", "").strip()

    missing = []
    if not title:      missing.append("title")
    if not hospital:   missing.append("hospital_name")
    if not date_val:   missing.append("date")
    if not start_time: missing.append("start_time")
    if not end_time:   missing.append("end_time")
    if not location:   missing.append("location")

    if missing:
        return Response(
            {"success": False, "message": f"Required fields missing: {', '.join(missing)}"},
            status=status.HTTP_400_BAD_REQUEST
        )

    camp = DonationCamp.objects.create(
        title=title,
        description=request.data.get("description", ""),
        hospital_name=hospital,
        date=date_val,
        start_time=start_time,
        end_time=end_time,
        location=location,
        contact_number=contact_number,   # ✅ NEW
        map_link=map_link,               # ✅ NEW
        is_urgent=bool(request.data.get("is_urgent", False)),
        is_approved=False,
        created_by="admin"
    )

    camp.refresh_from_db()

    try:
        Notification.objects.create(
            title="New Donation Camp Created",
            message=f'"{camp.title}" on {camp.date} at {camp.location}',
            type="alert",
        )
    except:
        pass

    return Response(_serialize_camp(camp), status=status.HTTP_201_CREATED)
# ================= DONATION CAMPS: DETAIL + UPDATE + DELETE =================
@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([AllowAny])
def admin_donation_camp_detail(request, camp_id):

    try:
        camp = DonationCamp.objects.get(id=camp_id)
    except DonationCamp.DoesNotExist:
        return Response({"success": False, "message": "Camp not found"}, status=404)

    if request.method == "GET":
        return Response(_serialize_camp(camp))

    if request.method == "DELETE":
        camp.delete()
        return Response({"success": True, "message": "Deleted"}, status=204)

    data = request.data

    # ── PUT (FULL UPDATE) ─────────────────
    if request.method == "PUT":
        camp.title         = data.get("title", "").strip()
        camp.description   = data.get("description", "")
        camp.hospital_name = data.get("hospital_name", "").strip()
        camp.date          = data.get("date")
        camp.start_time    = data.get("start_time")
        camp.end_time      = data.get("end_time")
        camp.location      = data.get("location", "").strip()

        # ✅ NEW
        camp.contact_number = data.get("contact_number", "")
        camp.map_link       = data.get("map_link", "")

        camp.is_urgent     = bool(data.get("is_urgent", False))

        camp.save()
        camp.refresh_from_db()

    # ── PATCH (PARTIAL UPDATE) ────────────
    elif request.method == "PATCH":

        if "title" in data: camp.title = data["title"].strip()
        if "description" in data: camp.description = data["description"]
        if "hospital_name" in data: camp.hospital_name = data["hospital_name"].strip()
        if "date" in data: camp.date = data["date"]
        if "start_time" in data: camp.start_time = data["start_time"]
        if "end_time" in data: camp.end_time = data["end_time"]
        if "location" in data: camp.location = data["location"].strip()

        # ✅ NEW
        if "contact_number" in data:
            camp.contact_number = data["contact_number"]

        if "map_link" in data:
            camp.map_link = data["map_link"]

        if "is_urgent" in data:
            camp.is_urgent = bool(data["is_urgent"])

        camp.save()
        camp.refresh_from_db()

    return Response(_serialize_camp(camp))


# ================= PUBLIC DONATION CAMPS =================
@api_view(["GET"])
@permission_classes([AllowAny])
def public_donation_camps(request):
    today = timezone.localdate()
    camps = DonationCamp.objects.filter(date__gte=today, is_approved=True).order_by("date", "start_time")
    return Response([_serialize_camp(c) for c in camps])


@api_view(["GET"])
@permission_classes([AllowAny])
def admin_all_hospitals_stock(request):
    result = []

    # ── Blood Bank (hospital=None) ──
    bank_stocks = BloodStock.objects.filter(hospital__isnull=True)
    if bank_stocks.exists():
        result.append({
            "hospital": {"id": None, "name": "Blood Bank", "district": "Central"},
            "stock": [
                {"blood_type": s.blood_type, "units": s.units, "last_updated": s.last_updated}
                for s in bank_stocks
            ]
        })

    # ── Active Hospitals ──
    hospitals = Hospital.objects.filter(is_active=True)
    for h in hospitals:
        stocks = BloodStock.objects.filter(hospital=h)
        result.append({
            "hospital": {
                "id": h.id,
                "name": h.name,
                "district": h.profile.district if hasattr(h, "profile") else None
            },
            "stock": [
                {"blood_type": s.blood_type, "units": s.units, "last_updated": s.last_updated}
                for s in stocks
            ]
        })

    return Response(result)

# ================= PARTNER CREATE (FIXED) =================
@api_view(["POST"])
@permission_classes([AllowAny])
def create_camp_by_partner(request):

    camp = DonationCamp.objects.create(
        title=request.data.get("title"),
        description=request.data.get("description"),
        hospital_name=request.data.get("hospital_name"),
        date=request.data.get("date"),
        start_time=request.data.get("start_time"),
        end_time=request.data.get("end_time"),
        location=request.data.get("location"),

        # ✅ ADD THESE
        contact_number=request.data.get("contact_number"),
        map_link=request.data.get("map_link"),

        is_urgent=request.data.get("is_urgent", False),
        is_approved=False,
        created_by="corporate"
    )

    Notification.objects.create(
        title="New Camp Submitted",
        message=f'"{camp.title}" waiting for approval',
        type="camp"
    )

    return Response({"success": True})

@api_view(["PATCH"])
@permission_classes([AllowAny])
def approve_camp(request, camp_id):
    try:
        camp = DonationCamp.objects.get(id=camp_id)
        camp.is_approved = True
        camp.save()

        return Response({"success": True, "message": "Camp approved"})
    except DonationCamp.DoesNotExist:
        return Response({"success": False, "message": "Not found"}, status=404)
    
@api_view(["DELETE"])
@permission_classes([AllowAny])
def reject_camp(request, camp_id):
    try:
        camp = DonationCamp.objects.get(id=camp_id)
        camp.delete()

        return Response({"success": True, "message": "Camp rejected"})
    except DonationCamp.DoesNotExist:
        return Response({"success": False}, status=404)
    

    
