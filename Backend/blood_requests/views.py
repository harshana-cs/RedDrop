from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from .forms import BloodRequestForm
from .models import BloodRequest
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from .serializers import BloodRequestSerializer

# -----------------------------
# Regular Django Views
# -----------------------------

@login_required
def create_request(request):
    """Standard Django form submission view"""
    if request.method == "POST":
        form = BloodRequestForm(request.POST, request.FILES)
        if form.is_valid():
            blood_request = form.save(commit=False)
            blood_request.patient = request.user
            blood_request.save()
            messages.success(request, "Blood request submitted successfully!")
            return redirect("blood_request_list")
    else:
        form = BloodRequestForm()
    return render(request, "blood_requests/create_request.html", {"form": form})

@login_required
def request_list(request):
    """List of blood requests for the logged-in user"""
    requests = request.user.bloodrequest_set.all()
    return render(request, "blood_requests/request_list.html", {"requests": requests})

def create_request_view(request):
    """Render the JS frontend page for fetch/SPA submissions"""
    return render(request, "blood_requests/blood_request.html")


# -----------------------------
# API-style View for JS Fetch
# -----------------------------

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def api_create_request(request):
    """
    Accept JSON POST from frontend fetch with authentication.
    Sets patient automatically from logged-in user.
    """
    serializer = BloodRequestSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save(patient=request.user)
        return Response({"success": True, "data": serializer.data}, status=status.HTTP_201_CREATED)
    return Response({"success": False, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
