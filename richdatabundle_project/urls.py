from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),  # Make sure this is here
    path('api/', include('core.api_urls')),  # your API endpoints
]
