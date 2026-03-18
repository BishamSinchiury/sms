"""
sub_organization.py
--------------------
SubOrganization — a named sub-unit under a parent Organization.

Examples: academic departments, campuses, branches, faculties.

Design:
    - Always belongs to exactly one parent Organization.
    - Identified by a slug-like `code` that is unique within the parent org.
    - Soft-deleted via is_active flag — never hard-deleted.
    - Users can be scoped to a sub-org via OrgMembership.sub_org (optional).
"""

from django.db import models
from core.models import TimeStampedModel
from .organization import Organization


class SubOrgType(models.TextChoices):
    DEPARTMENT = "department", "Department"
    CAMPUS     = "campus",     "Campus"
    BRANCH     = "branch",     "Branch"
    FACULTY    = "faculty",    "Faculty"
    OTHER      = "other",      "Other"


class SubOrganization(TimeStampedModel):
    """
    A lightweight child unit of an Organization.

    Identified by `code` (slug), unique within the parent org.
    All membership/access scoping happens via OrgMembership.sub_org FK.

    Lifecycle:
        - Created by the org's system_admin via the sys dashboard.
        - Deactivated (soft-delete) via is_active=False; never hard-deleted.
    """

    parent_org = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="sub_orgs",
        help_text="The parent tenant organisation this sub-org belongs to.",
    )
    name = models.CharField(
        max_length=200,
        help_text="Human-readable name. e.g. 'Science Department', 'Birtamod Campus'",
    )
    code = models.SlugField(
        max_length=100,
        help_text=(
            "URL-safe identifier, unique within the parent org. "
            "e.g. 'sci-dept', 'birtamod-campus'. Set at creation."
        ),
    )
    sub_type = models.CharField(
        max_length=20,
        choices=SubOrgType.choices,
        default=SubOrgType.DEPARTMENT,
        help_text="Category of this sub-organization.",
    )
    description = models.TextField(
        blank=True,
        default="",
        help_text="Optional description of this sub-organization.",
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Soft-delete flag. Inactive sub-orgs are hidden but not removed.",
    )

    class Meta:
        app_label = "Orgs"
        db_table = "sub_organizations"
        verbose_name = "Sub-Organization"
        verbose_name_plural = "Sub-Organizations"
        unique_together = [("parent_org", "code")]
        ordering = ["parent_org", "name"]

    def __str__(self):
        return f"{self.parent_org.slug} › {self.code}"
