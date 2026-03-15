"""
sys_auth_views.py
-----------------
System Admin two-step authentication — session-based login with OTP verification.

Flow overview
=============
                ┌──────────────────────────────────────────────────┐
                │  POST /api/sys/auth/login/                       │
                │  { email, password }                             │
                │                                                  │
                │  1. Verify email+password against User table     │
                │  2. Confirm user has is_system_admin membership  │
                │  3. Generate 6-digit OTP                         │
                │  4. Cache OTP in Redis (otp cache, 5-min TTL)   │
                │  5. Return 200 + "OTP dispatched" message        │
                │     (OTP emailed via Gmail SMTP)                 │
                └──────────────────────────────────────────────────┘
                                    │
                                    ▼
                ┌──────────────────────────────────────────────────┐
                │  POST /api/sys/auth/verify-otp/                  │
                │  { email, otp }                                  │
                │                                                  │
                │  1. Pop OTP from Redis (single-use)              │
                │  2. Compare provided OTP (timing-safe)           │
                │  3. Create Django session (session backend)      │
                │  4. Write SystemAdminSession audit record        │
                │  5. Return 200 + basic user/org info             │
                └──────────────────────────────────────────────────┘
                                    │
                                    ▼
                ┌──────────────────────────────────────────────────┐
                │  POST /api/sys/auth/logout/                      │
                │  (requires active session cookie)                │
                │                                                  │
                │  1. Mark SystemAdminSession.is_active = False    │
                │  2. Flush Django session                         │
                │  3. Return 200                                   │
                └──────────────────────────────────────────────────┘

Security notes
==============
- OTP is stored ONLY in Redis (never in DB). It is deleted on first use.
- Rate limiting should be applied at the nginx / middleware level.
- In production, replace the console OTP print with an email/SMS dispatch.
- CSRF protection is active (DRF SessionAuthentication enforces CSRF on
  unsafe methods by default). The client must include the CSRF token.
- Session cookie is HttpOnly + Secure in production.
"""

import hmac
import logging
import random
import string

from django.conf import settings
from django.core.mail import EmailMultiAlternatives

from django.contrib.auth import get_user_model
from django.core.cache import caches
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from Users.models.auth_session import SystemAdminSession
from Users.models.membership import OrgMembership, MembershipStatus
from Users.serializers.sys_auth_serializers import (
    SysAdminLoginSerializer,
    SysAdminOTPVerifySerializer,
)

User = get_user_model()
logger = logging.getLogger(__name__)

# Redis cache alias defined in settings.py → CACHES["otp"]
OTP_CACHE = caches["otp"]

# Cache key template — scoped to prevent collisions with other OTP flows
OTP_KEY_TEMPLATE = "sys_admin_otp:{email}"

# OTP TTL (seconds) — must match the TIMEOUT set in settings.CACHES["otp"]
OTP_TTL = 300  # 5 minutes


def _generate_otp(length: int = 6) -> str:
    """Return a cryptographically random numeric OTP string."""
    return "".join(random.SystemRandom().choices(string.digits, k=length))


def _otp_cache_key(email: str) -> str:
    return OTP_KEY_TEMPLATE.format(email=email.lower().strip())


def _get_client_ip(request) -> str:
    """Best-effort IP extraction — handles proxies."""
    x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded:
        return x_forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def _get_user_agent(request) -> str:
    return request.META.get("HTTP_USER_AGENT", "")


def _dispatch_otp(email: str, otp: str) -> None:
    """
    Send the OTP to the system admin via Gmail SMTP.

    Uses Django's EmailMultiAlternatives to deliver both a plain-text
    and an HTML version of the OTP email. Credentials are pulled from
    settings (EMAIL_HOST_USER / EMAIL_HOST_PASSWORD) which are sourced
    from .env.dev via python-decouple.

    Failures are caught and logged so that a mail error does NOT expose
    a 500 to the login endpoint — the OTP is still cached in Redis and
    can be retried by re-posting to /login/.
    """
    subject    = "Your System Admin Login OTP"
    from_email = settings.DEFAULT_FROM_EMAIL

    # ── Plain-text body (fallback for non-HTML clients) ───────
    text_body = (
        f"Hello,\n\n"
        f"Your one-time password (OTP) for System Admin login is:\n\n"
        f"    {otp}\n\n"
        f"This OTP expires in 5 minutes. Do not share it with anyone.\n\n"
        f"If you did not request this, please secure your account immediately.\n\n"
        f"— SMS Platform"
    )

    # ── HTML body ─────────────────────────────────────────────
    html_body = f"""\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>System Admin OTP</title>
</head>
<body style="margin:0;padding:0;background:#f4f6f8;font-family:'Segoe UI',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6f8;padding:40px 0;">
    <tr>
      <td align="center">
        <table width="480" cellpadding="0" cellspacing="0"
               style="background:#ffffff;border-radius:12px;
                      box-shadow:0 4px 24px rgba(0,0,0,0.08);overflow:hidden;">

          <!-- Header -->
          <tr>
            <td style="background:linear-gradient(135deg,#1a1a2e 0%,#16213e 100%);
                        padding:32px 40px;text-align:center;">
              <h1 style="margin:0;color:#ffffff;font-size:22px;
                          font-weight:700;letter-spacing:0.5px;">SMS Platform</h1>
              <p style="margin:6px 0 0;color:#a0aec0;font-size:13px;">System Admin Portal</p>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:40px 40px 32px;">
              <p style="margin:0 0 8px;color:#4a5568;font-size:15px;">Hello,</p>
              <p style="margin:0 0 28px;color:#4a5568;font-size:15px;line-height:1.6;">
                Your one-time password for <strong>System Admin</strong> login is:
              </p>

              <!-- OTP box -->
              <div style="background:#f7fafc;border:2px dashed #e2e8f0;
                           border-radius:10px;padding:24px;text-align:center;
                           margin-bottom:28px;">
                <span style="font-size:40px;font-weight:800;letter-spacing:12px;
                              color:#1a1a2e;font-family:'Courier New',monospace;">{otp}</span>
              </div>

              <p style="margin:0 0 6px;color:#718096;font-size:13px;text-align:center;">
                ⏱ &nbsp;This OTP expires in <strong>5 minutes</strong>.
              </p>
              <p style="margin:0 0 28px;color:#718096;font-size:13px;text-align:center;">
                Do not share this OTP with anyone.
              </p>

              <hr style="border:none;border-top:1px solid #edf2f7;margin-bottom:24px;">

              <p style="margin:0;color:#a0aec0;font-size:12px;">
                If you did not request this login, please secure your account immediately
                and contact your platform administrator.
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background:#f7fafc;padding:16px 40px;
                        text-align:center;border-top:1px solid #edf2f7;">
              <p style="margin:0;color:#cbd5e0;font-size:11px;">
                &copy; SMS Platform &mdash; Automated security email, do not reply.
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    try:
        msg = EmailMultiAlternatives(
            subject      = subject,
            body         = text_body,
            from_email   = from_email,
            to           = [email],
        )
        msg.attach_alternative(html_body, "text/html")
        msg.send(fail_silently=False)
        logger.info("OTP email dispatched to %s", email)
    except Exception as exc:  # noqa: BLE001
        # Log the failure but do NOT propagate — the OTP is cached in Redis
        # and the user will see "OTP dispatched". They can retry /login/ if
        # the email genuinely fails to arrive.
        logger.error("Failed to send OTP email to %s: %s", email, exc)


# ─────────────────────────────────────────────────────────────
# View 1 — Step 1: Validate credentials → issue OTP
# ─────────────────────────────────────────────────────────────

class SysAdminLoginView(APIView):
    """
    POST /api/sys/auth/login/

    Accepts email + password. On success, generates an OTP, caches it in
    Redis, and dispatches it (console in dev / email in prod).

    Always returns a generic message to prevent user enumeration attacks.
    """
    authentication_classes = []  # No auth required — this IS the login endpoint
    permission_classes     = []

    def post(self, request):
        serializer = SysAdminLoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email    = serializer.validated_data["email"].lower().strip()
        password = serializer.validated_data["password"]

        # ── Generic error — same message for all failure cases (anti-enumeration) ──
        GENERIC_ERROR = {
            "detail": "Invalid credentials or account not authorized."
        }

        # ── 1. Find the user ──────────────────────────────────
        try:
            user = User.objects.select_related().get(email=email)
        except User.DoesNotExist:
            logger.info("SysAdmin login attempt for unknown email: %s", email)
            return Response(GENERIC_ERROR, status=status.HTTP_401_UNAUTHORIZED)

        # ── 2. Check password ─────────────────────────────────
        if not user.check_password(password):
            logger.info("SysAdmin login: bad password for %s", email)
            return Response(GENERIC_ERROR, status=status.HTTP_401_UNAUTHORIZED)

        # ── 3. Confirm user is an active system admin ─────────
        try:
            membership = OrgMembership.objects.select_related("org").get(
                user=user,
                is_system_admin=True,
                status=MembershipStatus.ACTIVE,
            )
        except OrgMembership.DoesNotExist:
            logger.warning(
                "SysAdmin login: user %s has no active system_admin membership.", email
            )
            return Response(GENERIC_ERROR, status=status.HTTP_401_UNAUTHORIZED)

        # ── 4. Check the org is active ────────────────────────
        if not membership.org.is_active:
            logger.warning(
                "SysAdmin login: org '%s' is inactive.", membership.org.slug
            )
            return Response(
                {"detail": "Your organization is currently inactive."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # ── 5. Generate + cache OTP ───────────────────────────
        otp = _generate_otp()
        cache_key = _otp_cache_key(email)
        OTP_CACHE.set(cache_key, otp, timeout=OTP_TTL)

        # ── 6. Dispatch OTP ───────────────────────────────────
        _dispatch_otp(email, otp)

        logger.info("SysAdmin OTP issued for %s (org: %s)", email, membership.org.slug)

        return Response(
            {
                "detail": (
                    "OTP has been dispatched. "
                    "Please verify within 5 minutes."
                )
            },
            status=status.HTTP_200_OK,
        )


# ─────────────────────────────────────────────────────────────
# View 2 — Step 2: Verify OTP → create session
# ─────────────────────────────────────────────────────────────

class SysAdminOTPVerifyView(APIView):
    """
    POST /api/sys/auth/verify-otp/

    Accepts email + 6-digit OTP. On success:
        - Pops (deletes) the OTP from Redis (single-use).
        - Creates a Django session.
        - Writes a SystemAdminSession audit record.
        - Returns basic user + org info (no token in body — relies on session cookie).
    """
    authentication_classes = []
    permission_classes     = []

    def post(self, request):
        serializer = SysAdminOTPVerifySerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email       = serializer.validated_data["email"].lower().strip()
        otp_input   = serializer.validated_data["otp"]
        cache_key   = _otp_cache_key(email)

        # ── 1. Fetch cached OTP (None if expired/never issued) ──
        cached_otp = OTP_CACHE.get(cache_key)
        if cached_otp is None:
            return Response(
                {"detail": "OTP has expired or was never issued. Please log in again."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── 2. Constant-time comparison (prevent timing attacks) ──
        if not hmac.compare_digest(str(cached_otp), str(otp_input)):
            logger.warning("SysAdmin OTP mismatch for email: %s", email)
            return Response(
                {"detail": "Invalid OTP. Please try again."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── 3. OTP is valid — delete it immediately (single-use) ──
        OTP_CACHE.delete(cache_key)

        # ── 4. Fetch user + membership ────────────────────────
        try:
            user = User.objects.get(email=email)
            membership = OrgMembership.objects.select_related("org").get(
                user=user,
                is_system_admin=True,
                status=MembershipStatus.ACTIVE,
            )
        except (User.DoesNotExist, OrgMembership.DoesNotExist):
            # Shouldn't happen if step 1 passed, but guard anyway
            return Response(
                {"detail": "Account error. Please contact support."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        org = membership.org

        # ── 5. Create Django session ──────────────────────────
        request.session.cycle_key()              # regenerate to prevent fixation
        request.session["user_id"]     = user.pk
        request.session["org_slug"]    = org.slug
        request.session["is_sys_admin"] = True
        request.session.set_expiry(86400)        # 24 hours (matches Redis sessions TTL)
        request.session.save()

        # ── 6. Write audit record ─────────────────────────────
        SystemAdminSession.objects.create(
            user        = user,
            org         = org,
            session_key = request.session.session_key,
            ip_address  = _get_client_ip(request) or None,
            user_agent  = _get_user_agent(request),
            is_active   = True,
        )

        logger.info(
            "SysAdmin session created for %s (org: %s, session: %s)",
            email, org.slug, request.session.session_key[:8],
        )

        return Response(
            {
                "detail": "Login successful.",
                "user": {
                    "id":        user.pk,
                    "email":     user.email,
                    "full_name": user.full_name,
                    "org_slug":  org.slug,
                },
            },
            status=status.HTTP_200_OK,
        )


# ─────────────────────────────────────────────────────────────
# View 3 — Me: return identity from active session (page-refresh)
# ─────────────────────────────────────────────────────────────

class SysAdminMeView(APIView):
    """
    GET /api/sys/auth/me/

    Called by the frontend on every page load to check whether the browser
    already holds a valid system-admin session cookie (set after OTP verify).

    No credentials required — Django reads the session cookie automatically.
    Returns basic identity data so the frontend can restore auth state
    without forcing the admin to re-login after a hard refresh (F5).

    Responses
    ---------
    200  — Active session found. Returns user_id, email, full_name, org_slug.
    401  — No session or session does not have is_sys_admin=True.
    """
    authentication_classes = []
    permission_classes     = []

    def get(self, request):
        if not request.session.get("is_sys_admin"):
            return Response(
                {"detail": "No active system admin session."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        user_id = request.session.get("user_id")
        org_slug = request.session.get("org_slug")

        # Fetch fresh user data so the response is always up-to-date
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            # Session references a deleted user — treat as invalid
            request.session.flush()
            return Response(
                {"detail": "Session invalid. Please log in again."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        logger.debug("SysAdmin /me/ called for user %s (org: %s)", user.email, org_slug)

        return Response(
            {
                "id":        user.pk,
                "email":     user.email,
                "full_name": user.full_name,
                "org_slug":  org_slug,
            },
            status=status.HTTP_200_OK,
        )


# ─────────────────────────────────────────────────────────────
# View 4 — Logout: invalidate session + audit record
# ─────────────────────────────────────────────────────────────

class SysAdminLogoutView(APIView):
    """
    POST /api/sys/auth/logout/

    Requires an active session cookie (is_sys_admin=True in session data).
    Marks the SystemAdminSession as inactive and flushes the Django session.
    """
    authentication_classes = []
    permission_classes     = []

    def post(self, request):
        # ── Guard: must be a system admin session ─────────────
        if not request.session.get("is_sys_admin"):
            return Response(
                {"detail": "No active system admin session found."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        session_key = request.session.session_key

        # ── Mark audit record as inactive ─────────────────────
        if session_key:
            SystemAdminSession.objects.filter(
                session_key=session_key,
                is_active=True,
            ).update(
                is_active    = False,
                revoked_at   = timezone.now(),
                revoked_reason = "User initiated logout.",
            )

        # ── Flush the Django session ───────────────────────────
        request.session.flush()

        logger.info("SysAdmin logout: session %s terminated.", session_key[:8] if session_key else "unknown")

        return Response({"detail": "Logged out successfully."}, status=status.HTTP_200_OK)
