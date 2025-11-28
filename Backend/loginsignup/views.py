import json
import random
import string
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from google.oauth2 import id_token
from google.auth.transport import requests
from .models import GoogleSignup, Patient
from django.core.mail import send_mail

GOOGLE_CLIENT_ID = "320231613519-n8ppnf9bof8r6js60el89rar1mvtl8lo.apps.googleusercontent.com"

def generate_code():
    return ''.join(random.choices(string.digits, k=6))

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

        # If user existed but was not verified, update code
        if not created:
            user.verification_code = code
            user.is_verified = False
            user.save()

        # Send verification code email
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
            "user_type": user.user_type
        })

    except Exception as e:
        print("Google login error:", e)
        return JsonResponse({"success": False, "message": "Invalid Google token"})


@csrf_exempt
def verify_code(request):
    data = json.loads(request.body)
    email = data.get("email")
    code = data.get("code")

    user = GoogleSignup.objects.filter(email=email, verification_code=code).first()
    if not user:
        return JsonResponse({"success": False, "message": "Invalid code"})

    user.is_verified = True
    user.save()

    return JsonResponse({"success": True})
@csrf_exempt
def patient_signup_manually(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "Invalid request"}, status=400)

    data = json.loads(request.body)

    fullname = data.get("fullname")
    emailaddress = data.get("emailaddress")
    phonenumber = data.get("phonenumber")
    # address = data.get("address")
    password = data.get("password")
    confirmpassword = data.get("confirmpassword")

    if password != confirmpassword:
        return JsonResponse({"success": False, "message": "Passwords do not match"})

    # Check duplicate email
    if Patient.objects.filter(emailaddress=emailaddress).exists():
        return JsonResponse({"success": False, "message": "Email already registered"})

    # Create patient
    patient = Patient(
        fullname=fullname,
        emailaddress=emailaddress,
        phonenumber=phonenumber,
        address=address,
    )
    patient.set_password(password)
    patient.save()

    return JsonResponse({"success": True, "message": "Account created successfully!"})