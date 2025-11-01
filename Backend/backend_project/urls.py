from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect

urlpatterns = [
    path('admin/', admin.site.urls),
    path('loginsignup/', include('loginsignup.urls')),

    # Root URL redirect to loginsignup page
    path('', lambda request: redirect('home')),  # '/' redirects to signup page
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
