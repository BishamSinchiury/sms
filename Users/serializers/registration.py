"""
registration.py
---------------
Atomic, role-aware registration serializer for creating User, OrgMembership, and Person.
"""

from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.db import transaction

from Orgs.models.organization import Organization
from Users.models.roles import OrgRole, CoreRoleType
from Users.models.membership import OrgMembership, MembershipStatus
from Users.models.person import Person, Guardian

User = get_user_model()

class RegisterRoleAwareSerializer(serializers.Serializer):
    # Step 1: Account
    first_name = serializers.CharField(max_length=150)
    last_name  = serializers.CharField(max_length=150)
    email      = serializers.EmailField()
    password   = serializers.CharField(write_only=True, min_length=8)
    phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    org_slug   = serializers.CharField()
    role_id    = serializers.CharField()

    # Step 2: Personal Info
    photo = serializers.ImageField(required=False, allow_null=True)
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    gender = serializers.ChoiceField(choices=Person.GenderChoices.choices, default=Person.GenderChoices.PREFER_NOT_TO_SAY)
    blood_group = serializers.ChoiceField(choices=Person.BloodGroupChoices.choices, required=False, allow_blank=True)
    nationality = serializers.CharField(max_length=100, required=False, allow_blank=True)
    religion = serializers.CharField(max_length=100, required=False, allow_blank=True)

    # Step 3: Address
    address_line_1 = serializers.CharField(max_length=255, required=False, allow_blank=True)
    address_line_2 = serializers.CharField(max_length=255, required=False, allow_blank=True)
    city = serializers.CharField(max_length=100, required=False, allow_blank=True)
    state_or_province = serializers.CharField(max_length=100, required=False, allow_blank=True)
    postal_code = serializers.CharField(max_length=20, required=False, allow_blank=True)
    country = serializers.CharField(max_length=100, required=False, allow_blank=True)

    # Step 4: Role-specific Data (Using JSONField to support multipart/form-data stringified JSON)
    teacher = serializers.JSONField(required=False)
    student = serializers.JSONField(required=False)
    staff = serializers.JSONField(required=False)
    parent = serializers.JSONField(required=False)
    vendor = serializers.JSONField(required=False)

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
            raise serializers.ValidationError({"org_slug": "Organization not found. Please check the slug."})

        profile = getattr(org, "profile", None)
        if not profile or not profile.name:
            raise serializers.ValidationError({"org_slug": "This organization has not completed setup. Registration is currently disabled."})

        try:
            role = OrgRole.objects.get(id=role_id, is_system_role=False, org=org)
        except OrgRole.DoesNotExist:
            raise serializers.ValidationError({"role_id": "Invalid role. The role must belong to the specified organization."})

        data["_org"]  = org
        data["_role"] = role
        return data

    @transaction.atomic
    def save(self):
        data = self.validated_data
        role = data["_role"]
        org  = data["_org"]

        # 1. Create User (active immediately, membership handles pending status)
        user = User.objects.create_user(
            email=data["email"],
            password=data["password"],
            first_name=data["first_name"],
            last_name=data["last_name"],
            phone_number=data.get("phone_number", ""),
            is_active=True,
        )

        # 2. Create OrgMembership
        membership = OrgMembership.objects.create(
            user=user,
            org=org,
            role=role,
            status=MembershipStatus.PENDING,
        )

        # 3. Create Person
        role_type = role.role_type
        extra_data_key = role_type.lower()
        extra_data = data.get(extra_data_key, {})

        person = Person.objects.create(
            user=user,
            photo=data.get("photo"),
            date_of_birth=data.get("date_of_birth"),
            gender=data.get("gender", Person.GenderChoices.PREFER_NOT_TO_SAY),
            blood_group=data.get("blood_group", ""),
            nationality=data.get("nationality", ""),
            religion=data.get("religion", ""),
            address_line_1=data.get("address_line_1", ""),
            address_line_2=data.get("address_line_2", ""),
            city=data.get("city", ""),
            state_or_province=data.get("state_or_province", ""),
            postal_code=data.get("postal_code", ""),
            country=data.get("country", ""),
            extra_data=extra_data,
        )

        # Handle Student's Guardian info mapped from the student step
        if role_type == CoreRoleType.STUDENT and extra_data:
            g_name = extra_data.get("guardian_name", "").strip()
            g_phone = extra_data.get("guardian_phone", "").strip()
            g_rel = extra_data.get("guardian_relation", "").strip()
            if g_name:
                Guardian.objects.create(
                    person=person,
                    full_name=g_name,
                    phone_number=g_phone,
                    relation=g_rel or Guardian.RelationChoices.OTHER,
                    is_primary=True
                )

        return user
