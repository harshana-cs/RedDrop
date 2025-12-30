from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import BloodRequestForm
from .models import BloodRequest
from loginsignup.models import Patient
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .serializers import BloodRequestSerializer
from django.shortcuts import get_object_or_404
from django.db.models import Count


# -----------------------------
# Regular Django Views
# -----------------------------

@login_required
def create_request(request):
    """
    Standard Django form submission view using BloodRequestForm.
    Maps the logged-in Django User to a Patient.
    """
    if request.method == "POST":
        form = BloodRequestForm(request.POST, request.FILES)
        if form.is_valid():
            blood_request = form.save(commit=False)
            patient = Patient.objects.filter(email=request.user.email).first()
            if not patient:
                messages.error(request, "Patient profile not found. Cannot submit request.")
                return redirect("blood_request_list")
            blood_request.patient = patient
            blood_request.save()
            messages.success(request, "Blood request submitted successfully!")
            return redirect("blood_request_list")
    else:
        form = BloodRequestForm()
    return render(request, "blood_requests/create_request.html", {"form": form})

@login_required
def request_list(request):
    """
    List all blood requests for the logged-in patient.
    """
    patient = Patient.objects.filter(emailaddress=request.user.email).first()
    if not patient:
        messages.error(request, "Patient profile not found.")
        return redirect("/")
    requests_qs = BloodRequest.objects.filter(patient=patient)
    return render(request, "blood_requests/request_list.html", {"requests": requests_qs})


def create_request_view(request):
    """
    Render the JS frontend page for fetch/SPA submissions.
    """
    return render(request, "blood_requests/blood_request.html")

@login_required
def dashboard_view(request):
    """
    Render the JS frontend dashboard page for SPA-style interaction.
    """
    return render(request, "blood_requests/blood_request.html")


# -----------------------------
# API-style View for JS Fetch
# -----------------------------
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_user_requests(request):
    """
    Returns full request history + dashboard statistics
    for logged in patient.
    """
    # FIXED — always use emailaddress not email
    patient = Patient.objects.filter(emailaddress=request.user.username).first()
    if not patient:
        return Response({"success": False, "message": "Patient not found"}, status=403)

    requests_qs = BloodRequest.objects.filter(patient=patient).order_by("-created_at")
    serializer = BloodRequestSerializer(requests_qs, many=True)

    total_requests = requests_qs.count()
    approved_requests = requests_qs.filter(status="approved").count()
    pending_requests = requests_qs.filter(status="pending").count()
    completed_requests = requests_qs.filter(status="completed").count()

    # ------- Most Requested Blood Group -------
        # ------- Most Requested Blood Group -------
    most_requested = (
        requests_qs.values("blood_type")
        .annotate(total=Count("blood_type"))
        .order_by("-total")
        .first()
    )

    most_requested_group = most_requested["blood_type"] if most_requested else None
    most_requested_count = most_requested["total"] if most_requested else 0


    # ------- Success Rate -------
    success_rate = 0
    if total_requests > 0:
        success_rate = round((completed_requests / total_requests) * 100)

    # ------- Average Response Time -------
    # We assume you have an "approved_at" or update timestamp,
    # if not then this will just return None gracefully
    avg_response_hours = None
    try:
        completed = requests_qs.filter(status="completed")
        if completed.exists():
            diffs = [
                (req.updated_at - req.created_at).total_seconds() / 3600
                for req in completed
                if req.updated_at
            ]
            if diffs:
                avg_response_hours = round(sum(diffs) / len(diffs))
    except:
        avg_response_hours = None

    return Response({
        "success": True,
        "patient_name": patient.fullname,
        "stats": {
            "total": total_requests,
            "approved": approved_requests,
            "pending": pending_requests,
            "completed": completed_requests,
            "most_requested_group": most_requested_group,
            "most_requested_count": most_requested_count,
            "success_rate": success_rate,
            "avg_response_hours": avg_response_hours
        },
        "data": serializer.data
    })



@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_create_request(request):
    """
    API endpoint for creating blood requests using JWT authentication.
    Accepts multipart/form-data including files.
    """
    try:
        print("request.user:", request.user)
        print("request.auth:", request.auth)

        # Map JWT user to Patient
        patient = Patient.objects.filter(emailaddress=request.user.username).first()
        if not patient:
            return Response({"success": False, "message": "Patient not found"}, status=403)

        # Use serializer with files
        serializer = BloodRequestSerializer(
            data=request.data, 
            context={"request": request}
        )

        if serializer.is_valid():
            serializer.save(patient=patient)
            return Response({"success": True, "data": serializer.data}, status=201)
        else:
            return Response({"success": False, "errors": serializer.errors}, status=400)

    except Exception as e:
        return Response({"success": False, "message": str(e)}, status=500)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_confirm_receipt(request, request_id):
    patient = Patient.objects.filter(emailaddress=request.user.username).first()
    if not patient:
        return Response({"success": False, "message": "Patient not found"}, status=403)

    blood_request = get_object_or_404(BloodRequest, id=request_id, patient=patient)

    if blood_request.status != "approved":
        return Response({
            "success": False,
            "message": "Only approved requests can be confirmed."
        }, status=400)

    blood_request.status = "completed"
    blood_request.fulfilled = True
    blood_request.save()

    return Response({"success": True, "message": "Request marked as received!"})
