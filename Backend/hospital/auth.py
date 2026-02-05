import jwt
from django.conf import settings
from hospital.models import Hospital

def get_hospital_from_token(request):
    auth_header = request.headers.get("Authorization")

    if not auth_header or not auth_header.startswith("Bearer "):
        return None

    token = auth_header.split(" ")[1]

    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=["HS256"]
        )
        hospital_id = payload.get("hospital_id")
        return Hospital.objects.get(id=hospital_id, is_active=True)
    except Exception as e:
        print("JWT ERROR:", e)
        return None
