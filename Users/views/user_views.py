# ── Users/views/user_views.py ──

"""
user_views.py
-------------
UserProfileUpdateView — Step 2 of the profile submission flow.

Called by ProfileSetup.handleSubmit after PATCH /profile/me/ (Step 1)
succeeds. This view triggers the status transition to WAITING_APPROVAL
and enforces hard document validation before allowing the transition.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from Users.permissions import HasValidToken
from Users.models.membership import OrgMembership, MembershipStatus
from Users.models.person import Person, IdentityDocument


# ─────────────────────────────────────────────
# Document hard-validation — same rules as profile.py
# Duplicated here intentionally to keep this view self-contained.
# ─────────────────────────────────────────────

_REQUIRED_IDENTITY_DOCS = {
    "teacher": {"national_id", "passport"},
    "staff":   {"national_id", "passport"},
    "parent":  {"national_id", "passport"},
    "vendor":  {"national_id", "passport"},
    "student": {"national_id", "birth_certificate"},
}


def _has_required_identity_doc(person, role_type):
    required_types = _REQUIRED_IDENTITY_DOCS.get(role_type)
    if not required_types:
        return True, None
    exists = IdentityDocument.objects.filter(
        person=person,
        document_type__in=required_types,
    ).exists()
    if not exists:
        if role_type == "student":
            msg = (
                "Please upload at least one identity document: "
                "National ID or Birth Certificate."
            )
        else:
            msg = (
                "Please upload at least one identity document: "
                "National ID or Passport."
            )
        return False, msg
    return True, None


class UserProfileUpdateView(APIView):
    """
    PATCH /api/users/me/profile/

    Step 2 of the profile submission flow.
    Updates User.first_name, User.last_name, User.phone_number and
    transitions membership.status from PENDING or REJECTED to
    WAITING_APPROVAL.

    Hard validation: checks that the required identity document exists
    before allowing the transition. If the document is missing, returns
    400 with a clear error message and does NOT change the status.

    Allowed when status is PENDING or REJECTED only.
    WAITING_APPROVAL, ACTIVE, and SUSPENDED are not re-submittable.
    """
    permission_classes = [HasValidToken]

    def patch(self, request):
        user = request.user
        membership = getattr(user, 'membership', None)

        if not membership:
            return Response(
                {'detail': 'No membership found.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        submittable_statuses = [
            MembershipStatus.PENDING,
            MembershipStatus.REJECTED,
        ]
        if membership.status not in submittable_statuses:
            return Response(
                {'detail': 'Profile has already been submitted or cannot be resubmitted at this time.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Hard document validation before status transition.
        # If the person has not uploaded the required identity document,
        # we stop here — do not update the status.
        try:
            person = Person.objects.get(user=user)
            role_type = person.role_type
            ok, error_msg = _has_required_identity_doc(person, role_type)
            if not ok:
                return Response(
                    {'detail': error_msg, 'code': 'missing_identity_document'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except Person.DoesNotExist:
            # Person was not found — block submission.
            return Response(
                {'detail': 'Profile data not found. Please complete the profile form first.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Update User name and phone from request body.
        first_name   = request.data.get('first_name', '').strip()
        last_name    = request.data.get('last_name', '').strip()
        phone_number = request.data.get('phone_number', '').strip()

        changed = False
        if first_name:
            user.first_name = first_name
            changed = True
        if last_name:
            user.last_name = last_name
            changed = True
        if phone_number:
            user.phone_number = phone_number
            changed = True
        if changed:
            user.save(update_fields=['first_name', 'last_name', 'phone_number'])

        # Transition status → WAITING_APPROVAL.
        membership.status = MembershipStatus.WAITING_APPROVAL
        membership.save(update_fields=['status', 'updated_at'])

        return Response(
            {'detail': 'Profile submitted. Awaiting admin approval.'},
            status=status.HTTP_200_OK,
        )