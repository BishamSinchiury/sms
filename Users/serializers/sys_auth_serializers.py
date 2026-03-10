"""
sys_auth_serializers.py
-----------------------
Serializers for the System Admin two-step authentication flow.

Step 1 — Login:
    Input:  { email, password }
    Output: { detail }   (OTP dispatched; no tokens revealed here)

Step 2 — OTP Verify:
    Input:  { email, otp }
    Output: { detail, user: { id, email, full_name, org_slug } }
            (Django session is created server-side; no body token)
"""

from rest_framework import serializers


# ─────────────────────────────────────────────────────────────
# Step 1 — Credential serializer
# ─────────────────────────────────────────────────────────────

class SysAdminLoginSerializer(serializers.Serializer):
    """
    Validates the initial email + password pair.
    Does NOT mutate state — all auth logic lives in the view.
    """
    email    = serializers.EmailField()
    password = serializers.CharField(
        write_only=True,
        style={"input_type": "password"},
    )


# ─────────────────────────────────────────────────────────────
# Step 2 — OTP verification serializer
# ─────────────────────────────────────────────────────────────

class SysAdminOTPVerifySerializer(serializers.Serializer):
    """
    Validates the OTP that was cached in Redis after step 1.
    The email is required again to look up the cached OTP key.
    """
    email = serializers.EmailField()
    otp   = serializers.CharField(
        min_length=6,
        max_length=6,
        help_text="6-digit one-time password sent/displayed after login.",
    )
