"""
person.py
---------
Stores personal profiles for all users.
Every person is uniquely linked to a User record.

- IdentityDocument: documents linked to a Person.
- Guardian: linked to a Person (students only).
"""

from django.db import models
from django.core.exceptions import ValidationError
from core.models import TimeStampedModel
from .roles import CoreRoleType
from .user import User

# ─────────────────────────────────────────────
# Person
# ─────────────────────────────────────────────
class Person(TimeStampedModel):
    """
    Detailed profile information for a user.
    Role and org logic are handled via User -> OrgMembership -> OrgRole.
    """
    class GenderChoices(models.TextChoices):
        MALE = "male", "Male"
        FEMALE = "female", "Female"
        OTHER = "other", "Other"
        PREFER_NOT_TO_SAY = "prefer_not_to_say", "Prefer not to say"

    class BloodGroupChoices(models.TextChoices):
        A_POS = "A+", "A+"
        A_NEG = "A-", "A-"
        B_POS = "B+", "B+"
        B_NEG = "B-", "B-"
        AB_POS = "AB+", "AB+"
        AB_NEG = "AB-", "AB-"
        O_POS = "O+", "O+"
        O_NEG = "O-", "O-"

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="person",
    )
    
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(
        max_length=20,
        choices=GenderChoices.choices,
        default=GenderChoices.PREFER_NOT_TO_SAY,
    )
    blood_group = models.CharField(
        max_length=3,
        choices=BloodGroupChoices.choices,
        blank=True,
        default="",
    )
    nationality = models.CharField(max_length=100, blank=True, default="")
    religion = models.CharField(max_length=100, blank=True, default="")
    
    photo = models.ImageField(upload_to="persons/photos/", blank=True)
    
    address_line_1 = models.CharField(max_length=255, blank=True, default="")
    address_line_2 = models.CharField(max_length=255, blank=True, default="")
    city = models.CharField(max_length=100, blank=True, default="")
    state_or_province = models.CharField(max_length=100, blank=True, default="")
    postal_code = models.CharField(max_length=20, blank=True, default="")
    country = models.CharField(max_length=100, blank=True, default="")
    
    emergency_contact_name = models.CharField(max_length=150, blank=True, default="")
    emergency_contact_phone = models.CharField(max_length=20, blank=True, default="")
    emergency_contact_relation = models.CharField(max_length=100, blank=True, default="")
    
    extra_data = models.JSONField(blank=True, default=dict)

    class Meta:
        db_table = "persons"
        verbose_name = "Person"
        verbose_name_plural = "Persons"

    def __str__(self):
        return f"Person: {self.user.email}"

    @property
    def age(self):
        import datetime
        if not self.date_of_birth:
            return None
        today = datetime.date.today()
        # compute age
        return today.year - self.date_of_birth.year - ((today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day))

    @property
    def role_type(self):
        membership = getattr(self.user, "membership", None)
        if membership and membership.role:
            return membership.role.role_type
        return None


# ─────────────────────────────────────────────
# IdentityDocument
# ─────────────────────────────────────────────
class IdentityDocument(TimeStampedModel):
    """
    Various documents associated with a Person.
    """
    class DocumentTypeChoices(models.TextChoices):
        NATIONAL_ID = "national_id", "National ID"
        PASSPORT = "passport", "Passport"
        BIRTH_CERTIFICATE = "birth_certificate", "Birth Certificate"
        DRIVING_LICENSE = "driving_license", "Driving License"
        OTHER = "other", "Other"

    person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name="identity_documents",
    )
    document_type = models.CharField(
        max_length=50,
        choices=DocumentTypeChoices.choices,
        default=DocumentTypeChoices.OTHER,
    )
    document_number = models.CharField(max_length=100, blank=True, default="")
    issued_by = models.CharField(max_length=100, blank=True, default="")
    issued_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    
    front_image = models.FileField(upload_to="persons/documents/")
    back_image = models.FileField(upload_to="persons/documents/", blank=True)
    
    is_verified = models.BooleanField(default=False)

    class Meta:
        db_table = "identity_documents"
        verbose_name = "Identity Document"
        verbose_name_plural = "Identity Documents"
        indexes = [
            models.Index(fields=["person"], name="idx_identity_doc_person"),
        ]

    def __str__(self):
        return f"{self.document_type} for {self.person}"


# ─────────────────────────────────────────────
# Guardian
# ─────────────────────────────────────────────
class Guardian(TimeStampedModel):
    """
    A guardian linked to a Student person.
    """
    class RelationChoices(models.TextChoices):
        FATHER = "father", "Father"
        MOTHER = "mother", "Mother"
        SIBLING = "sibling", "Sibling"
        UNCLE = "uncle", "Uncle"
        AUNT = "aunt", "Aunt"
        GRANDPARENT = "grandparent", "Grandparent"
        LEGAL_GUARDIAN = "legal_guardian", "Legal Guardian"
        OTHER = "other", "Other"

    person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name="guardians",
    )
    parent_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="guardian_profiles",
    )
    full_name = models.CharField(max_length=150)
    phone_number = models.CharField(max_length=20, blank=True, default="")
    email = models.EmailField(blank=True, null=True)
    relation = models.CharField(
        max_length=50,
        choices=RelationChoices.choices,
        default=RelationChoices.OTHER,
    )
    is_primary = models.BooleanField(default=False)
    address = models.TextField(blank=True, default="")
    occupation = models.CharField(max_length=150, blank=True, default="")

    class Meta:
        db_table = "guardians"
        verbose_name = "Guardian"
        verbose_name_plural = "Guardians"
        indexes = [
            models.Index(fields=["person"], name="idx_guardian_person"),
        ]

    def __str__(self):
        return f"{self.full_name} ({self.relation}) for {self.person}"

    def clean(self):
        super().clean()
        if self.is_primary:
            existing = Guardian.objects.filter(person=self.person, is_primary=True)
            if self.pk:
                existing = existing.exclude(pk=self.pk)
            if existing.exists():
                raise ValidationError("A primary guardian already exists for this person.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
