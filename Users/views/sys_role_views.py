from rest_framework import generics, serializers
from rest_framework.exceptions import ValidationError

from Users.models.roles import OrgRole, CoreRoleType
from Orgs.permissions import IsSysAdmin

class OrgRoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrgRole
        fields = ["id", "name", "role_type", "is_system_role", "description"]
        read_only_fields = ["id", "is_system_role"]

    def create(self, validated_data):
        request = self.context.get("request")
        validated_data["org"] = request.sys_admin_org
        return super().create(validated_data)

    def validate_name(self, value):
        request = self.context.get("request")
        org = request.sys_admin_org
        qs = OrgRole.objects.filter(org=org, name__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("A role with this name already exists in your organization.")
        return value

class RoleListCreateView(generics.ListCreateAPIView):
    serializer_class = OrgRoleSerializer
    permission_classes = [IsSysAdmin]

    def get_queryset(self):
        return OrgRole.objects.filter(org=self.request.sys_admin_org).order_by("name")

class RoleDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = OrgRoleSerializer
    permission_classes = [IsSysAdmin]

    def get_queryset(self):
        return OrgRole.objects.filter(org=self.request.sys_admin_org)

    def perform_destroy(self, instance):
        if not instance.can_be_deleted():
            raise ValidationError({"detail": "System roles cannot be deleted."})
        instance.delete()

    def perform_update(self, serializer):
        instance = self.get_object()
        if instance.is_system_role:
            if "name" in serializer.validated_data and serializer.validated_data["name"] != instance.name:
                raise ValidationError({"name": "System roles cannot be renamed."})
            if "role_type" in serializer.validated_data and serializer.validated_data["role_type"] != instance.role_type:
                raise ValidationError({"role_type": "System role types cannot be changed."})
        serializer.save()
