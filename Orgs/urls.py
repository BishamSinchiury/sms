from django.urls import path
from .views import OrgProfileMeView
from .views.sub_org_views import SubOrgListCreateView, SubOrgDetailView

urlpatterns = [
    path('profile/me/',        OrgProfileMeView.as_view(),      name='org-profile-me'),
    path('sub-orgs/',          SubOrgListCreateView.as_view(),   name='sub-org-list-create'),
    path('sub-orgs/<slug:code>/', SubOrgDetailView.as_view(),   name='sub-org-detail'),
]
