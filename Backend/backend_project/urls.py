from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView


urlpatterns = [
    path('admin/', admin.site.urls),

    path('loginsignup/', include('loginsignup.urls')),
    path('blood_requests/', include('blood_requests.urls')),
    path('donor/', include('register_donor.urls')),
    path('api/admin/', include('adminpanel.urls')),

    path("api/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/donor/", include("donor.urls")),
    path("api/hospital/", include("hospital.urls")),
    path("api/", include("blood_stock.urls")),


    # Root redirect
    path('', lambda request: redirect('home')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
