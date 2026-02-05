from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.conf import settings
from hospital.models import Hospital, HospitalProfile
from blood_requests.models import BloodRequest
from register_donor.models import Donor
from loginsignup.models import Patient
from hospital.models import Hospital
from django.core.mail import send_mail
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from hospital.models import HospitalApplication, Hospital



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

    # ✅ ONLY approve — no donor, no OTP
    blood_request.status = "approved"
    blood_request.patient_confirmed = False
    blood_request.fulfilled = False
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
            "hospital": r.hospital,
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
@permission_classes([AllowAny])  # you can later change to IsAdminUser
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
