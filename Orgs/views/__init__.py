"""
Orgs/views/__init__.py
-----------------------
Public surface for the Orgs views package.

Exports OrgProfileMeView and _get_sys_admin_context so that:
  - urls.py can do:  from .views import OrgProfileMeView
  - sub_org_views.py can do: from Orgs.views import _get_sys_admin_context
"""

import logging

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from Orgs.utils.logger import log_org_activity
from Orgs.permissions import IsSysAdmin

from Users.models.membership import OrgMembership, MembershipStatus
from Orgs.models.organization import Organization
from Orgs.models.profile import OrganizationProfile
from Orgs.models.legal import OrganizationLegal
from Orgs.serializers import OrganizationProfileSerializer, OrganizationLegalSerializer

from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework import status
from Orgs.permissions import IsSysAdmin
from Orgs.models.owner import OrgOwner
from Orgs.serializers import OrgOwnerSerializer

logger = logging.getLogger(__name__)

class OrgProfileMeView(APIView):
    """
    GET  /api/org/profile/me/   — Retrieve own org's profile
    PATCH /api/org/profile/me/  — Partial update own org's profile
    Both methods are scoped to the org stored in the session.
    Cross-org access is impossible by design.
    """
    # FIX 12 (BUG 14): Removed authentication_classes = []. Django's default
    # JWTAuthentication now runs as a safety net. IsSysAdmin still handles
    # session-based auth via request.session — this just adds a fallback layer.
    permission_classes     = [IsSysAdmin]

    def get(self, request):
        org = request.sys_admin_org

        profile = getattr(org, "profile", None)
        if not profile:
            return Response(
                {"detail": "Organisation profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = OrganizationProfileSerializer(
            profile, context={"request": request}
        )
        return Response(serializer.data)

    def patch(self, request):
        """
        Partial update — supports multipart/form-data for image uploads.
        Only the sys-admin of THIS org can call this.
        """
        org = request.sys_admin_org

        profile, _ = OrganizationProfile.objects.get_or_create(org=org)

        serializer = OrganizationProfileSerializer(
            profile,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        if serializer.is_valid():
            old_values = {field: getattr(profile, field, None) for field in serializer.validated_data}
            serializer.save()
            
            changed_fields = {}
            for field, new_val in serializer.validated_data.items():
                old_val = old_values[field]
                if str(old_val) != str(new_val):
                    changed_fields[field] = {
                        "old_value": str(old_val),
                        "new_value": str(new_val)
                    }

            log_org_activity(
                org=org,
                actor=request.sys_admin_user,
                category="org_changes",
                severity="info",
                action="Organization profile updated",
                detail={"fields_changed": changed_fields} if changed_fields else {},
                request=request
            )

            logger.info(
                "OrgProfile updated: org='%s' by user_id=%s",
                org.slug, request.session.get("user_id"),
            )
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class OrgLegalMeView(APIView):
    """
    GET  /api/org/legal/me/   — Retrieve own org's legal config
    PATCH /api/org/legal/me/  — Partial update own org's legal config

    Scoped to the org stored in the session by IsSysAdmin.
    """
    # FIX 12 (BUG 14): Removed authentication_classes = [] — same reasoning as OrgProfileMeView.
    permission_classes     = [IsSysAdmin]

    def get(self, request):
        org = request.sys_admin_org

        legal = getattr(org, "legal", None)
        if not legal:
            return Response(
                {"detail": "Organisation legal configuration not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = OrganizationLegalSerializer(
            legal, context={"request": request}
        )
        return Response(serializer.data)

    def patch(self, request):
        org = request.sys_admin_org

        legal, _ = OrganizationLegal.objects.get_or_create(org=org)

        serializer = OrganizationLegalSerializer(
            legal,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        if serializer.is_valid():
            serializer.save()

            log_org_activity(
                org=org,
                actor=request.sys_admin_user,
                category="org_changes",
                severity="warning", # compliance changes usually warn
                action="Organization legal config updated",
                request=request
            )

            logger.info(
                "OrgLegal updated: org='%s' by user_id=%s",
                org.slug, request.session.get("user_id"),
            )
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)





class OrgOwnerListCreateView(APIView):
    """
    GET  /api/sys/owners/
        List all owners for the session org.
        Sensitive ID numbers are excluded from list responses.

    POST /api/sys/owners/
        Create a new owner for the session org.
        Accepts multipart/form-data for document file uploads.

    Org is always request.sys_admin_org — attached by IsSysAdmin.
    Never read org from request.data or URL kwargs.
    """

    permission_classes = [IsSysAdmin]
    # Accept both multipart (file uploads) and JSON
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        org = request.sys_admin_org

        owners = OrgOwner.objects.filter(org=org).select_related(
            "user"  # avoid N+1 on user_email field
        ).order_by("-is_primary", "full_legal_name")

        serializer = OrgOwnerSerializer(
            owners,
            many=True,
            context={
                "request": request,
                "org": org,
                "detail": False,  # sensitive numbers excluded in list
            },
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        org = request.sys_admin_org

        serializer = OrgOwnerSerializer(
            data=request.data,
            context={
                "request": request,
                "org": org,
                "detail": True,  # return full data including numbers on create
            },
        )

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # org is always forced from session — client cannot supply it
        serializer.save(org=org)

        return Response(serializer.data, status=status.HTTP_201_CREATED)


class OrgOwnerDetailView(APIView):
    """
    GET    /api/sys/owners/<pk>/   — retrieve single owner (includes ID numbers)
    PATCH  /api/sys/owners/<pk>/   — partial update, supports file uploads
    DELETE /api/sys/owners/<pk>/   — delete (primary owner blocked)

    Cross-org access returns 404 not 403 to avoid leaking record existence.
    Org is always request.sys_admin_org — never from URL or request body.
    """
    permission_classes = [IsSysAdmin]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def _get_owner(self, pk, org):
        """
        Fetch owner scoped strictly to org.
        Returns None if not found or belongs to a different org.
        """
        try:
            return OrgOwner.objects.select_related("user").get(pk=pk, org=org)
        except OrgOwner.DoesNotExist:
            return None

    def get(self, request, pk):
        org = request.sys_admin_org
        owner = self._get_owner(pk, org)

        if owner is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = OrgOwnerSerializer(
            owner,
            context={
                "request": request,
                "org": org,
                "detail": True,  # sensitive ID numbers included in detail
            },
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request, pk):
        org = request.sys_admin_org
        owner = self._get_owner(pk, org)

        if owner is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = OrgOwnerSerializer(
            owner,
            data=request.data,
            partial=True,  # PATCH — only update provided fields
            context={
                "request": request,
                "org": org,
                "detail": True,
            },
        )

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # org is read_only in the serializer — cannot be overwritten by client
        serializer.save()

        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, pk):
        org = request.sys_admin_org
        owner = self._get_owner(pk, org)

        if owner is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if owner.is_primary:
            return Response(
                {
                    "detail": (
                        "Cannot delete the primary owner. "
                        "Assign another owner as primary first, "
                        "then delete this one."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        owner.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)