from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),    
    path('api/user/', include('Users.urls')),
    path('api/org/', include('Orgs.urls')),
]
