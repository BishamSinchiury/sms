from rest_framework import generics, serializers
from rest_framework.exceptions import ValidationError

from Orgs.models.domain import OrgDomain
from Orgs.permissions import IsSysAdmin


class OrgDomainSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrgDomain
        fields = [
            "id", "domain", "is_primary", "is_verified", 
            "notes", "created_at"
        ]
        read_only_fields = ["id", "is_verified", "created_at"]

    def create(self, validated_data):
        request = self.context.get("request")
        validated_data["org"] = request.sys_admin_org
        return super().create(validated_data)


class DomainListCreateView(generics.ListCreateAPIView):
    serializer_class = OrgDomainSerializer
    permission_classes = [IsSysAdmin]

    def get_queryset(self):
        return OrgDomain.objects.filter(org=self.request.sys_admin_org).order_by("-is_primary", "-created_at")


class DomainDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = OrgDomainSerializer
    permission_classes = [IsSysAdmin]

    def get_queryset(self):
        return OrgDomain.objects.filter(org=self.request.sys_admin_org)

    def perform_destroy(self, instance):
        if instance.is_primary:
            raise ValidationError({"detail": "Cannot delete the primary domain. Set another domain as primary first."})
        instance.delete()
