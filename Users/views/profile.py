"""
profile.py
----------
Endpoints for managing the current user's Person profile.
"""
from rest_framework import generics, parsers, status
from rest_framework.response import Response
from rest_framework.exceptions import NotFound
from Users.permissions import HasValidToken

from Users.models.person import Person, IdentityDocument, Guardian
from Users.serializers.person import PersonSerializer, IdentityDocumentSerializer, GuardianSerializer

class MyProfileView(generics.RetrieveUpdateAPIView):
    """
    GET /api/profile/me/
    PATCH /api/profile/me/
    """
    permission_classes = [HasValidToken]
    serializer_class = PersonSerializer

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
            raise NotFound("Profile not found. Please complete the registration wizard.")
        
    def partial_update(self, request, *args, **kwargs):
        membership = getattr(request.user, 'membership', None)
        if not membership:
            return Response({'detail': 'No membership found.'}, status=403)
        if membership.status not in ['rejected', 'pending']:
            return Response({'detail': 'Profile cannot be edited at this time.'}, status=403)
        return super().partial_update(request, *args, **kwargs)

class MyDocumentsView(generics.CreateAPIView):
    """
    POST /api/profile/me/documents/
    """
    permission_classes = [HasValidToken]
    serializer_class = IdentityDocumentSerializer
    parser_classes = [parsers.MultiPartParser, parsers.FormParser]

    def perform_create(self, serializer):
        try:
            person = Person.objects.get(user=self.request.user)
        except Person.DoesNotExist:
            raise NotFound("Complete your profile setup before uploading documents.")
        serializer.save(person=person)

class MyGuardiansView(generics.ListCreateAPIView):
    """
    GET /api/profile/me/guardians/
    POST /api/profile/me/guardians/
    """
    permission_classes = [HasValidToken]
    serializer_class = GuardianSerializer

    def get_queryset(self):
        try:
            person = Person.objects.get(user=self.request.user)
        except Person.DoesNotExist:
            return Guardian.objects.none()
        if person.role_type != "student":
            return Guardian.objects.none()
        return Guardian.objects.filter(person=person)

    def list(self, request, *args, **kwargs):
        try:
            person = Person.objects.get(user=request.user)
        except Person.DoesNotExist:
            raise NotFound("Profile not found.")
        if person.role_type != "student":
            return Response({"detail": "Only students have guardians."}, status=status.HTTP_403_FORBIDDEN)
        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        try:
            person = Person.objects.get(user=request.user)
        except Person.DoesNotExist:
            raise NotFound("Profile not found.")
        if person.role_type != "student":
            return Response({"detail": "Only students can add guardians."}, status=status.HTTP_403_FORBIDDEN)
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        try:
            person = Person.objects.get(user=self.request.user)
        except Person.DoesNotExist:
            raise NotFound("Profile not found.")
        serializer.save(person=person)
