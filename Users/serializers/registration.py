# ── Users/serializers/registration.py ──

"""
registration.py
---------------
Atomic registration serializer — creates User + OrgMembership only.
Person profile is created separately via the profile setup flow
(PATCH /api/profile/me/ after first login).
"""

from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.db import transaction

from Orgs.models.organization import Organization
from Users.models.roles import OrgRole, SYSTEM_ADMIN_ROLE
from Users.models.membership import OrgMembership, MembershipStatus
from Users.models.person import Person
User = get_user_model()


class RegisterRoleAwareSerializer(serializers.Serializer):
    # Account fields only — no Person fields, no role-specific fields
    first_name   = serializers.CharField(max_length=150)
    last_name    = serializers.CharField(max_length=150)
    email        = serializers.EmailField()
    password     = serializers.CharField(write_only=True, min_length=8)
    phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    org_slug     = serializers.CharField()
    role_id      = serializers.CharField()

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value.lower().strip()

    def validate(self, data):
        org_slug = data.get("org_slug", "").strip()
        role_id  = data.get("role_id")

        try:
            org = Organization.objects.select_related("profile").get(
                slug=org_slug, is_active=True
            )
        except Organization.DoesNotExist:
            raise serializers.ValidationError(
                {"org_slug": "Organization not found. Please check the slug."}
            )

        profile = getattr(org, "profile", None)
        if not profile or not profile.name:
            raise serializers.ValidationError(
                {"org_slug": "This organization has not completed setup. Registration is currently disabled."}
            )

        try:
            role = OrgRole.objects.get(id=role_id, org=org)
        except OrgRole.DoesNotExist:
            raise serializers.ValidationError(
                {"role_id": "Invalid role. The role must belong to the specified organization."}
            )

        # Block system_admin role from self-registration — all other roles allowed.
        # The approval flow is the gate, not role selection.
        if role.name == SYSTEM_ADMIN_ROLE:
            raise serializers.ValidationError(
                {"role_id": "This role cannot be self-registered."}
            )

        data["_org"]  = org
        data["_role"] = role
        return data

    @transaction.atomic
    def save(self):
        data = self.validated_data

        # 1. Create User
        user = User.objects.create_user(
            email=data["email"],
            password=data["password"],
            first_name=data["first_name"],
            last_name=data["last_name"],
            phone_number=data.get("phone_number", ""),
            is_active=True,
        )

        # 2. Create OrgMembership — status PENDING until profile is completed
        # and approved by the system admin.
        OrgMembership.objects.create(
            user=user,
            org=data["_org"],
            role=data["_role"],
            status=MembershipStatus.PENDING,
        )

        Person.objects.create(
            user=user,
        )

        return user