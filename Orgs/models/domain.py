"""
domain.py
---------
Per-organization domain registry.

Each org has one PRIMARY domain and zero or more ALIAS domains.
Domain-based auth works by:
    1. Request comes in to greenwood.edu/login
    2. Backend extracts host from request.get_host()
    3. Looks up OrgDomain → finds Organization
    4. Auth proceeds only if user belongs to THAT org

This completely prevents cross-org credential reuse — a system admin
from School A cannot log in at School B's domain even with valid credentials.

Domain rules:
    - Exactly ONE domain per org can have is_primary=True
      (enforced by partial unique index)
    - Aliases are useful for: www. prefix, old domains during migration,
      custom subdomains (e.g. app.greenwood.edu alongside greenwood.edu)
    - All domains must be globally unique across the platform
      (one domain cannot point to two orgs)
    - Domains are verified by super_user — unverified domains are registered
      but not yet used for auth routing
"""

from django.db import models
from core.models import TimeStampedModel
from .organization import Organization


class OrgDomain(TimeStampedModel):
    """
    A domain name associated with an organization.

    Auth middleware lookup:
        org = OrgDomain.objects.select_related("org").get(
            domain=request.get_host(),
            is_verified=True,
            org__is_active=True,
        ).org

    Primary domain:
        - Used as the canonical URL for the org's public page and dashboard.
        - Shown in the sys dashboard and org profile.
        - Only one primary per org (DB-enforced via UniqueConstraint + condition).

    Alias domains:
        - Redirect to primary OR serve the same content.
        - Useful during domain migrations or for www/non-www variants.
    """

    org = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="domains",
    )
    domain = models.CharField(
        max_length=253,  # max DNS name length per RFC 1035
        unique=True,     # globally unique — one domain, one org, always
        db_index=True,
        help_text=(
            "Full domain name without protocol or trailing slash. "
            "e.g. 'greenwood.edu' or 'app.greenwood.edu'"
        ),
    )
    is_primary = models.BooleanField(
        default=False,
        help_text=(
            "Only one domain per org can be primary. "
            "Enforced by DB partial unique index."
        ),
    )
    is_verified = models.BooleanField(
        default=False,
        help_text=(
            "Super user marks as verified after DNS confirmation. "
            "Unverified domains are NOT used for auth routing."
        ),
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(
        blank=True,
        default="",
        help_text="Internal notes. e.g. 'Old domain — alias until March 2026'",
    )

    class Meta:
        app_label = "Orgs"
        db_table = "org_domains"
        verbose_name = "Org Domain"
        verbose_name_plural = "Org Domains"
        constraints = [
            # Exactly one primary domain per org at the DB level
            models.UniqueConstraint(
                fields=["org"],
                condition=models.Q(is_primary=True),
                name="uq_one_primary_domain_per_org",
            )
        ]
        indexes = [
            models.Index(fields=["domain", "is_verified"], name="idx_domain_verified"),
        ]

    def __str__(self):
        tag = "PRIMARY" if self.is_primary else "alias"
        verified = "✓" if self.is_verified else "unverified"
        return f"{self.domain} [{tag}] [{verified}] → {self.org.slug}"

    @classmethod
    def resolve_org(cls, domain: str):
        """
        Resolve a domain string to its Organization.
        Returns None if domain is unknown, unverified, or org is inactive.

        Usage in auth middleware:
            org = OrgDomain.resolve_org(request.get_host())
            if org is None:
                return HttpResponse(status=404)
        """
        try:
            return cls.objects.select_related("org").get(
                domain=domain,
                is_verified=True,
                org__is_active=True,
            ).org
        except cls.DoesNotExist:
            return None
