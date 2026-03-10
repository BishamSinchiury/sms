"""
legal.py
--------
OrganizationLegal — private legal, registration, and accreditation data.

This model is NEVER exposed publicly. It is:
    - Only accessible via the Sys Dashboard (system_admin)
    - Never included in public API serializers
    - Stored separately from OrganizationProfile intentionally

Contains:
    1. Owner Identity     — who legally owns/operates the school
    2. Registration       — government registration details
    3. Tax                — VAT / tax identification
    4. Accreditation      — academic accreditation body details

Security note:
    - Fields like owner_id_number should be encrypted at rest in production.
      Consider django-fernet-fields or pgcrypto for these columns.
    - Document uploads (registration_document, accreditation_document)
      must be stored in a private media bucket (not public S3/CDN).
    - Access to this model's API endpoints must be gated behind
      is_system_admin=True checks — never expose to admin or general users.
"""

from django.db import models
from django.core.validators import FileExtensionValidator
from core.models import TimeStampedModel
from .organization import Organization


def legal_document_path(instance, filename):
    """Private upload path scoped to org slug — never served publicly."""
    return f"private/orgs/{instance.org.slug}/legal/{filename}"


def accreditation_document_path(instance, filename):
    return f"private/orgs/{instance.org.slug}/accreditation/{filename}"


class AccreditationStatus(models.TextChoices):
    ACCREDITED     = "accredited",     "Accredited"
    PENDING        = "pending",        "Pending"
    EXPIRED        = "expired",        "Expired"
    NOT_APPLICABLE = "not_applicable", "Not Applicable"


class OrganizationLegal(TimeStampedModel):
    """
    Private legal and compliance data for an organization.

    OneToOne with Organization — auto-created alongside OrganizationProfile
    when the org is provisioned. System admin fills it in via Sys Dashboard.

    IMPORTANT: This model must never be included in public-facing serializers.
    Always use explicit field whitelisting in any serializer that touches this.
    """

    org = models.OneToOneField(
        Organization,
        on_delete=models.CASCADE,
        related_name="legal",
    )

    # ─────────────────────────────────────────────
    # Owner / Principal Identity
    # ─────────────────────────────────────────────

    owner_full_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Full legal name of the school owner or principal.",
    )
    owner_title = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Title/designation. e.g. 'Principal', 'Chairman', 'Director'",
    )
    owner_id_type = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Type of ID provided. e.g. 'National ID', 'Passport'",
    )
    owner_id_number = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text=(
            "Owner's national ID or passport number. "
            "SENSITIVE — encrypt at rest in production."
        ),
    )

    # ─────────────────────────────────────────────
    # School Registration
    # ─────────────────────────────────────────────

    registration_number = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Official school registration number issued by the government body.",
    )
    registration_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date the school was officially registered.",
    )
    registered_with = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text=(
            "Name of the government body the school is registered with. "
            "e.g. 'Ministry of Education, Nepal'"
        ),
    )
    registration_document = models.FileField(
        upload_to=legal_document_path,
        null=True,
        blank=True,
        validators=[FileExtensionValidator(allowed_extensions=["pdf", "jpg", "jpeg", "png"])],
        help_text="Scanned copy of the official registration certificate. Private — not public.",
    )
    registration_expiry = models.DateField(
        null=True,
        blank=True,
        help_text="Registration expiry date if applicable.",
    )

    # ─────────────────────────────────────────────
    # Tax / VAT
    # ─────────────────────────────────────────────

    tax_id_number = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Tax identification number / PAN / VAT number.",
    )
    vat_registered = models.BooleanField(
        default=False,
        help_text="Whether the school is VAT registered.",
    )
    vat_number = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="VAT registration number (if VAT registered).",
    )

    # ─────────────────────────────────────────────
    # Accreditation
    # ─────────────────────────────────────────────

    accreditation_status = models.CharField(
        max_length=20,
        choices=AccreditationStatus.choices,
        default=AccreditationStatus.NOT_APPLICABLE,
    )
    accreditation_body = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Name of the accrediting organization. e.g. 'Nepal Accreditation Council'",
    )
    accreditation_number = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Certificate or license number issued by the accrediting body.",
    )
    accreditation_valid_from = models.DateField(
        null=True,
        blank=True,
    )
    accreditation_valid_until = models.DateField(
        null=True,
        blank=True,
        help_text="Expiry date of the accreditation. Alerts should fire before this.",
    )
    accreditation_document = models.FileField(
        upload_to=accreditation_document_path,
        null=True,
        blank=True,
        validators=[FileExtensionValidator(allowed_extensions=["pdf", "jpg", "jpeg", "png"])],
        help_text="Scanned accreditation certificate. Private — not public.",
    )

    # ─────────────────────────────────────────────
    # Internal Notes
    # ─────────────────────────────────────────────

    internal_notes = models.TextField(
        blank=True,
        default="",
        help_text=(
            "Private notes visible only to super_user via terminal/admin. "
            "e.g. billing issues, compliance flags, support history."
        ),
    )

    class Meta:
        app_label = "Orgs"
        db_table = "org_legal"
        verbose_name = "Organization Legal"
        verbose_name_plural = "Organization Legal Records"

    def __str__(self):
        return f"Legal: {self.org.slug}"

    # ─────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────

    @property
    def is_accreditation_expired(self) -> bool:
        from django.utils import timezone
        if self.accreditation_valid_until is None:
            return False
        return self.accreditation_valid_until < timezone.now().date()

    @property
    def is_registration_expired(self) -> bool:
        from django.utils import timezone
        if self.registration_expiry is None:
            return False
        return self.registration_expiry < timezone.now().date()

    @property
    def legal_completion_percent(self) -> int:
        """
        0–100 completeness score for the legal section.
        Shown in sys dashboard to prompt system admin to fill in required fields.
        """
        tracked_fields = [
            "owner_full_name", "owner_id_number",
            "registration_number", "registration_date", "registered_with",
            "tax_id_number",
            "accreditation_status",
        ]
        filled = sum(1 for f in tracked_fields if getattr(self, f))
        return round((filled / len(tracked_fields)) * 100)
