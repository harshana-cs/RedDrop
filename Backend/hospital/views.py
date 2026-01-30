from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from .models import Hospital
import jwt
from django.conf import settings
from django.utils import timezone

@api_view(["POST"])
@permission_classes([AllowAny])
def hospital_login(request):
    username = request.data.get("username")
    password = request.data.get("password")

    try:
        hospital = Hospital.objects.get(username=username, is_active=True)
    except Hospital.DoesNotExist:
        return Response({"success": False}, status=401)

    if not hospital.check_password(password):
        return Response({"success": False}, status=401)

    payload = {
        "hospital_id": hospital.id,
        "exp": timezone.now() + timezone.timedelta(hours=12)
    }

    token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")

    return Response({
        "success": True,
        "token": token
    })
