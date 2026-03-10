"""
roles.py
--------
Dynamic, per-organization role system.

Design decisions:
    - Roles are created per org by the system_admin.
    - Three roles are system-reserved and auto-created per org:
        * SYSTEM_ADMIN_ROLE  — locked, one user max
        * ADMIN_ROLE         — locked name, system_admin can assign users
        * MEMBER_ROLE        — base fallback role (no special permissions)
    - All other roles (e.g., "Teacher", "Student") are custom, created by system_admin.
    - Permissions are toggled per role, per module, per action.
    - Feature flags are also per role — enables/disables UI features for that role.
"""

from django.db import models
from core.models import TimeStampedModel
from Orgs.models import Organization


# ─────────────────────────────────────────────
# Choices & Constants
# ─────────────────────────────────────────────

class PermissionAction(models.TextChoices):
    VIEW   = "view",   "View"
    CREATE = "create", "Create"
    EDIT   = "edit",   "Edit"
    DELETE = "delete", "Delete"
    EXPORT = "export", "Export"


SYSTEM_ADMIN_ROLE = "system_admin"
ADMIN_ROLE        = "admin"
MEMBER_ROLE       = "member"

SYSTEM_RESERVED_ROLES = {SYSTEM_ADMIN_ROLE, ADMIN_ROLE, MEMBER_ROLE}


# ─────────────────────────────────────────────
# OrgRole
# ─────────────────────────────────────────────

class OrgRole(TimeStampedModel):
    """
    A named role within an organization.

    System roles (is_system_role=True) are created automatically when
    an org is provisioned and cannot be renamed or deleted.

    Custom roles (e.g. "Teacher", "Lab Assistant") are created and
    managed by system_admin via the sys dashboard.
    """

    org = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="roles",
    )
    name = models.CharField(
        max_length=100,
        help_text="Human-readable role name. e.g. 'Teacher', 'Student', 'admin'",
    )
    is_system_role = models.BooleanField(
        default=False,
        help_text="System roles are locked — cannot be renamed or deleted.",
    )
    description = models.TextField(blank=True, default="")

    class Meta:
        db_table = "org_roles"
        unique_together = [("org", "name")]
        verbose_name = "Org Role"
        verbose_name_plural = "Org Roles"

    def __str__(self):
        return f"{self.org.slug} › {self.name}"

    @property
    def is_admin_role(self):
        return self.name == ADMIN_ROLE

    @property
    def is_system_admin_role(self):
        return self.name == SYSTEM_ADMIN_ROLE

    def can_be_deleted(self):
        return not self.is_system_role


# ─────────────────────────────────────────────
# RolePermission
# ─────────────────────────────────────────────

class RolePermission(TimeStampedModel):
    """
    Granular permission entry — one row per (role, module, action) combination.

    Adding a new module to the platform only requires inserting rows here.
    No schema changes needed.

    Example modules: 'attendance', 'grades', 'reports', 'timetable', 'finance'
    Example actions: 'view', 'create', 'edit', 'delete', 'export'
    """

    role = models.ForeignKey(
        OrgRole,
        on_delete=models.CASCADE,
        related_name="permissions",
    )
    module = models.CharField(
        max_length=100,
        help_text="Module/section identifier. e.g. 'attendance', 'gradebook'",
    )
    action = models.CharField(
        max_length=50,
        choices=PermissionAction.choices,
    )
    allowed = models.BooleanField(default=False)

    class Meta:
        db_table = "role_permissions"
        unique_together = [("role", "module", "action")]
        verbose_name = "Role Permission"
        verbose_name_plural = "Role Permissions"
        indexes = [
            models.Index(fields=["role", "module"], name="idx_role_module"),
        ]

    def __str__(self):
        status = "✓" if self.allowed else "✗"
        return f"{self.role} | {self.module}.{self.action} [{status}]"


# ─────────────────────────────────────────────
# FeatureFlag
# ─────────────────────────────────────────────

class FeatureFlag(TimeStampedModel):
    """
    Per-role feature toggles within an org.

    Use cases:
        - Beta features rolled out to specific roles only
        - UI module visibility (e.g., new gradebook UI for teachers only)
        - Experimental features gated per role

    Platform-wide flags are set via super_user terminal scripts.
    Org-level flags (per role) are managed by system_admin via the sys dashboard.
    """

    role = models.ForeignKey(
        OrgRole,
        on_delete=models.CASCADE,
        related_name="feature_flags",
    )
    flag_key = models.CharField(
        max_length=100,
        help_text="Snake_case key. e.g. 'beta_gradebook', 'new_attendance_ui'",
    )
    enabled = models.BooleanField(default=False)
    description = models.TextField(
        blank=True,
        default="",
        help_text="Internal description of what this flag controls.",
    )

    class Meta:
        db_table = "feature_flags"
        unique_together = [("role", "flag_key")]
        verbose_name = "Feature Flag"
        verbose_name_plural = "Feature Flags"

    def __str__(self):
        status = "ON" if self.enabled else "OFF"
        return f"{self.role} | {self.flag_key} [{status}]"
