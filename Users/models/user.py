"""
user.py
-------
Core User model — stores identity ONLY.
Role is NEVER stored here. It lives on OrgMembership.

User types are determined by:
    - super_user   → SuperUser table (terminal-seeded, no HTTP login)
    - system_admin → OrgMembership with is_system_admin=True
    - admin        → OrgMembership linked to an OrgRole with is_admin_role=True
    - general user → OrgMembership linked to any other OrgRole

Auth strategy:
    - system_admin → session-based (handled in views/middleware, not here)
    - admin + general → JWT (djangorestframework-simplejwt)
    - super_user   → terminal only, no login endpoint
"""

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from core.models import TimeStampedModel


class UserManager(BaseUserManager):
    """Custom manager — email is the unique identifier, not username."""

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email address is required.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """
        Django's built-in superuser — only used for manage.py shell/admin.
        Not the same as the platform's super_user concept.
        """
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin, TimeStampedModel):
    """
    Platform user — identity record only.

    What this model does NOT store:
        - Role (lives on OrgMembership)
        - Organization (lives on OrgMembership)
        - Permissions (live on RolePermission)

    Registration flow:
        - General users self-register → status 'pending' on OrgMembership
        - Admin users are created & assigned by system_admin
        - System admins are created via terminal management command
    """

    email = models.EmailField(unique=True, db_index=True)
    first_name = models.CharField(max_length=150, blank=True, default="")
    last_name = models.CharField(max_length=150, blank=True, default="")
    phone_number = models.CharField(max_length=20, blank=True, default="", help_text="Contact phone number.")

    is_active = models.BooleanField(
        default=True,
        help_text="Designates whether this user account is active. "
                  "Deactivate instead of deleting.",
    )
    is_staff = models.BooleanField(
        default=False,
        help_text="Django admin access only. Not related to platform roles.",
    )

    # Tracks the last time a password was changed — used for JWT invalidation
    password_changed_at = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []  # email + password only at creation

    class Meta:
        db_table = "users"
        ordering = ["email"]
        verbose_name = "User"
        verbose_name_plural = "Users"

    def __str__(self):
        return self.email

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.email

    def get_membership(self):
        """
        Returns this user's single OrgMembership or None.
        Super users have no membership.
        """
        return getattr(self, "membership", None)


class SuperUser(TimeStampedModel):
    """
    Marks a User record as the platform super_user.

    Rules:
        - Created ONLY via management command (terminal). No HTTP endpoint.
        - No membership to any org.
        - Has full read/write access to everything via terminal & Django admin.
        - Never exposed through the public API.

    There should typically be only 1–2 records here (platform owners/devs).
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="super_user_profile",
    )
    notes = models.TextField(
        blank=True,
        default="",
        help_text="Internal notes about this super user (e.g., 'Lead developer').",
    )

    class Meta:
        db_table = "super_users"
        verbose_name = "Super User"
        verbose_name_plural = "Super Users"

    def __str__(self):
        return f"SuperUser: {self.user.email}"
