"""
auth_session.py
---------------
Session tracking for system_admin users.

Why a custom session table (instead of Django's default sessions)?
    - System admin sessions need to be auditable (IP, user agent, last activity).
    - We want the ability to force-expire a specific session from the terminal.
    - Provides a clear audit trail for security-sensitive org management actions.

Django's default session engine stores data in django_session. This model sits
ALONGSIDE that — it stores metadata about system_admin sessions so they can be
listed, inspected, and revoked from the sys dashboard or terminal.

Flow:
    1. system_admin POSTs to /sys/auth/login/ with email + password
    2. Django authenticates via session (contrib.sessions + CSRF)
    3. SystemAdminSession record created with session_key reference
    4. On logout or timeout → session deleted + SystemAdminSession marked inactive
"""

from django.db import models
from core.models import TimeStampedModel
from .user import User
from Orgs.models import Organization


class SystemAdminSession(TimeStampedModel):
    """
    Audit record for each system_admin login session.

    The actual session data lives in Django's session backend (DB or Redis).
    This model stores metadata for auditing and forced revocation.
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="sys_admin_sessions",
    )
    org = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="sys_admin_sessions",
    )

    # Reference to Django's session — used for forced logout
    session_key = models.CharField(max_length=40, unique=True, db_index=True)

    # Audit metadata
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default="")
    last_activity = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    # Tracks forced revocations (e.g., super_user kills a session via terminal)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_reason = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        db_table = "system_admin_sessions"
        ordering = ["-created_at"]
        verbose_name = "System Admin Session"
        verbose_name_plural = "System Admin Sessions"
        indexes = [
            models.Index(fields=["user", "is_active"], name="idx_sysadmin_session_user"),
            models.Index(fields=["org", "is_active"],  name="idx_sysadmin_session_org"),
        ]

    def __str__(self):
        status = "active" if self.is_active else "revoked"
        return f"Session {self.session_key[:8]}… | {self.user.email} [{status}]"


class RefreshTokenRecord(TimeStampedModel):
    """
    Tracks issued JWT refresh tokens for admin and general users.

    Why track refresh tokens?
        - Enables logout (token blacklisting) without shared state in JWT.
        - Allows revoking ALL tokens for a user (e.g., on password change).
        - Provides audit trail of active sessions per user.

    On password change:
        - Increment user.password_changed_at
        - All refresh tokens with issued_at < password_changed_at are invalid

    Use djangorestframework-simplejwt's token blacklist app as the primary
    blacklist mechanism. This table is supplementary audit storage.
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="refresh_tokens",
    )
    jti = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text="JWT ID — unique identifier from the token payload.",
    )
    issued_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    is_revoked = models.BooleanField(default=False)

    # Device/client metadata for session listing
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default="")

    class Meta:
        db_table = "refresh_token_records"
        ordering = ["-issued_at"]
        verbose_name = "Refresh Token Record"
        verbose_name_plural = "Refresh Token Records"
        indexes = [
            models.Index(fields=["user", "is_revoked"], name="idx_refresh_token_user"),
            models.Index(fields=["expires_at"],          name="idx_refresh_token_expiry"),
        ]

    def __str__(self):
        status = "revoked" if self.is_revoked else "valid"
        return f"Token {self.jti[:8]}… | {self.user.email} [{status}]"
