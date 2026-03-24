"""
person.py
---------
Serializers for Person, IdentityDocument, and Guardian models.
"""

from rest_framework import serializers
from Users.models.person import Person, IdentityDocument, Guardian

class IdentityDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = IdentityDocument
        fields = [
            "id", "document_type", "document_number",
            "issued_by", "issued_date", "expiry_date",
            "front_image", "back_image", "is_verified"
        ]
        read_only_fields = ["id", "is_verified"]

class GuardianSerializer(serializers.ModelSerializer):
    class Meta:
        model = Guardian
        fields = [
            "id", "full_name", "phone_number", "email",
            "relation", "is_primary", "address", "occupation"
        ]
        read_only_fields = ["id"]

# ── Users/serializers/person.py ──

"""
person.py
---------
Serializers for Person, IdentityDocument, and Guardian models.
"""

from rest_framework import serializers
from Users.models.person import Person, IdentityDocument, Guardian


class IdentityDocumentSerializer(serializers.ModelSerializer):
    """
    Used for both GET /profile/me/documents/ and POST /profile/me/documents/.
    front_image is required on create. back_image is optional.
    document_type must be a valid choice from the extended list.
    is_verified is read-only — set by admin only.
    """
    # Expose the human-readable label alongside the raw value
    document_type_display = serializers.CharField(
        source='get_document_type_display',
        read_only=True,
    )

    class Meta:
        model  = IdentityDocument
        fields = [
            "id",
            "document_type",
            "document_type_display",
            "document_number",
            "issued_by",
            "issued_date",
            "expiry_date",
            "front_image",
            "back_image",
            "is_verified",
            "created_at",
        ]
        read_only_fields = ["id", "is_verified", "created_at", "document_type_display"]


class GuardianSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Guardian
        fields = [
            "id", "full_name", "phone_number", "email",
            "relation", "is_primary", "address", "occupation"
        ]
        read_only_fields = ["id"]


# ── Users/serializers/person.py ──

"""
person.py
---------
Serializers for Person, IdentityDocument, and Guardian models.
"""

from rest_framework import serializers
from Users.models.person import Person, IdentityDocument, Guardian


class IdentityDocumentSerializer(serializers.ModelSerializer):
    """
    Used for both GET /profile/me/documents/ and POST /profile/me/documents/.
    front_image is required on create. back_image is optional.
    document_type must be a valid choice from the extended list.
    is_verified is read-only — set by admin only.
    """
    # Expose the human-readable label alongside the raw value
    document_type_display = serializers.CharField(
        source='get_document_type_display',
        read_only=True,
    )

    class Meta:
        model  = IdentityDocument
        fields = [
            "id",
            "document_type",
            "document_type_display",
            "document_number",
            "issued_by",
            "issued_date",
            "expiry_date",
            "front_image",
            "back_image",
            "is_verified",
            "created_at",
        ]
        read_only_fields = ["id", "is_verified", "created_at", "document_type_display"]


class GuardianSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Guardian
        fields = [
            "id", "full_name", "phone_number", "email",
            "relation", "is_primary", "address", "occupation"
        ]
        read_only_fields = ["id"]


class PersonSerializer(serializers.ModelSerializer):
    photo_url          = serializers.SerializerMethodField()
    identity_documents = IdentityDocumentSerializer(many=True, read_only=True)
    guardians          = GuardianSerializer(many=True, read_only=True)

    first_name   = serializers.CharField(source="user.first_name", required=False)
    last_name    = serializers.CharField(source="user.last_name",  required=False)
    email        = serializers.EmailField(source="user.email",     read_only=True)
    phone_number = serializers.CharField(source="user.phone_number", required=False)

    age       = serializers.IntegerField(read_only=True)
    role_type = serializers.CharField(read_only=True)

    # Role-specific extra_data fields — write-only on input, injected back
    # via to_representation() on output under the role_type key.
    teacher = serializers.DictField(required=False, write_only=True)
    student = serializers.DictField(required=False, write_only=True)
    staff   = serializers.DictField(required=False, write_only=True)
    parent  = serializers.DictField(required=False, write_only=True)
    vendor  = serializers.DictField(required=False, write_only=True)

    class Meta:
        model  = Person
        fields = [
            "id", "first_name", "last_name", "email", "phone_number",
            "gender", "date_of_birth", "blood_group", "nationality", "religion",
            "photo", "photo_url",
            "address_line_1", "address_line_2", "city",
            "state_or_province", "postal_code", "country",
            "emergency_contact_name", "emergency_contact_phone", "emergency_contact_relation",
            "age", "role_type",
            "identity_documents", "guardians",
            "teacher", "student", "staff", "parent", "vendor",
        ]
        read_only_fields = ["id", "age", "role_type"]
        extra_kwargs = {
            'photo': {'write_only': True},
        }

    def get_photo_url(self, obj):
        if not obj.photo:
            return None
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(obj.photo.url)
        return obj.photo.url

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        role_type = instance.role_type
        # Inject role-specific extra_data under the role_type key.
        # Explicit allowlist — simpler and guaranteed to work even if
        # write_only DictFields are excluded by super().
        # Guard extra_data against None so callers always get a dict.
        if role_type and role_type.lower() in ['teacher', 'student', 'staff', 'parent', 'vendor']:
            ret[role_type.lower()] = instance.extra_data or {}
        return ret

    def update(self, instance, validated_data):
        user_data    = validated_data.pop("user", {})
        user_changed = False

        if "first_name" in user_data:
            instance.user.first_name = user_data["first_name"]
            user_changed = True
        if "last_name" in user_data:
            instance.user.last_name = user_data["last_name"]
            user_changed = True
        if "phone_number" in user_data:
            instance.user.phone_number = user_data["phone_number"]
            user_changed = True
        if user_changed:
            instance.user.save()

        role_type = instance.role_type
        if role_type:
            role_key = role_type.lower()
            if role_key in validated_data:
                extra_data = validated_data.pop(role_key)
                current    = dict(instance.extra_data) if instance.extra_data else {}
                current.update(extra_data)
                instance.extra_data = current

        # Discard any stray role dicts that don't match this user's role
        for key in ["teacher", "student", "staff", "parent", "vendor"]:
            validated_data.pop(key, None)

        return super().update(instance, validated_data)
