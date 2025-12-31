from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.conf import settings

@api_view(["POST"])
@permission_classes([AllowAny])
def admin_secret_login(request):
    secret = request.data.get("secret_key")

    if not secret:
        return Response({"success": False, "message": "Secret Key Required"}, status=400)

    if secret == settings.ADMIN_SECRET_KEY:
        return Response({"success": True, "redirect": "admin_dashboard.html"})
    
    return Response({"success": False, "message": "Invalid Secret Key"}, status=401)
