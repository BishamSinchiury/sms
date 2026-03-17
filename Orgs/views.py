from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from .models.organization import Organization
from .models.profile import OrganizationProfile
from .serializers import OrganizationProfileSerializer

class OrgProfileMeView(APIView):
    """
    GET /api/org/profile/me/
    Returns the OrganizationProfile for the organization the current
    system admin is associated with (via session).
    """
    authentication_classes = [] # Handled by session middleware + is_sys_admin check
    permission_classes     = []

    def get(self, request):
        if not request.session.get("is_sys_admin"):
            return Response(
                {"detail": "System admin session required."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        org_slug = request.session.get("org_slug")
        if not org_slug:
             return Response(
                {"detail": "No organization associated with this session."},
                status=status.HTTP_400_BAD_REQUEST
            )

        org = Organization.objects.get(slug=org_slug)
        profile = getattr(org, 'profile', None)
        if not profile:
            return Response({"detail": "Profile not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = OrganizationProfileSerializer(profile, context={'request': request})
        return Response(serializer.data)

    def patch(self, request):
        """
        PATCH /api/org/profile/me/
        Updates the organization profile. Supports multipart/form-data for file uploads.
        """
        if not request.session.get("is_sys_admin"):
            return Response(
                {"detail": "System admin session required."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        org_slug = request.session.get("org_slug")
        org = get_object_or_404(Organization, slug=org_slug)
        
        # Ensure profile exists before updating
        profile, created = OrganizationProfile.objects.get_or_create(org=org)

        serializer = OrganizationProfileSerializer(profile, data=request.data, partial=True, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
