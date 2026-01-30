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

from loginsignup.models import Patient
from donor.models import DonationConfirmation
from django.utils import timezone


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
        patient=patient
    )

    if blood_request.status != "approved":
        return Response(
            {"message": "Only approved requests can be confirmed"},
            status=400
        )

    # 🔒 Prevent double confirmation
    if blood_request.donation_date:
        return Response(
            {"message": "Already confirmed"},
            status=400
        )

    blood_request.patient_confirmed = True   # 🔥 THIS WAS MISSING
    blood_request.fulfilled = True
    blood_request.donation_date = timezone.now()
    blood_request.save()

    DonationConfirmation.objects.update_or_create(
        request=blood_request,
        donor=blood_request.assigned_donor,
        defaults={
            "patient_confirmed": True
        }
    )

    return Response({
        "success": True,
        "message": "Blood receipt confirmed successfully"
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
