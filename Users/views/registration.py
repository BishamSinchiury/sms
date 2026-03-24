"""
registration.py
---------------
Registration views for creating accounts via the new wizard.
"""
from rest_framework import generics, serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from django.core.cache import caches  # FIX 1 (BUG 2): to read verified-email gate key

from Orgs.models.organization import Organization
from Users.models.roles import OrgRole, SYSTEM_ADMIN_ROLE
from Users.models.membership import MembershipStatus  # FIX 10 (BUG 10): for profile_complete
from Users.serializers.registration import RegisterRoleAwareSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from django.conf import settings

# FIX 1 (BUG 2): Use the same OTP cache alias + verified key prefix as auth_views.py.
OTP_CACHE        = caches["otp"]
_VERIFIED_PREFIX = "signup_email_verified:"

class RolesListView(generics.ListAPIView):
    """
    GET /api/auth/roles/?org=<slug>
    """
    permission_classes = [AllowAny]
    
    class RoleListSerializer(serializers.ModelSerializer):
        class Meta:
            model = OrgRole
            fields = ["id", "name", "role_type"]

    serializer_class = RoleListSerializer

    def get_queryset(self):
        org_slug = self.request.query_params.get("org", "").strip()
        if not org_slug:
            return OrgRole.objects.none()
        try:
            org = Organization.objects.get(slug=org_slug, is_active=True)
            return OrgRole.objects.filter(org=org).exclude(name=SYSTEM_ADMIN_ROLE)
        except Organization.DoesNotExist:
            return OrgRole.objects.none()

    def list(self, request, *args, **kwargs):
        org_slug = request.query_params.get("org", "").strip()
        if not org_slug:
            return Response({"detail": "org query parameter is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            org = Organization.objects.select_related("profile").get(slug=org_slug, is_active=True)
        except Organization.DoesNotExist:
            return Response(
                {"detail": "Organization not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        profile = getattr(org, "profile", None)
        if not profile or not profile.name:
            return Response(
                {"detail": "This organization has not completed setup. Registration is currently unavailable."},
                status=status.HTTP_403_FORBIDDEN,
            )

        return super().list(request, *args, **kwargs)

class RegisterWizardView(generics.CreateAPIView):
    """
    POST /api/auth/register/
    Creates User + OrgMembership + Person in one atomic transaction.
    Requires prior email OTP verification (SendOTPView → VerifyOTPView).
    """
    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    serializer_class = RegisterRoleAwareSerializer

    def create(self, request, *args, **kwargs):
        raw_email = request.data.get("email", "").lower().strip()
        if not raw_email:
            return Response(
                {"detail": "email is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        verified_key = f"{_VERIFIED_PREFIX}{raw_email}"
        if not OTP_CACHE.get(verified_key):
            return Response(
                {"detail": "Email not verified. Please complete OTP verification first."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        

        OTP_CACHE.delete(verified_key)

        # Generate tokens for the new user auto-login
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)
        membership = getattr(user, "membership", None)

        profile_complete = (
            membership.status != MembershipStatus.PENDING
            if membership else False
        )

        response = Response({
            "message": "Registration received — awaiting approval",
            "access": access_token,
            "user_id": user.id,
            "profile_complete": profile_complete,
            "membership_status": membership.status if membership else None,
            "role_type": membership.role.role_type if membership and membership.role else None,
        }, status=status.HTTP_201_CREATED)
        
        # Set HttpOnly refresh token cookie
        cookie_name = getattr(settings, 'SIMPLE_JWT', {}).get('AUTH_COOKIE', 'refresh_token')
        response.set_cookie(
            cookie_name,
            refresh_token,
            max_age=7 * 24 * 60 * 60,
            httponly=True,
            samesite='Lax',
            secure=getattr(settings, 'SIMPLE_JWT', {}).get('AUTH_COOKIE_SECURE', False)
        )
        
        return response
