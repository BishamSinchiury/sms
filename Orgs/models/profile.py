"""
profile.py
----------
OrganizationProfile — public-facing school identity data.

This model holds everything shown on the org's public homepage:
    - School name, logo, motto/tagline
    - Contact details (address, phone, email, website)
    - A brief description / about section

Visibility:
    - ALL fields here are considered PUBLIC.
    - Served to the frontend for the org's public landing page.
    - Never mix sensitive/legal data here — that lives in OrganizationLegal.

Who manages it:
    - System admin via the Sys Dashboard.
    - Changes take effect immediately on the public page.

Public page content served from this model:
    ┌─────────────────────────────────────────┐
    │  [LOGO]   Greenwood High School         │
    │           "Excellence in Education"     │
    │                                         │
    │  📍 123 School Lane, Kathmandu          │
    │  📞 +977-1-234567                       │
    │  🌐 greenwood.edu                       │
    │                                         │
    │  [Login as Student/Teacher]             │
    │  [Login as Admin]                       │
    └─────────────────────────────────────────┘
"""

from django.db import models
from django.core.validators import URLValidator
from core.models import TimeStampedModel
from .organization import Organization


class SchoolType(models.TextChoices):
    PRE_PRIMARY  = "pre_primary",  "Pre-Primary"
    PRIMARY      = "primary",      "Primary"
    SECONDARY    = "secondary",    "Secondary"
    HIGHER_SEC   = "higher_sec",   "Higher Secondary"
    UNIVERSITY   = "university",   "University"
    VOCATIONAL   = "vocational",   "Vocational / Technical"
    OTHER        = "other",        "Other"


class OrganizationProfile(TimeStampedModel):
    """
    Public-facing profile for an organization.

    OneToOne with Organization — created automatically (with blank fields)
    when Organization is provisioned. System admin fills it in via Sys Dashboard.

    All fields are optional at DB level (blank=True) because the org is
    provisioned before the system admin has a chance to fill in details.
    The frontend should prompt the system admin to complete the profile
    on first login (profile_completion_percent property helps with this).
    """

    org = models.OneToOneField(
        Organization,
        on_delete=models.CASCADE,
        related_name="profile",
    )

    # ─────────────────────────────────────────────
    # Core Identity
    # ─────────────────────────────────────────────

    name = models.CharField(
        max_length=255,
        help_text="Full official name of the school. e.g. 'Greenwood High School'",
    )
    short_name = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Abbreviated name for display in tight spaces. e.g. 'GHS'",
    )
    school_type = models.CharField(
        max_length=20,
        choices=SchoolType.choices,
        blank=True,
        default="",
        help_text="The level/type of the institution.",
    )
    tagline = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Motto or tagline shown on the public page. e.g. 'Excellence in Education'",
    )
    description = models.TextField(
        blank=True,
        default="",
        help_text="Short about/description paragraph for the public landing page.",
    )
    established_year = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Year the school was founded. e.g. 1995",
    )

    # ─────────────────────────────────────────────
    # Branding
    # ─────────────────────────────────────────────

    logo = models.ImageField(
        upload_to="org_logos/%Y/",
        null=True,
        blank=True,
        help_text="School logo. Displayed on public page and dashboards.",
    )
    favicon = models.ImageField(
        upload_to="org_favicons/%Y/",
        null=True,
        blank=True,
        help_text="Browser tab icon for the org's hosted frontend.",
    )
    cover_image = models.ImageField(
        upload_to="org_covers/%Y/",
        null=True,
        blank=True,
        help_text="Hero/banner image shown on the public landing page.",
    )
    primary_color = models.CharField(
    max_length=7,
    blank=True,
    default="",
    help_text="Primary hex color code for org branding. e.g. '#1A3C6E'",
    )
    secondary_color = models.CharField(
        max_length=7,
        blank=True,
        default="",
        help_text="Secondary hex color code for org branding. e.g. '#F59E0B'",
    )

    # ─────────────────────────────────────────────
    # Physical Address
    # ─────────────────────────────────────────────

    address_line_1 = models.CharField(max_length=255, blank=True, default="")
    address_line_2 = models.CharField(max_length=255, blank=True, default="")
    city = models.CharField(max_length=100, blank=True, default="")
    state_province = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="State, province, or district.",
    )
    postal_code = models.CharField(max_length=20, blank=True, default="")
    country = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Country name or ISO 3166-1 alpha-2 code.",
    )

    # ─────────────────────────────────────────────
    # Contact Details
    # ─────────────────────────────────────────────

    phone_primary = models.CharField(
        max_length=30,
        blank=True,
        default="",
        help_text="Main contact phone number.",
    )
    phone_secondary = models.CharField(
        max_length=30,
        blank=True,
        default="",
        help_text="Secondary / alternate phone number.",
    )
    email_primary = models.EmailField(
        blank=True,
        default="",
        help_text="Main public contact email. e.g. info@greenwood.edu",
    )
    email_admissions = models.EmailField(
        blank=True,
        default="",
        help_text="Admissions-specific email (optional).",
    )
    website = models.URLField(
        blank=True,
        default="",
        validators=[URLValidator()],
        help_text="School's external website (if different from the platform domain).",
    )

    # ─────────────────────────────────────────────
    # Social Media
    # ─────────────────────────────────────────────

    facebook_url  = models.URLField(blank=True, default="")
    twitter_url   = models.URLField(blank=True, default="")
    instagram_url = models.URLField(blank=True, default="")
    linkedin_url  = models.URLField(blank=True, default="")
    youtube_url   = models.URLField(blank=True, default="")

    class Meta:
        app_label = "Orgs"
        db_table = "org_profiles"
        verbose_name = "Organization Profile"
        verbose_name_plural = "Organization Profiles"

    def __str__(self):
        return f"Profile: {self.name} ({self.org.slug})"

    # ─────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────

    @property
    def full_address(self) -> str:
        """Returns a single formatted address string."""
        parts = filter(None, [
            self.address_line_1,
            self.address_line_2,
            self.city,
            self.state_province,
            self.postal_code,
            self.country,
        ])
        return ", ".join(parts)

    @property
    def profile_completion_percent(self) -> int:
        """
        Returns a 0–100 score of how complete the profile is.
        Used in the sys dashboard to prompt system admin to fill in missing fields.
        """
        tracked_fields = [
            "name", "school_type", "tagline", "description",
            "logo", "address_line_1", "city", "country",
            "phone_primary", "email_primary", "website",
        ]
        filled = sum(1 for f in tracked_fields if getattr(self, f))
        return round((filled / len(tracked_fields)) * 100)

    def public_data(self) -> dict:
        """
        Returns only the fields safe to expose on the public landing page.
        Use this in the public-facing API serializer.
        """
        return {
            "name": self.name,
            "short_name": self.short_name,
            "tagline": self.tagline,
            "description": self.description,
            "school_type": self.school_type,
            "established_year": self.established_year,
            "logo": self.logo.url if self.logo else None,
            "cover_image": self.cover_image.url if self.cover_image else None,
            "favicon": self.favicon.url if self.favicon else None,
            "primary_color": self.primary_color,
            "address": self.full_address,
            "phone": self.phone_primary,
            "email": self.email_primary,
            "website": self.website,
            "social": {
                "facebook": self.facebook_url,
                "twitter": self.twitter_url,
                "instagram": self.instagram_url,
                "linkedin": self.linkedin_url,
                "youtube": self.youtube_url,
            },
        }
