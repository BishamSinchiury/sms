from rest_framework import serializers
from .models.profile import OrganizationProfile
from .models.legal import OrganizationLegal
from .models.sub_organization import SubOrganization
from Orgs.models.owner import OrgOwner


class OrganizationLegalSerializer(serializers.ModelSerializer):
    """
    Serializer for the private OrganizationLegal model.
    Used exclusively by system admins via the sys dashboard.
    """
    legal_completion_percent = serializers.ReadOnlyField()
    is_registration_expired = serializers.ReadOnlyField()
    is_accreditation_expired = serializers.ReadOnlyField()

    class Meta:
        model = OrganizationLegal
        fields = [
            'registration_number',
            'registration_date',
            'registered_with',
            'registration_document',
            'registration_expiry',
            'tax_id_number',
            'vat_registered',
            'vat_number',
            'accreditation_status',
            'accreditation_body',
            'accreditation_number',
            'accreditation_valid_from',
            'accreditation_valid_until',
            'accreditation_document',
            'internal_notes',
            'legal_completion_percent',
            'is_registration_expired',
            'is_accreditation_expired',
        ]


class OrganizationProfileSerializer(serializers.ModelSerializer):
    """
    Serializer for the OrganizationProfile model.
    Used by system admins to view and manage their org's identity.
    """
    org_slug = serializers.ReadOnlyField(source='org.slug')
    completion_score = serializers.ReadOnlyField(source='profile_completion_percent')
    full_address = serializers.ReadOnlyField()

    class Meta:
        model = OrganizationProfile
        fields = [
            'id',
            'org_slug',
            'name',
            'short_name',
            'school_type',
            'tagline',
            'description',
            'established_year',
            'logo',
            'favicon',
            'cover_image',
            'primary_color',
            'secondary_color',
            'address_line_1',
            'address_line_2',
            'city',
            'state_province',
            'postal_code',
            'country',
            'phone_primary',
            'phone_secondary',
            'email_primary',
            'email_admissions',
            'website',
            'facebook_url',
            'twitter_url',
            'instagram_url',
            'linkedin_url',
            'youtube_url',
            'completion_score',
            'full_address',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class SubOrganizationSerializer(serializers.ModelSerializer):
    """
    Read serializer for SubOrganization.
    Exposes parent_org slug and a computed member count.
    """
    parent_org_slug = serializers.ReadOnlyField(source='parent_org.slug')
    member_count    = serializers.SerializerMethodField()

    class Meta:
        model  = SubOrganization
        fields = [
            'id',
            'parent_org_slug',
            'name',
            'code',
            'sub_type',
            'description',
            'is_active',
            'member_count',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'parent_org_slug', 'member_count', 'created_at', 'updated_at']

    def get_member_count(self, obj):
        return obj.members.filter(status='active').count()


class SubOrganizationWriteSerializer(serializers.ModelSerializer):
    """
    Write serializer for SubOrganization (create / partial update).
    Validates that the code is unique within the parent org.
    """
    class Meta:
        model  = SubOrganization
        fields = ['name', 'code', 'sub_type', 'description', 'is_active']

    def validate_code(self, value):
        """Ensure code is unique within this org (exclude self on update)."""
        parent_org = self.context.get('parent_org')
        qs = SubOrganization.objects.filter(parent_org=parent_org, code=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                f"A sub-organization with code '{value}' already exists in this org."
            )
        return value

from .models.activity_log import OrgActivityLog

class OrgActivityLogSerializer(serializers.ModelSerializer):
    """
    Serializer for the append-only OrgActivityLog.
    Masks IP addresses by default unless ?expand=true is passed.
    Extracts the last 8 chars of a session_id.
    """
    actor = serializers.SerializerMethodField()
    session_id = serializers.SerializerMethodField()
    ip_address = serializers.SerializerMethodField()
    ip_address_full = serializers.SerializerMethodField()

    class Meta:
        model = OrgActivityLog
        fields = [
            'id', 'category', 'severity', 'action', 'detail',
            'created_at', 'actor', 'session_id', 'ip_address', 'ip_address_full',
            'user_agent'
        ]
        read_only_fields = fields

    def get_actor(self, obj):
        return {
            "id": obj.actor_id,
            "full_name": obj.actor_name,
            "email": obj.actor_email
        }

    def get_session_id(self, obj):
        if not obj.session_id:
            return ""
        return obj.session_id[-8:]

    def get_ip_address(self, obj):
        if not obj.ip_address:
            return ""
        parts = obj.ip_address.split('.')
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.*.*"
        return f"{obj.ip_address[:4]}***"

    def get_ip_address_full(self, obj):
        request = self.context.get('request')
        if request and request.query_params.get('expand') == 'true':
            return obj.ip_address
        return None




# Fields containing sensitive ID numbers — stripped from list responses,
# returned only in detail (single instance) responses
SENSITIVE_NUMBER_FIELDS = [
    "pan_number",
    "national_id_number",
    "driving_license_number",
    "passport_number",
]


class OrgOwnerSerializer(serializers.ModelSerializer):
    """
    Serializer for OrgOwner.

    Sensitive number fields (pan_number, national_id_number, etc.):
      - Always writable (POST / PATCH)
      - Stripped from LIST responses
      - Included in DETAIL (single instance) responses
      - Views signal which context via context["detail"] = True/False

    Document file fields:
      - Writable as file uploads (multipart)
      - Returned as URLs in responses when a file exists

    user field:
      - Returned as the user's email for readability
      - Writable as a user PK (optional, nullable)
    """

    # Return user email in responses instead of raw PK for readability
    user_email = serializers.SerializerMethodField(read_only=True)

    # org is always set from request.sys_admin_org in the view
    org = serializers.SlugRelatedField(
        slug_field="slug",
        read_only=True,
    )

    class Meta:
        model = OrgOwner
        fields = [
            "id",
            "org",
            "user",
            "user_email",
            "full_legal_name",
            "is_primary",
            # PAN
            "pan_number",
            "pan_document",
            # National ID
            "national_id_number",
            "national_id_document",
            # Driving license
            "driving_license_number",
            "driving_license_document",
            # Passport
            "passport_number",
            "passport_document",
            # Ownership
            "ownership_document",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "org", "user_email", "created_at", "updated_at"]
        extra_kwargs = {
            # user is optional — nullable FK
            "user": {"required": False, "allow_null": True},
            # Document files are optional
            "pan_document":              {"required": False, "allow_null": True},
            "national_id_document":      {"required": False, "allow_null": True},
            "driving_license_document":  {"required": False, "allow_null": True},
            "passport_document":         {"required": False, "allow_null": True},
            "ownership_document":        {"required": False, "allow_null": True},
        }

    def get_user_email(self, obj):
        # Safely return the linked user's email or None if no user linked
        if obj.user_id:
            return obj.user.email
        return None

    def to_representation(self, instance):
        rep = super().to_representation(instance)

        # Strip sensitive ID number fields from list responses
        # Only include them when the view explicitly signals detail context
        if not self.context.get("detail", False):
            for field in SENSITIVE_NUMBER_FIELDS:
                rep.pop(field, None)

        return rep

    def validate_full_legal_name(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Full legal name is required.")
        return value.strip()

    def validate(self, attrs):
        is_primary = attrs.get(
            "is_primary",
            # On PATCH, fall back to current value if not being changed
            self.instance.is_primary if self.instance else False,
        )

        if is_primary:
            org = self.context.get("org")
            if org is None:
                raise serializers.ValidationError(
                    "Org context missing — this is a server configuration error."
                )

            conflict_qs = OrgOwner.objects.filter(org=org, is_primary=True)
            if self.instance:
                conflict_qs = conflict_qs.exclude(pk=self.instance.pk)

            if conflict_qs.exists():
                raise serializers.ValidationError({
                    "is_primary": (
                        "A primary owner already exists for this organization. "
                        "Set the existing primary owner to non-primary first."
                    )
                })

        return attrs