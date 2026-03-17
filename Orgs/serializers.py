from rest_framework import serializers
from .models.profile import OrganizationProfile

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
