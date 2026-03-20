from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.utils import timezone

from Users.models.membership import OrgMembership, MembershipStatus
from Users.models.user import User
from rest_framework import serializers

from Orgs.utils.logger import log_org_activity

# No specific sysadmin DRF permission available. We check it in the view.


class PendingUserSerializer(serializers.ModelSerializer):
    email = serializers.CharField(source="user.email", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)
    phone_number = serializers.CharField(source="user.phone_number", read_only=True)
    role_name = serializers.CharField(source="role.name", read_only=True)
    status = serializers.CharField(read_only=True)

    class Meta:
        model = OrgMembership
        fields = ["id", "email", "first_name", "last_name", "phone_number", "role_name", "status", "created_at"]

class PendingUsersListView(generics.ListAPIView):
    """
    Lists users waiting for approval (or pending overall).
    For system admin.
    """
    serializer_class = PendingUserSerializer

    def get_queryset(self):
        user_id = self.request.session.get("user_id")
        is_sys_admin = self.request.session.get("is_sys_admin")
        
        if not user_id or not is_sys_admin:
            return OrgMembership.objects.none()
            
        try:
            membership = OrgMembership.objects.get(user_id=user_id, is_system_admin=True)
        except OrgMembership.DoesNotExist:
            return OrgMembership.objects.none()

        # Returns users in PENDING or WAITING_APPROVAL
        return OrgMembership.objects.filter(
            org=membership.org, 
            status__in=[MembershipStatus.PENDING, MembershipStatus.WAITING_APPROVAL]
        ).select_related("user", "role")

class ApproveUserView(APIView):
    """
    Approves a user's membership.
    """
    def post(self, request, pk):
        user_id = request.session.get("user_id")
        is_sys_admin = request.session.get("is_sys_admin")
        
        if not user_id or not is_sys_admin:
            return Response({"detail": "Not authorized."}, status=status.HTTP_403_FORBIDDEN)
            
        try:
            membership_sys = OrgMembership.objects.get(user_id=user_id, is_system_admin=True)
        except OrgMembership.DoesNotExist:
             return Response({"detail": "Not authorized."}, status=status.HTTP_403_FORBIDDEN)

        target_membership = get_object_or_404(OrgMembership, id=pk, org=membership_sys.org)
        
        # We need the user object for the audit trail
        req_user = User.objects.get(id=user_id)
        target_membership.approve(req_user)
        
        log_org_activity(
            org=membership_sys.org, actor=req_user, category="membership", severity="info",
            action=f"Membership approved for {target_membership.user.email}", request=request
        )
        
        return Response({"detail": "User approved successfully."})

class RejectUserView(APIView):
    """
    Rejects a user's membership.
    """
    def post(self, request, pk):
        user_id = request.session.get("user_id")
        is_sys_admin = request.session.get("is_sys_admin")
        
        if not user_id or not is_sys_admin:
            return Response({"detail": "Not authorized."}, status=status.HTTP_403_FORBIDDEN)
            
        try:
            membership_sys = OrgMembership.objects.get(user_id=user_id, is_system_admin=True)
        except OrgMembership.DoesNotExist:
             return Response({"detail": "Not authorized."}, status=status.HTTP_403_FORBIDDEN)

        target_membership = get_object_or_404(OrgMembership, id=pk, org=membership_sys.org)
        reason = request.data.get("reason", "")
        
        req_user = User.objects.get(id=user_id)
        target_membership.reject(req_user, reason)
        
        log_org_activity(
            org=membership_sys.org, actor=req_user, category="membership", severity="warning",
            action=f"Membership rejected for {target_membership.user.email}", request=request
        )
        
        return Response({"detail": "User rejected successfully."})
