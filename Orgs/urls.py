from django.urls import path
from .views import OrgProfileMeView

urlpatterns = [
    path('profile/me/', OrgProfileMeView.as_view(), name='org-profile-me'),
]
