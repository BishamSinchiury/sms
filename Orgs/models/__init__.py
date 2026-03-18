"""
models/__init__.py
------------------
Clean import surface for the organizations app.

Usage anywhere in the project:
    from apps.organizations.models import Organization, OrgDomain, OrganizationProfile, OrganizationLegal
"""

from .organization import Organization
from .domain import OrgDomain
from .profile import OrganizationProfile, SchoolType
from .legal import OrganizationLegal, AccreditationStatus
from .sub_organization import SubOrganization, SubOrgType

__all__ = [
    "Organization",
    "OrgDomain",
    "OrganizationProfile",
    "SchoolType",
    "OrganizationLegal",
    "AccreditationStatus",
    "SubOrganization",
    "SubOrgType",
]

