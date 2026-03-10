"""
membership.py
-------------
OrgMembership — the heart of the permission system.

This is the JOIN table between User and Organization, and it carries:
    - The user's role in the org (via OrgRole FK)
    - The user's approval status (pending / active / suspended)
    - Whether this user is the system_admin of this org
    - Who approved them and when

Design principles:
    - A user's role is NEVER on the User model — it lives here.
    - One user → one org only (enforced by unique_together on user).
      This constraint is intentionally easy to relax later for multi-org support.
    - system_admin is a boolean flag here rather than a separate table —
      it keeps queries simple and the constraint (one system_admin per org) is
      enforced at the DB level via a partial unique index.

Approval flows:
    General user self-registers:
        → OrgMembership created with status=PENDING
        → system_admin OR admin user approves → status=ACTIVE

    Admin user created by system_admin:
        → OrgMembership created with status=ACTIVE directly (no approval step)

    System admin created via terminal:
        → OrgMembership created by management command with is_system_admin=True
"""

from django.db import models
from django.utils import timezone
from core.models import TimeStampedModel
from .user import User
from Orgs.models import Organization
from .roles import OrgRole


class MembershipStatus(models.TextChoices):
    PENDING   = "pending",   "Pending Approval"
    ACTIVE    = "active",    "Active"
    SUSPENDED = "suspended", "Suspended"
    REJECTED  = "rejected",  "Rejected"


class OrgMembership(TimeStampedModel):
    """
    Links a User to an Organization with a Role and approval status.

    Key constraints:
        - unique on `user` alone → one user, one org (relax later for multi-org)
        - unique on (org, is_system_admin=True) → only one system_admin per org
          (enforced via partial unique index in migration)

    Auth note:
        - system_admin (is_system_admin=True) → session auth (separate login path)
        - admin role (role.name == 'admin') → JWT auth (standard API path)
        - general users → JWT auth (standard API path)
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="membership",
        help_text="OneToOne enforces one-org-per-user. Change to ForeignKey when scaling.",
    )
    org = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.ForeignKey(
        OrgRole,
        on_delete=models.PROTECT,
        related_name="memberships",
        help_text="The user's role within this org. Must belong to the same org.",
    )

    status = models.CharField(
        max_length=20,
        choices=MembershipStatus.choices,
        default=MembershipStatus.PENDING,
        db_index=True,
    )

    is_system_admin = models.BooleanField(
        default=False,
        help_text="True only for the org's designated system admin. "
                  "Only one per org (enforced by partial unique index).",
    )

    # Audit trail
    approved_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approvals_given",
        help_text="The user (admin or system_admin) who approved this membership.",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, default="")

    class Meta:
        db_table = "org_memberships"
        verbose_name = "Org Membership"
        verbose_name_plural = "Org Memberships"
        indexes = [
            models.Index(fields=["org", "status"], name="idx_membership_org_status"),
            models.Index(fields=["org", "role"],   name="idx_membership_org_role"),
        ]
        # NOTE: Add this partial unique index in your migration manually:
        # CREATE UNIQUE INDEX uq_one_sysadmin_per_org
        #   ON org_memberships (org_id)
        #   WHERE is_system_admin = TRUE;
        constraints = [
            models.UniqueConstraint(
                fields=["org"],
                condition=models.Q(is_system_admin=True),
                name="uq_one_sysadmin_per_org",
            )
        ]

    def __str__(self):
        return f"{self.user.email} @ {self.org.slug} [{self.role.name}] ({self.status})"

    # ─────────────────────────────────────────────
    # Convenience helpers
    # ─────────────────────────────────────────────

    def approve(self, approved_by_user):
        """Activate a pending membership. Call this from the approval view."""
        self.status = MembershipStatus.ACTIVE
        self.approved_by = approved_by_user
        self.approved_at = timezone.now()
        self.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])

    def reject(self, rejected_by_user, reason=""):
        """Reject a pending membership."""
        self.status = MembershipStatus.REJECTED
        self.approved_by = rejected_by_user
        self.approved_at = timezone.now()
        self.rejection_reason = reason
        self.save(update_fields=[
            "status", "approved_by", "approved_at", "rejection_reason", "updated_at"
        ])

    def suspend(self):
        """Suspend an active membership."""
        self.status = MembershipStatus.SUSPENDED
        self.save(update_fields=["status", "updated_at"])

    @property
    def is_active(self):
        return self.status == MembershipStatus.ACTIVE

    @property
    def is_pending(self):
        return self.status == MembershipStatus.PENDING

    def has_permission(self, module: str, action: str) -> bool:
        """
        Check if this membership's role grants a specific module+action permission.
        Cache this result in the request cycle (e.g., via middleware) for performance.
        """
        return self.role.permissions.filter(
            module=module,
            action=action,
            allowed=True,
        ).exists()

    def has_feature(self, flag_key: str) -> bool:
        """Check if a feature flag is enabled for this membership's role."""
        return self.role.feature_flags.filter(
            flag_key=flag_key,
            enabled=True,
        ).exists()
