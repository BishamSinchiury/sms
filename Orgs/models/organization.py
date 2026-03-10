"""
organization.py
---------------
The anchor/tenant record for each organization.

Design principles:
    - Stays intentionally lean — just enough to identify and activate a tenant.
    - Everything else (profile, legal, domains) lives in related models.
    - All other apps (accounts, academic, etc.) FK to this model.
    - Created ONLY by super_user via terminal management command.
    - Never created through any HTTP endpoint.

Relationship map:
    Organization
        ├── OrganizationDomain    (one primary + optional aliases)
        ├── OrganizationProfile   (public-facing info)
        ├── OrganizationLegal     (private legal & accreditation info)
        └── [accounts] OrgMembership, OrgRole, etc. (FK from accounts app)
"""

from django.db import models
from core.models import TimeStampedModel

class Organization(TimeStampedModel):
    """
    Tenant anchor record. One row = one school on the platform.

    This model is the single source of truth for tenant identity.
    All cross-app relationships point here.

    Lifecycle:
        1. Super user runs: python manage.py create_org --slug "greenwood-high"
        2. Management command creates Organization + seeds 3 system OrgRoles
        3. System admin is then assigned via: python manage.py create_system_admin
        4. System admin fills in OrganizationProfile + OrganizationLegal via Sys Dashboard
    """

    slug = models.SlugField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text=(
            "Immutable URL-safe identifier. Set at creation, never changed. "
            "e.g. 'greenwood-high'. Used internally to reference the org."
        ),
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text=(
            "Master switch for the org. When False: all logins blocked, "
            "API access denied, public page returns 503."
        ),
    )

    # Soft-deletion support — deactivated orgs are never hard-deleted
    deactivated_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set when is_active is toggled to False. Auditing purposes.",
    )
    deactivation_reason = models.TextField(
        blank=True,
        default="",
        help_text="Reason recorded by super_user when deactivating.",
    )

    class Meta:
        app_label = "Orgs"
        db_table = "organizations"
        ordering = ["slug"]
        verbose_name = "Organization"
        verbose_name_plural = "Organizations"

    def __str__(self):
        return self.slug

    # ─────────────────────────────────────────────
    # Convenience accessors
    # ─────────────────────────────────────────────

    @property
    def name(self):
        """Shortcut to profile name — avoids joins in templates."""
        return getattr(self, "_profile_cache_name", None) or (
            self.profile.name if hasattr(self, "profile") else self.slug
        )

    @property
    def primary_domain(self):
        """Returns the primary OrgDomain instance for this org."""
        return self.domains.filter(is_primary=True).first()

    def get_domain_list(self):
        """Returns all domain strings for this org (primary first)."""
        return list(
            self.domains.order_by("-is_primary").values_list("domain", flat=True)
        )
