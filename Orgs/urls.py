from django.urls import path
from .views import OrgProfileMeView, OrgLegalMeView, OrgOwnerListCreateView, OrgOwnerDetailView
from .views.sub_org_views import SubOrgListCreateView, SubOrgDetailView

urlpatterns = [
    # FIX 8 (BUG 5): Removed duplicate path('me/', ...) — was identical to profile/me/
    # but caused non-deterministic reverse('org-profile-me') and unnecessary attack surface.
    path('profile/me/',         OrgProfileMeView.as_view(),      name='org-profile-me'),
    path('legal/me/',           OrgLegalMeView.as_view(),        name='org-legal-me'),
    path('sub-orgs/',           SubOrgListCreateView.as_view(),  name='sub-org-list-create'),
    path('sub-orgs/<str:code>/', SubOrgDetailView.as_view(),      name='sub-org-detail'),
    path("sys/owners/",          OrgOwnerListCreateView.as_view(), name="sys-owners-list"),
    path("sys/owners/<int:pk>/", OrgOwnerDetailView.as_view(),     name="sys-owners-detail"),

]
