"""
Orgs/views/sub_org_views.py
-----------------------------
CRUD views for SubOrganization.

Auth: every request is validated via _get_sys_admin_context(), which
ensures the caller is an active system admin for their org only.
Cross-org access is structurally impossible.
"""

import logging

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from Orgs.models.sub_organization import SubOrganization
from Orgs.serializers import SubOrganizationSerializer, SubOrganizationWriteSerializer

from Orgs.permissions import IsSysAdmin
from Orgs.utils.logger import log_org_activity

logger = logging.getLogger(__name__)


class SubOrgListCreateView(APIView):
    """
    GET  /api/org/sub-orgs/   — List all sub-orgs for the sys admin's org.
    POST /api/org/sub-orgs/   — Create a new sub-org.

    Query params for GET:
        ?include_inactive=true   — also return inactive sub-orgs (default: active only)
    """
    authentication_classes = []
    permission_classes     = [IsSysAdmin]

    def get(self, request):
        org = request.sys_admin_org
        qs  = SubOrganization.objects.filter(parent_org=org)

        if request.query_params.get("include_inactive") != "true":
            qs = qs.filter(is_active=True)

        serializer = SubOrganizationSerializer(qs, many=True)
        return Response(serializer.data)

    def post(self, request):
        org = request.sys_admin_org

        serializer = SubOrganizationWriteSerializer(
            data=request.data,
            context={"parent_org": org},
        )
        if serializer.is_valid():
            sub_org = serializer.save(parent_org=org)
            log_org_activity(
                org=org, actor=request.sys_admin_user, category="system", severity="info",
                action=f"Sub-organization '{sub_org.name}' created", request=request
            )
            logger.info(
                "SubOrg created: org='%s' code='%s' by user_id=%s",
                org.slug, sub_org.code, request.session.get("user_id"),
            )
            return Response(
                SubOrganizationSerializer(sub_org).data,
                status=status.HTTP_201_CREATED,
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SubOrgDetailView(APIView):
    """
    GET    /api/org/sub-orgs/<code>/   — Retrieve a sub-org.
    PATCH  /api/org/sub-orgs/<code>/   — Partial update (name, description, type, active).
    DELETE /api/org/sub-orgs/<code>/   — Soft-delete (sets is_active=False).
    """
    authentication_classes = []
    permission_classes     = [IsSysAdmin]

    def _get_sub_org(self, request, code):
        """Helper to fetch sub_org ensuring it belongs to the sys admin's org."""
        return get_object_or_404(
            SubOrganization,
            code=code,
            parent_org=request.sys_admin_org,   # ← org-ownership check
        )

    def get(self, request, code):
        sub_org = self._get_sub_org(request, code)
        return Response(SubOrganizationSerializer(sub_org).data)

    def patch(self, request, code):
        sub_org = self._get_sub_org(request, code)
        org = request.sys_admin_org

        serializer = SubOrganizationWriteSerializer(
            sub_org,
            data=request.data,
            partial=True,
            context={"parent_org": org},
        )
        if serializer.is_valid():
            serializer.save()
            logger.info(
                "SubOrg updated: org='%s' code='%s' by user_id=%s",
                org.slug, code, request.session.get("user_id"),
            )
            return Response(SubOrganizationSerializer(serializer.instance).data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, code):
        """Soft-delete: sets is_active=False instead of hard-deleting."""
        sub_org = self._get_sub_org(request, code)
        org = request.sys_admin_org

        sub_org.is_active = False
        sub_org.save(update_fields=["is_active", "updated_at"])
        log_org_activity(
            org=org, actor=request.sys_admin_user, category="system", severity="warning",
            action=f"Sub-organization '{code}' deactivated", request=request
        )
        logger.info(
            "SubOrg deactivated: org='%s' code='%s' by user_id=%s",
            org.slug, code, request.session.get("user_id"),
        )
        return Response(
            {"detail": f"Sub-organization '{code}' has been deactivated."},
            status=status.HTTP_200_OK,
        )
