"""
models/__init__.py
------------------
Single import surface for all auth/user models.

Usage in views, serializers, signals:
    from .models import User, Organization, OrgMembership, OrgRole, ...
"""

from .user import User, SuperUser
from .roles import OrgRole, RolePermission, FeatureFlag
from .membership import OrgMembership, MembershipStatus
from .auth_session import SystemAdminSession, RefreshTokenRecord
from .person import Person, IdentityDocument, Guardian

__all__ = [
    
    # Users
    "User",
    "SuperUser",

    # Roles & Permissions
    "OrgRole",
    "RolePermission",
    "FeatureFlag",

    # Membership
    "OrgMembership",
    "MembershipStatus",

    # Auth / Sessions
    "SystemAdminSession",
    "RefreshTokenRecord",

    # Persons & Profiles
    "Person",
    "IdentityDocument",
    "Guardian",
]
