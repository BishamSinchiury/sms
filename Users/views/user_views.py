from rest_framework import generics, status
from rest_framework.response import Response
from Users.permissions import HasValidToken

from Users.models.user import User
from Users.models.membership import MembershipStatus
from rest_framework import serializers

class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "phone_number"]

class UserProfileUpdateView(generics.RetrieveUpdateAPIView):
    """
    Endpoint for users to complete or resubmit their profile.
    Automatically changes membership status to 'WAITING_APPROVAL'.
    """
    permission_classes = [HasValidToken]
    serializer_class = UserProfileSerializer

    def get_object(self):
        return self.request.user

    def update(self, request, *args, **kwargs):
        user = self.get_object()
        membership = user.membership

        # Only allow if pending or rejected (otherwise they are already active/waiting)
        if membership.status not in [MembershipStatus.PENDING, MembershipStatus.REJECTED]:
            return Response(
                {"detail": f"Profile cannot be updated while in {membership.status} status."},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = self.get_serializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        # Triggers status transition
        membership.status = MembershipStatus.WAITING_APPROVAL
        membership.save(update_fields=["status", "updated_at"])

        return Response(
            {"detail": "Profile updated successfully. Waiting for admin approval.", "data": serializer.data},
            status=status.HTTP_200_OK
        )

