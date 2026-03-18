from rest_framework import serializers
from .models.profile import OrganizationProfile
from .models.sub_organization import SubOrganization


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
