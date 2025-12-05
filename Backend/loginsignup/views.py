{"id":"27451","variant":"standard","title":"Updated views.py with Patient insert after Google verification"}
import json
import random
import string
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from google.oauth2 import id_token
from google.auth.transport import requests
from .models import GoogleSignup, Patient
from django.core.mail import send_mail
from django.contrib.auth.hashers import make_password
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.contrib.auth.hashers import check_password

GOOGLE_CLIENT_ID = "320231613519-n8ppnf9bof8r6js60el89rar1mvtl8lo.apps.googleusercontent.com"


def generate_code():
    return ''.join(random.choices(string.digits, k=6))


# --------------------------------------------------
# GOOGLE SIGNUP (Create or update GoogleSignup only)
# --------------------------------------------------
@csrf_exempt
def google_signup(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "Invalid request method"})

    data = json.loads(request.body)
    token = data.get("credential")
    user_type = data.get("user_type", "patient")

    try:
        idinfo = id_token.verify_oauth2_token(token, requests.Request(), GOOGLE_CLIENT_ID)

        email = idinfo["email"]
        fullname = idinfo.get("name", "")

        code = generate_code()

        user, created = GoogleSignup.objects.get_or_create(
            email=email,
            defaults={
                "fullname": fullname,
                "user_type": user_type,
                "verification_code": code,
                "is_verified": False
            }
        )

        # If user exists but NOT verified → update verification code
        if not created:
            user.verification_code = code
            user.is_verified = False
            user.save()

        # Send verification email
        send_mail(
            subject="RedDrop Verification Code",
            message=f"Your verification code is: {code}",
            from_email="harshanabhandari2@gmail.com",
            recipient_list=[email],
            fail_silently=False
        )

        return JsonResponse({"success": True, "email": email})

    except Exception as e:
        print("Google signup error:", e)
        return JsonResponse({"success": False, "message": "Invalid Google token"})


# --------------------------------------------------
# GOOGLE LOGIN (Only if verified)
# --------------------------------------------------
@csrf_exempt
def google_login(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "Invalid request method"})

    data = json.loads(request.body)
    token = data.get("credential")

    try:
        idinfo = id_token.verify_oauth2_token(token, requests.Request(), GOOGLE_CLIENT_ID)

        email = idinfo["email"]

        user = GoogleSignup.objects.filter(email=email, is_verified=True).first()
        if not user:
            return JsonResponse({"success": False, "message": "User not registered or not verified."})

        return JsonResponse({
            "success": True,
            "fullname": user.fullname,
            "user_type": user.user_type,
            "email": user.email
        })

    except Exception as e:
        print("Google login error:", e)
        return JsonResponse({"success": False, "message": "Invalid Google token"})


# --------------------------------------------------
# VERIFY GOOGLE CODE → Insert minimal info into Patient
# --------------------------------------------------
@csrf_exempt
def verify_code(request):
    data = json.loads(request.body)
    email = data.get("email")
    code = data.get("code")

    user = GoogleSignup.objects.filter(email=email, verification_code=code).first()
    if not user:
        return JsonResponse({"success": False, "message": "Invalid code"})

    # Mark Google user as verified
    user.is_verified = True
    user.save()

    # Create patient entry ONLY if not already created
    Patient.objects.get_or_create(
        emailaddress=user.email,
        defaults={
            "fullname": user.fullname,
            "password": None,
            "confirm_password": None,
            "phonenumber": None
        }
    )

    return JsonResponse({"success": True})


# --------------------------------------------------
# MANUAL SIGNUP (Normal full signup)
# --------------------------------------------------
@csrf_exempt
def patient_signup_manually(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "Invalid request"}, status=400)

    data = json.loads(request.body)

    fullname = data.get("fullname")
    emailaddress = data.get("emailaddress")
    phonenumber = data.get("phonenumber")
    password = data.get("password")
    confirmpassword = data.get("confirmpassword")

    if password != confirmpassword:
        return JsonResponse({"success": False, "message": "Passwords do not match"})

    # Check email in BOTH Patient and GoogleSignup
    if Patient.objects.filter(emailaddress=emailaddress).exists():
        return JsonResponse({"success": False, "message": "Email already registered"})

    if GoogleSignup.objects.filter(email=emailaddress).exists():
        return JsonResponse({"success": False, "message": "Email already used for Google Signup"})


    # Create patient
    patient = Patient(
        fullname=fullname,
        emailaddress=emailaddress,
        phonenumber=phonenumber
    )
    patient.password = make_password(password)
    patient.confirm_password = make_password(confirmpassword)
    patient.save()

    return JsonResponse({"success": True, "message": "Account created successfully!"})

@csrf_exempt
def patient_login(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "Invalid request method"})

    data = json.loads(request.body)
    email = data.get("emailaddress")
    password = data.get("password")

    if not email or not password:
        return JsonResponse({"success": False, "message": "Email and password are required"})

    try:
        patient = Patient.objects.get(emailaddress=email)

        # Correct way to check hashed password
        if check_password(password, patient.password):
            return JsonResponse({
                "success": True,
                "fullname": patient.fullname,
                "emailaddress": patient.emailaddress,
            })
        else:
            return JsonResponse({"success": False, "message": "Incorrect password"})

    except Patient.DoesNotExist:
        return JsonResponse({"success": False, "message": "No account found with this email"})
    # Fetch profile
@api_view(['GET'])
def get_patient_profile(request):
    email = request.GET.get('email')
    if not email:
        return Response({"success": False, "message": "Email parameter missing"})

    # Clean email and do case-insensitive search
    email = email.strip()
    patient = Patient.objects.filter(emailaddress__iexact=email).first()

    if not patient:
        return Response({"success": False, "message": "Patient not found."})

    data = {
        "fullname": patient.fullname,
        "emailaddress": patient.emailaddress,
        "phonenumber": patient.phonenumber,
        "date_of_birth": patient.date_of_birth.strftime("%Y-%m-%d") if patient.date_of_birth else "",
        "gender": patient.gender,
        "blood_type": patient.blood_type,
        "street_address": patient.street_address,
        "city": patient.city,
        "state": patient.state,
        "zip_code": patient.zip_code,
        "weight": patient.weight,
        "height": patient.height,
        "allergies": patient.allergies,
        "medical_conditions": patient.medical_conditions,
        "emergency_name": patient.emergency_name,
        "emergency_relationship": patient.emergency_relationship,
        "emergency_phone": patient.emergency_phone,
        "emergency_email": patient.emergency_email
    }
    return Response({"success": True, "data": data})

# Update profile
from datetime import datetime

@api_view(['POST'])
def update_patient_profile(request):
    email = request.data.get('emailaddress')
    try:
        patient = Patient.objects.get(emailaddress=email)
        fields = [
            "fullname", "phonenumber", "date_of_birth", "gender", "blood_type",
            "street_address", "city", "state", "zip_code",
            "weight", "height", "allergies", "medical_conditions",
            "emergency_name", "emergency_relationship", "emergency_phone", "emergency_email"
        ]

        for field in fields:
            if field in request.data:
                value = request.data[field]
                # Convert date_of_birth to proper format
                if field == "date_of_birth" and value:
                    try:
                        # Accept YYYY/MM/DD or YYYY-MM-DD
                        value = datetime.strptime(value, "%Y/%m/%d").date()
                    except ValueError:
                        try:
                            value = datetime.strptime(value, "%Y-%m-%d").date()
                        except ValueError:
                            return Response({"success": False, "message": "Invalid date format for date_of_birth. Use YYYY-MM-DD"})
                setattr(patient, field, value)
        
        patient.save()
        return Response({"success": True, "message": "Profile updated successfully."})
    except Patient.DoesNotExist:
        return Response({"success": False, "message": "Patient not found."})
