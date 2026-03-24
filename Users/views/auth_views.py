"""
auth_views.py
-------------
Public registration endpoints for general users.

Registration flow (two-step, with email OTP verification):

  Step 1 — POST /api/auth/register/
    • Validates all fields (org_slug, role, email uniqueness, etc.)
    • Creates User (is_active=False) + OrgMembership (PENDING)
    • Generates 6-digit OTP → cached in Redis (5-min TTL)
    • Dispatches OTP email via Gmail SMTP
    • Returns 200 + { detail, email }

  Step 2 — POST /api/auth/verify-email/
    • Accepts { email, otp }
    • Pops OTP from Redis (single-use)
    • Verifies with constant-time comparison
    • Sets user.is_active = True
    • Returns 200 → user can now log in

Pre-registration OTP flow (guards RegisterWizardView):

  Step A — POST /api/auth/send-otp/
    • Sends OTP without creating a user

  Step B — POST /api/auth/verify-otp/
    • Validates OTP, pops it, then writes a short-lived
      'signup_email_verified:{email}' key to Redis (600s TTL)
    • RegisterWizardView checks this key before creating anything
    • The key is deleted (single-use) once registration completes
"""

import hmac
import logging
import random
import string

from django.conf import settings
from django.core.cache import caches
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from rest_framework import generics, serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from Orgs.models.organization import Organization
from Users.models.membership import OrgMembership, MembershipStatus
from Users.models.roles import OrgRole, SYSTEM_RESERVED_ROLES
from Users.models.user import User

logger = logging.getLogger(__name__)

OTP_CACHE          = caches["otp"]
OTP_TTL            = 300   # 5 minutes — OTP validity window
_OTP_PREFIX        = "signup_otp:"
_VERIFIED_PREFIX   = "signup_email_verified:"  # FIX 1 (BUG 2): post-OTP gate key
VERIFIED_TTL       = 600   # 10 minutes — enough to complete the wizard


def _otp_key(email: str) -> str:
    return f"{_OTP_PREFIX}{email.lower().strip()}"


# FIX 1 (BUG 2): Key written by VerifyOTPView, read+deleted by RegisterWizardView.
def _verified_key(email: str) -> str:
    return f"{_VERIFIED_PREFIX}{email.lower().strip()}"


def _generate_otp(length: int = 6) -> str:
    return "".join(random.SystemRandom().choices(string.digits, k=length))


def _dispatch_signup_otp(email: str, otp: str, first_name: str = "") -> None:
    """Send email OTP for signup verification (re-uses the same SMTP config as sys admin OTP)."""
    subject    = "Verify your email — OTP"
    from_email = settings.DEFAULT_FROM_EMAIL
    greeting   = f"Hi {first_name}," if first_name else "Hello,"

    text_body = (
        f"{greeting}\n\n"
        f"Your email verification OTP is:\n\n"
        f"    {otp}\n\n"
        f"This OTP expires in 5 minutes. Do not share it with anyone.\n\n"
        f"— SMS Platform"
    )

    html_body = f"""\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Email Verification OTP</title></head>
<body style="margin:0;padding:0;background:#f4f6f8;font-family:'Segoe UI',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6f8;padding:40px 0;">
    <tr><td align="center">
      <table width="480" cellpadding="0" cellspacing="0"
             style="background:#fff;border-radius:12px;box-shadow:0 4px 24px rgba(0,0,0,0.08);overflow:hidden;">
        <tr>
          <td style="background:linear-gradient(135deg,#1a1a2e 0%,#16213e 100%);padding:32px 40px;text-align:center;">
            <h1 style="margin:0;color:#fff;font-size:22px;font-weight:700;">SMS Platform</h1>
            <p style="margin:6px 0 0;color:#a0aec0;font-size:13px;">Email Verification</p>
          </td>
        </tr>
        <tr>
          <td style="padding:40px 40px 32px;">
            <p style="margin:0 0 8px;color:#4a5568;font-size:15px;">{greeting}</p>
            <p style="margin:0 0 28px;color:#4a5568;font-size:15px;line-height:1.6;">
              Your one-time verification code is:
            </p>
            <div style="background:#f7fafc;border:2px dashed #e2e8f0;border-radius:10px;
                        padding:24px;text-align:center;margin-bottom:28px;">
              <span style="font-size:40px;font-weight:800;letter-spacing:12px;
                            color:#1a1a2e;font-family:'Courier New',monospace;">{otp}</span>
            </div>
            <p style="margin:0 0 6px;color:#718096;font-size:13px;text-align:center;">
              ⏱&nbsp;Expires in <strong>5 minutes</strong>.
            </p>
            <p style="margin:0;color:#718096;font-size:13px;text-align:center;">
              Do not share this code with anyone.
            </p>
          </td>
        </tr>
        <tr>
          <td style="background:#f7fafc;padding:16px 40px;text-align:center;border-top:1px solid #edf2f7;">
            <p style="margin:0;color:#cbd5e0;font-size:11px;">
              &copy; SMS Platform &mdash; Automated email, do not reply.
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""

    try:
        msg = EmailMultiAlternatives(subject, text_body, from_email, [email])
        msg.attach_alternative(html_body, "text/html")
        msg.send(fail_silently=False)
        logger.info("Signup OTP dispatched to %s", email)
    except Exception as exc:
        logger.error("Failed to send signup OTP to %s: %s", email, exc)


# FIX 13 (BUG 11): PublicRolesView deleted — it was dead code (never mounted in urls.py).
# RolesListView in registration.py is the active view at /api/auth/roles/.
# The org-profile completeness check has been moved to RolesListView (FIX 3).


# ─────────────────────────────────────────────────────────────────────────────
# Step 1 — Register: validate + create user + send OTP
# ─────────────────────────────────────────────────────────────────────────────

class RegisterSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=150)
    last_name  = serializers.CharField(max_length=150)
    email      = serializers.EmailField()
    password   = serializers.CharField(write_only=True, min_length=8)
    org_slug   = serializers.CharField()
    role_id    = serializers.CharField()

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value.lower().strip()

    def validate(self, data):
        org_slug = data.get("org_slug", "").strip()
        role_id  = data.get("role_id")

        try:
            org = Organization.objects.select_related("profile").get(
                slug=org_slug, is_active=True
            )
        except Organization.DoesNotExist:
            raise serializers.ValidationError(
                {"org_slug": "Organization not found. Please check the slug."}
            )

        profile = getattr(org, "profile", None)
        if not profile or not profile.name:
            raise serializers.ValidationError(
                {"org_slug": "This organization has not completed setup. Registration is currently disabled."}
            )

        try:
            role = OrgRole.objects.get(id=role_id, is_system_role=False, org=org)
        except OrgRole.DoesNotExist:
            raise serializers.ValidationError(
                {"role_id": "Invalid role. The role must belong to the specified organization."}
            )

        data["_org"]  = org
        data["_role"] = role
        return data


class RegisterView(generics.CreateAPIView):
    """
    POST /api/auth/register/
    Step 1 of registration: create user (is_active=False) + send email OTP.
    """
    permission_classes = [AllowAny]
    serializer_class   = RegisterSerializer

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        role = data["_role"]
        org  = data["_org"]

        # Create user with is_active=False until email is verified
        user = User.objects.create_user(
            email=data["email"],
            password=data["password"],
            first_name=data["first_name"],
            last_name=data["last_name"],
            is_active=False,
        )

        OrgMembership.objects.create(
            user=user,
            org=org,
            role=role,
            status=MembershipStatus.PENDING,
        )

        # Generate + cache OTP
        otp       = _generate_otp()
        cache_key = _otp_key(data["email"])
        OTP_CACHE.set(cache_key, otp, timeout=OTP_TTL)

        # Dispatch email (async-safe — failure is logged, not raised)
        _dispatch_signup_otp(data["email"], otp, first_name=data["first_name"])

        return Response(
            {
                "detail": "OTP sent to your email. Please verify to complete registration.",
                "email": data["email"],
            },
            status=status.HTTP_200_OK,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 — Verify email OTP → activate user
# ─────────────────────────────────────────────────────────────────────────────

class VerifyEmailView(APIView):
    """
    POST /api/auth/verify-email/
    Step 2 of registration: verify OTP → set user.is_active = True.
    """
    authentication_classes = []
    permission_classes     = [AllowAny]

    def post(self, request):
        email     = request.data.get("email", "").lower().strip()
        otp_input = request.data.get("otp", "").strip()

        if not email or not otp_input:
            return Response(
                {"detail": "email and otp are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cache_key  = _otp_key(email)
        cached_otp = OTP_CACHE.get(cache_key)

        if cached_otp is None:
            return Response(
                {"detail": "OTP has expired or was never issued. Please register again."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not hmac.compare_digest(str(cached_otp), str(otp_input)):
            return Response(
                {"detail": "Invalid OTP. Please try again."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Valid — delete OTP (single-use) and activate the user
        OTP_CACHE.delete(cache_key)

        try:
            user = User.objects.get(email=email, is_active=False)
        except User.DoesNotExist:
            return Response(
                {"detail": "No pending account found for this email."},
                status=status.HTTP_404_NOT_FOUND,
            )

        user.is_active = True
        user.save(update_fields=["is_active"])

        logger.info("Email verified for user %s — account activated (is_active=True)", email)

        return Response(
            {"detail": "Email verified! Your account is active. You can now log in."},
            status=status.HTTP_200_OK,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Pre-registration Step A — Send OTP (email must be free, no user created yet)
# ─────────────────────────────────────────────────────────────────────────────

class SendOTPView(APIView):
    """
    POST /api/auth/send-otp/
    Pre-registration email verification — Step A.
    Generates and emails a 6-digit OTP cached under signup_otp:{email}.
    Does NOT create a User. Returns 400 if the email already has an active account.
    """
    authentication_classes = []
    permission_classes     = [AllowAny]

    def post(self, request):
        email = request.data.get("email", "").lower().strip()

        if not email:
            return Response(
                {"detail": "email is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Reject if an active account already exists for this email —
        # the OTP flow is only for brand-new registrations.
        if User.objects.filter(email=email).exists():
            return Response(
                {"detail": "An account with this email already exists. Please log in instead."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Generate a fresh OTP, overwriting any previously cached one (allows resend).
        otp       = _generate_otp()
        cache_key = _otp_key(email)
        OTP_CACHE.set(cache_key, otp, timeout=OTP_TTL)

        # Dispatch email — uses the same HTML template as the old flow.
        _dispatch_signup_otp(email, otp)

        logger.info("Pre-registration OTP dispatched to %s", email)

        return Response(
            {"detail": "OTP sent to your email. Please verify within 5 minutes."},
            status=status.HTTP_200_OK,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Pre-registration Step B — Verify OTP (single-use, pop from Redis)
# ─────────────────────────────────────────────────────────────────────────────

class VerifyOTPView(APIView):
    """
    POST /api/auth/verify-otp/
    Pre-registration email verification — Step B.
    Pops the OTP from Redis (single-use). Returns { verified: true, email }
    on success. Does NOT activate or create any User — verification only.
    """
    authentication_classes = []
    permission_classes     = [AllowAny]

    def post(self, request):
        email     = request.data.get("email", "").lower().strip()
        otp_input = request.data.get("otp", "").strip()

        if not email or not otp_input:
            return Response(
                {"detail": "email and otp are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cache_key  = _otp_key(email)
        cached_otp = OTP_CACHE.get(cache_key)

        if cached_otp is None:
            return Response(
                {"detail": "OTP has expired or was never issued. Please request a new one."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Constant-time comparison prevents timing attacks.
        if not hmac.compare_digest(str(cached_otp), str(otp_input)):
            return Response(
                {"detail": "Invalid OTP. Please try again."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Valid — delete OTP immediately (single-use).
        OTP_CACHE.delete(cache_key)

        # FIX 1 (BUG 2): Write a short-lived "email verified" gate key.
        # RegisterWizardView checks this key before creating a user — if it is
        # absent (OTP not completed or TTL expired), registration is rejected.
        # TTL is 10 minutes (VERIFIED_TTL) — long enough to finish the wizard.
        OTP_CACHE.set(_verified_key(email), "1", timeout=VERIFIED_TTL)

        logger.info("Pre-registration OTP verified for %s; verified gate key set (TTL=%ds)", email, VERIFIED_TTL)

        # Return verified=True + email so the frontend can store the verified address
        # and pre-fill it in the wizard. No User record is created here.
        return Response(
            {"verified": True, "email": email},
            status=status.HTTP_200_OK,
        )
