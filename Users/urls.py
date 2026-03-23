"""
Users/urls.py
-------------
URL routing for the Users app.

Namespaces
----------
/api/sys/auth/   — System admin session-based two-step login
"""

from django.urls import path

from Users.views.sys_auth_views import (
    SysAdminLoginView,
    SysAdminOTPVerifyView,
    SysAdminLogoutView,
    SysAdminMeView,
)
from Users.views.auth_views import VerifyEmailView
from Users.views.user_views import UserProfileUpdateView
from Users.views.sys_user_views import PendingUsersListView, ApproveUserView, RejectUserView
from Users.views.registration import RegisterWizardView, RolesListView
from Users.views.profile import MyProfileView, MyDocumentsView, MyGuardiansView
from Users.models.person import Person

from Orgs.views.activity_log_views import (
    OrgActivityLogListView,
    OrgActivityLogExportView,
    OrgActivityLogActorsView
)

from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from django.conf import settings
from django.contrib.auth import get_user_model

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        
        try:
            profile_complete = Person.objects.filter(user=self.user).exists()
        except Exception:
            profile_complete = False

        data['user'] = {
            "id": str(self.user.id),
            "email": self.user.email,
            "first_name": self.user.first_name,
            "last_name": self.user.last_name,
            "profile_complete": profile_complete,
        }
        
        try:
            membership = self.user.membership
            if membership and membership.org and not membership.org.is_active:
                from rest_framework.exceptions import AuthenticationFailed
                raise AuthenticationFailed("Your organization is currently inactive.")
            
            data['user']['membership'] = {
                "status": membership.status,
                "role_type": membership.role.role_type if membership.role else None,
                "role_name": membership.role.name if membership.role else None,
                "org_name": membership.org.name if membership.org else None,
            }
        except AuthenticationFailed:
            raise
        except Exception:
            data['user']['membership'] = None

        return data

class CookieTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            refresh_token = response.data.get('refresh')
            access_token = response.data.get('access')
            user_data = response.data.get('user', {})
            membership = user_data.get('membership') or {}
            
            new_data = {
                'access_token': access_token,
                'profile_complete': user_data.get('profile_complete', False),
                'membership_status': membership.get('status'),
                'role_type': membership.get('role_type'),
            }
            response.data = new_data
            
            if refresh_token:
                cookie_name = getattr(settings, 'SIMPLE_JWT', {}).get('AUTH_COOKIE', 'refresh_token')
                response.set_cookie(
                    cookie_name,
                    refresh_token,
                    max_age=7 * 24 * 60 * 60,
                    httponly=True,
                    samesite='Lax',
                    secure=False
                )
        return response

class CookieTokenRefreshView(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        cookie_name = getattr(settings, 'SIMPLE_JWT', {}).get('AUTH_COOKIE', 'refresh_token')
        refresh_token = request.COOKIES.get(cookie_name)
        
        if not refresh_token:
            return Response(
                {"detail": "No active session. Please log in."},
                status=400
            )

        data = {}
        if refresh_token:
            data['refresh'] = refresh_token
            
        serializer = self.get_serializer(data=data)
        try:
            serializer.is_valid(raise_exception=True)
        except Exception as e:
            return Response({"detail": str(e)}, status=400)
            
        new_refresh = serializer.validated_data.get('refresh')
        access_token = serializer.validated_data.get('access')
        
        try:
            User = get_user_model()
            token_obj = RefreshToken(refresh_token)
            # Safe extraction of user id
            user_id_claim = getattr(settings, 'SIMPLE_JWT', {}).get('USER_ID_CLAIM', 'user_id')
            user_id = token_obj.payload.get(user_id_claim)
            user = User.objects.get(id=user_id) if user_id else None
        except Exception:
            user = None

        profile_complete = False
        if user:
            try:
                profile_complete = Person.objects.filter(user=user).exists()
            except Exception:
                pass

        membership_status = None
        role_type = None
        if user:
            try:
                membership = user.membership
                membership_status = membership.status
                role_type = membership.role.role_type if membership.role else None
            except Exception:
                pass

        response_data = {
            'access_token': access_token,
            'profile_complete': profile_complete,
            'membership_status': membership_status,
            'role_type': role_type,
        }
        
        response = Response(response_data, status=200)

        if new_refresh:
            response.set_cookie(
                cookie_name,
                new_refresh,
                max_age=7 * 24 * 60 * 60,
                httponly=True,
                samesite='Lax',
                secure=False
            )
        return response

class CookieTokenLogoutView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        cookie_name = getattr(settings, 'SIMPLE_JWT', {}).get('AUTH_COOKIE', 'refresh_token')
        refresh_token = request.COOKIES.get(cookie_name)
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except Exception:
                pass
        
        response = Response({"detail": "Successfully logged out."}, status=200)
        response.delete_cookie(cookie_name)
        return response

urlpatterns = [
    # ── System admin authentication (session + OTP) ──────────────────────
    # Step 1: Submit email + password → OTP dispatched to admin
    path("sys/auth/login/",       SysAdminLoginView.as_view(),     name="sys-auth-login"),
    # Step 2: Submit email + OTP → session created
    path("sys/auth/verify-otp/",  SysAdminOTPVerifyView.as_view(), name="sys-auth-verify-otp"),
    # Logout: flush session + mark audit record inactive
    path("sys/auth/logout/",      SysAdminLogoutView.as_view(),    name="sys-auth-logout"),
    # Me: check active session cookie → returns identity (used on page refresh)
    path("sys/auth/me/",          SysAdminMeView.as_view(),        name="sys-auth-me"),

    # ── System admin activity logs ───────────────────────────────────────
    path("sys/logs/",             OrgActivityLogListView.as_view(),   name="sys-logs-list"),
    path("sys/logs/export/",      OrgActivityLogExportView.as_view(), name="sys-logs-export"),
    path("sys/logs/actors/",      OrgActivityLogActorsView.as_view(), name="sys-logs-actors"),

    # ── System admin user management ─────────────────────────────────────
    path("sys/users/pending/",    PendingUsersListView.as_view(),  name="sys-users-pending"),
    path("sys/users/<int:pk>/approve/", ApproveUserView.as_view(), name="sys-users-approve"),
    path("sys/users/<int:pk>/reject/",  RejectUserView.as_view(),  name="sys-users-reject"),

    # ── General User authentication (JWT) ────────────────────────────────
    path("auth/login/",           CookieTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("auth/refresh/",         CookieTokenRefreshView.as_view(),    name="token_refresh"),
    path("auth/logout/",          CookieTokenLogoutView.as_view(),     name="token_logout"),
    path("auth/register/",        RegisterWizardView.as_view(),    name="auth-register"),
    path("auth/verify-email/",    VerifyEmailView.as_view(),       name="auth-verify-email"),
    path("auth/roles/",           RolesListView.as_view(),         name="auth-roles"),

    # ── General User Profile ─────────────────────────────────────────────
    path("profile/me/",                   MyProfileView.as_view(),   name="profile-me"),
    path("profile/me/documents/",         MyDocumentsView.as_view(), name="profile-me-documents"),
    path("profile/me/guardians/",         MyGuardiansView.as_view(), name="profile-me-guardians"),
    path("users/me/profile/",             UserProfileUpdateView.as_view(), name="user-profile-update"),
]

