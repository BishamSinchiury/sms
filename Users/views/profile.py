# ── Users/views/profile.py ──

"""
profile.py
----------
Endpoints for managing the current user's Person profile and documents.

Document hard-validation rules (enforced in UserProfileUpdateView before
status transition to WAITING_APPROVAL):
    teacher / staff:  at least one of national_id or passport
    student:          at least one of national_id or birth_certificate
    parent / vendor:  at least one of national_id or passport
    admin / owner:    no document requirement
"""

from rest_framework import generics, parsers, status
from rest_framework.response import Response
from rest_framework.exceptions import NotFound
from Users.permissions import HasValidToken

from Users.models.person import Person, IdentityDocument, Guardian
from Users.models.membership import MembershipStatus
from Users.serializers.person import (
    PersonSerializer,
    IdentityDocumentSerializer,
    GuardianSerializer,
)


# ─────────────────────────────────────────────
# Hard-validation helper
# ─────────────────────────────────────────────

# Maps role_type → set of document_type values that satisfy the requirement.
# At least ONE document of any type in the set must exist for the person.
_REQUIRED_IDENTITY_DOCS = {
    "teacher": {"national_id", "passport"},
    "staff":   {"national_id", "passport"},
    "parent":  {"national_id", "passport"},
    "vendor":  {"national_id", "passport"},
    "student": {"national_id", "birth_certificate"},
    "admin":   {"national_id", "passport"},
    "owner":   {"national_id", "passport"},
}


def _check_identity_document(person, role_type):
    """
    Returns (ok: bool, error_message: str | None).
    ok=True means the person has at least one document satisfying the
    role's identity requirement. ok=False means they do not.
    """
    required_types = _REQUIRED_IDENTITY_DOCS.get(role_type)
    if not required_types:
        # admin, owner, unknown roles — no document requirement
        return True, None

    has_required = IdentityDocument.objects.filter(
        person=person,
        document_type__in=required_types,
    ).exists()

    if not has_required:
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


# ─────────────────────────────────────────────
# Views
# ─────────────────────────────────────────────

class MyProfileView(generics.RetrieveUpdateAPIView):
    """
    GET  /api/profile/me/  — returns Person + User fields
    PATCH /api/profile/me/ — updates Person fields

    PATCH allowed when status is PENDING, WAITING_APPROVAL, or REJECTED.
    """
    permission_classes = [HasValidToken]
    serializer_class   = PersonSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['request'] = self.request
        return ctx

    def get_object(self):
        try:
            return Person.objects.select_related(
                'user', 'user__membership', 'user__membership__role'
            ).get(user=self.request.user)
        except Person.DoesNotExist:
            raise NotFound("Profile not found.")

    def partial_update(self, request, *args, **kwargs):
        membership = getattr(request.user, 'membership', None)
        if not membership:
            return Response({'detail': 'No membership found.'}, status=403)

        editable_statuses = [
            MembershipStatus.PENDING,
            MembershipStatus.WAITING_APPROVAL,
            MembershipStatus.REJECTED,
        ]
        if membership.status not in editable_statuses:
            return Response(
                {'detail': 'Profile cannot be edited at this time.'},
                status=403,
            )
        return super().partial_update(request, *args, **kwargs)


class MyDocumentsView(generics.ListCreateAPIView):
    """
    GET  /api/profile/me/documents/  — list all documents for this person
    POST /api/profile/me/documents/  — upload a new document

    Accepts multipart/form-data. Each POST creates one document row.
    The frontend submits one document at a time per role type.
    """
    permission_classes = [HasValidToken]
    serializer_class   = IdentityDocumentSerializer
    parser_classes     = [parsers.MultiPartParser, parsers.FormParser]

    def _get_person(self):
        try:
            return Person.objects.get(user=self.request.user)
        except Person.DoesNotExist:
            raise NotFound("Profile not found.")

    def get_queryset(self):
        person = self._get_person()
        return IdentityDocument.objects.filter(person=person).order_by('created_at')

    def perform_create(self, serializer):
        person = self._get_person()
        serializer.save(person=person)


class MyDocumentDetailView(generics.DestroyAPIView):
    """
    DELETE /api/profile/me/documents/<id>/

    Allows the user to remove a document they uploaded while their
    profile is still editable (PENDING, WAITING_APPROVAL, REJECTED).
    Verified documents (is_verified=True) cannot be deleted.
    """
    permission_classes = [HasValidToken]
    serializer_class   = IdentityDocumentSerializer

    def get_object(self):
        try:
            person = Person.objects.get(user=self.request.user)
        except Person.DoesNotExist:
            raise NotFound("Profile not found.")

        try:
            doc = IdentityDocument.objects.get(pk=self.kwargs['pk'], person=person)
        except IdentityDocument.DoesNotExist:
            raise NotFound("Document not found.")

        return doc

    def destroy(self, request, *args, **kwargs):
        membership = getattr(request.user, 'membership', None)
        if not membership:
            return Response({'detail': 'No membership found.'}, status=403)

        editable_statuses = [
            MembershipStatus.PENDING,
            MembershipStatus.WAITING_APPROVAL,
            MembershipStatus.REJECTED,
        ]
        if membership.status not in editable_statuses:
            return Response(
                {'detail': 'Documents cannot be removed at this time.'},
                status=403,
            )

        doc = self.get_object()
        if doc.is_verified:
            return Response(
                {'detail': 'Verified documents cannot be deleted.'},
                status=400,
            )

        doc.delete()
        return Response(status=204)


class MyGuardiansView(generics.ListCreateAPIView):
    """
    GET  /api/profile/me/guardians/
    POST /api/profile/me/guardians/
    Students only.
    """
    permission_classes = [HasValidToken]
    serializer_class   = GuardianSerializer

    def _get_person(self):
        try:
            return Person.objects.get(user=self.request.user)
        except Person.DoesNotExist:
            raise NotFound("Profile not found.")

    def get_queryset(self):
        person = self._get_person()
        if person.role_type != "student":
            return Guardian.objects.none()
        return Guardian.objects.filter(person=person)

    def list(self, request, *args, **kwargs):
        person = self._get_person()
        if person.role_type != "student":
            return Response(
                {"detail": "Only students have guardians."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        person = self._get_person()
        if person.role_type != "student":
            return Response(
                {"detail": "Only students can add guardians."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        person = self._get_person()
        serializer.save(person=person)