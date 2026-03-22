from datetime import timedelta
from django.conf import settings
from django.core.mail import send_mail
from django.db.models import Count
from django.utils import timezone
from django.utils.timezone import now
# from Backend import hospital
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from blood_requests.models import BloodRequest
from hospital.models import Hospital, HospitalProfile, HospitalApplication
from register_donor.models import Donor
from loginsignup.models import Patient
from loginsignup.models import Patient
from register_donor.models import Donor
from rest_framework.decorators import api_view
from rest_framework.response import Response
from blood_stock.models import BloodStock, BloodStockHistory
from django.db import transaction
from django.contrib.auth.models import User

import requests

def fetch_hospital_coordinates(hospital_name):

    url = "https://nominatim.openstreetmap.org/search"

    params = {
        "q": f"{hospital_name} Nepal",
        "format": "json",
        "limit": 1
    }

    headers = {
        "User-Agent": "reddrop-system"
    }

    response = requests.get(url, params=params, headers=headers)

    data = response.json()

    if data:
        lat = float(data[0]["lat"])
        lon = float(data[0]["lon"])
        return lat, lon

    return None, None

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
                if patient else "By Hospital"
            ),

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

            # Documents
            "citizenship_id": d.citizenship_id.url if d.citizenship_id else None,
            "photo": d.photo.url if d.photo else None,
        })

    return Response({
        "success": True,
        "count": len(data),
        "data": data
    })
def send_donor_alert(donor, blood_request, distance):

    subject = "Urgent Blood Donation Needed Near You"

    message = f"""
Hello {donor.first_name},

A nearby blood request has been approved and you are eligible to help.

Blood Group Needed: {blood_request.blood_type}
Hospital: {blood_request.hospital_location.name}
District: {blood_request.district}
Distance from you: {round(distance,2)} km

To help this patient, please login to your RedDrop donor dashboard
and accept the donation request.

Login here:
http://localhost:5500/donor_dashboard.html"""

    send_mail(
        subject,
        message,
        settings.EMAIL_HOST_USER,
        [donor.email],
        fail_silently=True
    )

from math import radians, sin, cos, sqrt, atan2

def haversine(lat1, lon1, lat2, lon2):
    R = 6371

    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)

    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    return R * c
import random
from django.utils import timezone
from django.contrib.auth.models import User

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

    # ✅ Approve request
    blood_request.status = "approved"
    blood_request.patient_confirmed = False
    blood_request.fulfilled = False
    blood_request.save()

    hospital = blood_request.hospital_location

    # ✅ Check hospital location
    if hospital and hospital.latitude and hospital.longitude:

        donors = Donor.objects.filter(
            is_approved=True,
            blood_type=blood_request.blood_type,
            latitude__isnull=False,
            longitude__isnull=False
        )

        for donor in donors:

            distance = haversine(
                hospital.latitude,
                hospital.longitude,
                donor.latitude,
                donor.longitude
            )

            if distance <= 15:

                # ✅ Send email
                send_donor_alert(donor, blood_request, distance)

                # ✅ FIX: correct user lookup
                user = User.objects.filter(email__iexact=donor.email).first()

                # 🔍 DEBUG (you can remove later)
                print("Donor:", donor.email, "User:", user)

                if user:
                    Notification.objects.create(
                        title="Blood Donation Needed",
                        message=(
                            f"{blood_request.patient.fullname} needs "
                            f"{blood_request.blood_type} blood at "
                            f"{hospital.name}. "
                            "Do you want to donate?"
                        ),
                        type="blood_request",   # ✅ must match model
                        blood_request=blood_request,
                        user=user
                    )
                else:
                    print("❌ No matching User found for donor:", donor.email)

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
    Notification.objects.create(
    title="Request Rejected",
    message=f"Request #{blood_request.id} was rejected",
    type="alert"
)

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

from django.core.mail import send_mail

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

    # Prevent duplicate approval
    if donor.is_approved:
        return Response({
            "success": True,
            "message": "Donor already approved"
        })

    donor.is_approved = True
    donor.save()

    # ✅ SEND APPROVAL EMAIL (USE Donor.email)
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

    # 1️⃣ Create Hospital (login)
    hospital = Hospital(
        name=name,
        username=username
    )
    hospital.set_password(password)
    hospital.save()

    # 2️⃣ Create Hospital Profile
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
    requests = (
        BloodRequest.objects
        .filter(status__in=["approved", "rejected"])
        .select_related("patient")
        .order_by("-created_at")
    )

    data = []

    for r in requests:
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
    donors = Donor.objects.filter(
        is_approved=True
    ).order_by("-created_on")

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
            # "approved_at": r.approved_at,
            # "rejected_at": r.rejected_at,
        })

    return Response(data, status=status.HTTP_200_OK)



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

    # 1️⃣ CREATE HOSPITAL (AUTH / LOGIN TABLE)
    hospital = Hospital.objects.create(
        name=app.hospital_name,
        username=username,
        is_active=True
    )
    hospital.set_password(password)
    hospital.save()

    # 2️⃣ CREATE HOSPITAL PROFILE (DETAIL TABLE)
    HospitalProfile.objects.create(
        hospital=hospital,
        district=app.address,
        contact_number=app.phone,
        registration_number=app.registration_number,
        email=app.email
    )

    # 3️⃣ UPDATE APPLICATION STATUS
    app.status = "approved"
    app.approved_at = timezone.now()
    app.save()

    # 4️⃣ SEND EMAIL
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
        {
            "success": True,
            "message": "Hospital request rejected"
        },
        status=status.HTTP_200_OK
    )
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

@api_view(["GET"])
@permission_classes([AllowAny])
def api_blood_type_distribution(request):
    data = (
        BloodRequest.objects
        .values("blood_type")
        .annotate(count=Count("id"))
    )

    return Response({
        "labels": [d["blood_type"] for d in data],
        "values": [d["count"] for d in data]
    })

from django.utils import timezone
from dateutil.relativedelta import relativedelta

@api_view(["GET"])
@permission_classes([AllowAny])
def api_request_status_overview(request):
    now_dt = timezone.now()

    labels = []
    pending = []
    approved = []
    rejected = []

    for i in range(5, -1, -1):
        month_start = (now_dt.replace(day=1) - relativedelta(months=i))
        month_end = month_start + relativedelta(months=1)

        labels.append(month_start.strftime("%b"))

        pending.append(
            BloodRequest.objects.filter(
                status="pending",
                created_at__gte=month_start,
                created_at__lt=month_end
            ).count()
        )
        approved.append(
            BloodRequest.objects.filter(
                status="approved",
                created_at__gte=month_start,
                created_at__lt=month_end
            ).count()
        )
        rejected.append(
            BloodRequest.objects.filter(
                status="rejected",
                created_at__gte=month_start,
                created_at__lt=month_end
            ).count()
        )

    return Response({
        "labels": labels,
        "pending": pending,
        "approved": approved,
        "rejected": rejected
    })
from django.http import JsonResponse
from .models import Notification

def get_notifications(request):

    # Only admin notifications
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
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404

@csrf_exempt
def mark_notification_read(request, notification_id):

    if request.method == "POST":
        notification = get_object_or_404(Notification, id=notification_id)

        notification.is_read = True
        notification.save()

        return JsonResponse({
            "success": True
        })

    return JsonResponse({"error": "Invalid request"}, status=400)
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import HospitalAuditLog


@api_view(["GET"])
@permission_classes([AllowAny])
def admin_hospital_audit_logs(request):

    logs = HospitalAuditLog.objects.select_related("hospital")\
        .order_by("-created_at")[:200]

    data = []

    for log in logs:
        data.append({
            "hospital": log.hospital.name if log.hospital else "Application",
            "action": log.action,
            "description": log.description,
            "metadata": log.metadata,
            "time": log.created_at
        })

    return Response({"logs": data})


@api_view(["GET"])
@permission_classes([AllowAny])
def admin_users(request):

    users = Patient.objects.all()

    data = []

    for u in users:

        donor = Donor.objects.filter(email=u.emailaddress).first()

        requests_count = BloodRequest.objects.filter(patient=u).count()

        donations_count = BloodRequest.objects.filter(
            patient=u,
            status="completed"
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

    requests = BloodRequest.objects.filter(patient=user)

    request_list = []
    donation_history = []

    for r in requests:

        request_list.append({
            "id": r.id,
            "blood_type": r.blood_type,
            "units": r.units_required,
            "hospital": r.hospital_location.name if r.hospital_location else None,
            "status": r.status,
            "date": r.created_at.strftime("%Y-%m-%d")
        })

        # Completed donation
        if r.status == "completed":
            donation_history.append({
                "blood_type": r.blood_type,
                "hospital": r.hospital_location.name if r.hospital_location else None,
                "date": r.donation_date.strftime("%Y-%m-%d") if r.donation_date else None
            })

    # Last donation date
    last_donation = None
    completed = requests.filter(status="completed").order_by("-donation_date").first()

    if completed and completed.donation_date:
        last_donation = completed.donation_date

    # Eligibility check (90 days rule)
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

        "last_donation_date": (
            last_donation.strftime("%Y-%m-%d") if last_donation else None
        ),

        "eligibility_status": eligibility,

        "requests": request_list,

        "donation_history": donation_history
    })

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
    return Response({"success": True})
@api_view(["POST"])
@permission_classes([AllowAny])
def admin_remove_inventory(request):

    blood_type = request.data.get("blood_type")
    units = int(request.data.get("units", 0))

    try:
        stock = BloodStock.objects.get(
            hospital=None,
            blood_type=blood_type
        )
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

@api_view(["GET"])
@permission_classes([AllowAny])
def admin_activity_logs(request):

    role = request.GET.get("role")       # patient / donor / hospital
    log_type = request.GET.get("type")   # blood_request / donor_accept / completed
    date = request.GET.get("date")

    logs = Notification.objects.all().order_by("-created_at")

    # ✅ FILTER BY TYPE
    if log_type and log_type != "all":
        logs = logs.filter(type=log_type)

    # ✅ FILTER BY DATE
    if date:
        logs = logs.filter(created_at__date=date)

    data = []

    for n in logs:

        # 🔍 DETERMINE ROLE
        role_type = "system"

        if n.user:
            # Check if donor or patient
            donor = Donor.objects.filter(email=n.user.email).first()
            if donor:
                role_type = "donor"
            else:
                role_type = "patient"

        elif hasattr(n, "hospital") and n.hospital:
            role_type = "hospital"

        # ✅ FILTER BY ROLE
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