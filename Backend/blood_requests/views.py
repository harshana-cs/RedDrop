from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
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
# REGULAR DJANGO VIEWS
# =========================================================

@login_required
def create_request(request):
    if request.method == "POST":
        form = BloodRequestForm(request.POST, request.FILES)
        if form.is_valid():
            blood_request = form.save(commit=False)

            patient = Patient.objects.filter(
                emailaddress=request.user.username
            ).first()

            if not patient:
                messages.error(request, "Patient profile not found.")
                return redirect("/")

            blood_request.patient = patient
            blood_request.save()

            messages.success(request, "Blood request submitted successfully!")
            return redirect("blood_request_list")
    else:
        form = BloodRequestForm()

    return render(request, "blood_requests/create_request.html", {"form": form})


@login_required
def request_list(request):
    patient = Patient.objects.filter(
        emailaddress=request.user.username
    ).first()

    if not patient:
        messages.error(request, "Patient profile not found.")
        return redirect("/")

    requests_qs = BloodRequest.objects.filter(patient=patient)
    return render(
        request,
        "blood_requests/request_list.html",
        {"requests": requests_qs}
    )


def create_request_view(request):
    return render(request, "blood_requests/blood_request.html")


@login_required
def dashboard_view(request):
    return render(request, "blood_requests/blood_request.html")


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

    serializer = BloodRequestSerializer(qs, many=True)

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
        "data": serializer.data
    })


# =========================================================
# API – CREATE BLOOD REQUEST
# =========================================================

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_create_request(request):
    patient = Patient.objects.filter(
        emailaddress=request.user.username
    ).first()

    if not patient:
        return Response(
            {"success": False, "message": "Patient not found"},
            status=403
        )

    serializer = BloodRequestSerializer(
        data=request.data,
        context={"request": request}
    )

    if serializer.is_valid():
        serializer.save(patient=patient)
        return Response(
            {"success": True, "data": serializer.data},
            status=201
        )

    return Response(
        {"success": False, "errors": serializer.errors},
        status=400
    )


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

    # Latest approved request
    blood_request = BloodRequest.objects.filter(
        patient=patient,
        status="approved"
    ).order_by("-created_at").first()

    if not blood_request:
        return Response({"success": True, "donors": []})

    required_blood = blood_request.blood_type
    request_district = normalize_district(blood_request.district)

    # Blood compatibility
    compatible_donor_bloods = [
        donor_blood
        for donor_blood, receivers in BLOOD_COMPATIBILITY.items()
        if required_blood in receivers
    ]

    # Approved donors with compatible blood
    donors_qs = Donor.objects.filter(
        is_approved=True,
        blood_type__in=compatible_donor_bloods
    )

    # 🔑 District smart-match
    donors = []
    for donor in donors_qs:
        donor_district = normalize_district(donor.city)

        if donor_district == request_district:
            donors.append(donor)

    data = [{
        "id": d.id,
        "name": f"{d.first_name} {d.last_name}".strip(),
        "blood_type": d.blood_type,
        "district": d.city,
        "phone": d.phone_number,
        "email": d.email,
    } for d in donors]

    return Response({
        "success": True,
        "request": {
            "id": blood_request.id,
            "blood_type": required_blood,
            "district": blood_request.district
        },
        "donors": data
    })
