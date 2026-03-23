# ── Orgs/models/owner.py ──

from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from core.models import TimeStampedModel
from .organization import Organization
from Users.models.user import User


ALLOWED_DOC_EXTENSIONS = ["pdf", "jpg", "jpeg", "png"]


def owner_document_path(instance, filename):
    """
    All owner documents stored under a private per-org scoped path.
    Never served via public media URLs.
    """
    return f"private/orgs/{instance.org.slug}/owners/{filename}"


class OrgOwner(TimeStampedModel):
    """
    Legal owner record for an organization.

    Purpose: legal compliance and documentation only.
    Stores identity documents required for school registration,
    accreditation, and government filings.

    NOT for platform access — login and roles are handled via
    User + OrgMembership. This model only cares about legal identity.

    user FK is optional:
      - Set when the owner also has a platform account (e.g. the
        principal who is also the system admin).
      - Null when the owner is an external legal contact who never
        logs into the platform.
      - No fields from User are duplicated here — full_legal_name is
        the legal name as it appears on documents, which may differ
        from user.first_name + user.last_name.
    """

    org = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="owners",
        help_text="The organization this owner belongs to.",
    )

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owner_profiles",
        help_text=(
            "Optional link to a platform user account. "
            "Set if the owner also uses the platform. "
            "Null for external owners with no platform account."
        ),
    )

    # ─────────────────────────────────────────────
    # Core Legal Identity
    # ─────────────────────────────────────────────

    full_legal_name = models.CharField(
        max_length=255,
        help_text=(
            "Full legal name exactly as it appears on official documents. "
            "May differ from the platform user's display name."
        ),
    )

    is_primary = models.BooleanField(
        default=False,
        help_text=(
            "Marks this as the primary legal owner. "
            "Only one primary owner allowed per org — enforced by DB constraint."
        ),
    )

    # ─────────────────────────────────────────────
    # PAN Card
    # ─────────────────────────────────────────────

    pan_number = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="PAN card number. SENSITIVE — encrypt at rest in production.",
    )
    pan_document = models.FileField(
        upload_to=owner_document_path,
        null=True,
        blank=True,
        validators=[FileExtensionValidator(allowed_extensions=ALLOWED_DOC_EXTENSIONS)],
        help_text="Scanned copy of PAN card. Private — never served publicly.",
    )

    # ─────────────────────────────────────────────
    # National ID
    # ─────────────────────────────────────────────

    national_id_number = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="National ID card number. SENSITIVE.",
    )
    national_id_document = models.FileField(
        upload_to=owner_document_path,
        null=True,
        blank=True,
        validators=[FileExtensionValidator(allowed_extensions=ALLOWED_DOC_EXTENSIONS)],
        help_text="Scanned national ID card. Private.",
    )

    # ─────────────────────────────────────────────
    # Driving License — optional
    # ─────────────────────────────────────────────

    driving_license_number = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Driving license number. Optional.",
    )
    driving_license_document = models.FileField(
        upload_to=owner_document_path,
        null=True,
        blank=True,
        validators=[FileExtensionValidator(allowed_extensions=ALLOWED_DOC_EXTENSIONS)],
        help_text="Scanned driving license. Optional. Private.",
    )

    # ─────────────────────────────────────────────
    # Passport — optional
    # ─────────────────────────────────────────────

    passport_number = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Passport number. Optional.",
    )
    passport_document = models.FileField(
        upload_to=owner_document_path,
        null=True,
        blank=True,
        validators=[FileExtensionValidator(allowed_extensions=ALLOWED_DOC_EXTENSIONS)],
        help_text="Scanned passport. Optional. Private.",
    )

    # ─────────────────────────────────────────────
    # Ownership Document
    # ─────────────────────────────────────────────

    ownership_document = models.FileField(
        upload_to=owner_document_path,
        null=True,
        blank=True,
        validators=[FileExtensionValidator(allowed_extensions=ALLOWED_DOC_EXTENSIONS)],
        help_text=(
            "Official proof of ownership — deed, board resolution, "
            "certificate of incorporation, or equivalent. Private."
        ),
    )

    class Meta:
        app_label = "Orgs"
        db_table = "org_owners"
        ordering = ["-is_primary", "full_legal_name"]
        verbose_name = "Org Owner"
        verbose_name_plural = "Org Owners"
        constraints = [
            # DB-level guarantee: only one primary owner per org
            models.UniqueConstraint(
                fields=["org"],
                condition=models.Q(is_primary=True),
                name="uq_one_primary_owner_per_org",
            )
        ]

    def __str__(self):
        tag = "PRIMARY" if self.is_primary else "owner"
        return f"{self.full_legal_name} [{tag}] → {self.org.slug}"

    def clean(self):
        super().clean()
        # Model-level check gives a readable error before DB constraint fires
        if self.is_primary:
            conflict = OrgOwner.objects.filter(org=self.org, is_primary=True)
            if self.pk:
                conflict = conflict.exclude(pk=self.pk)
            if conflict.exists():
                raise ValidationError(
                    "A primary owner already exists for this organization. "
                    "Set the existing primary owner to non-primary first."
                )

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)