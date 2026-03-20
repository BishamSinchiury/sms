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

from Users.models.membership import OrgMembership, MembershipStatus
from Orgs.models.organization import Organization
from Orgs.models.profile import OrganizationProfile
from Orgs.serializers import OrganizationProfileSerializer

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Shared permission helper
# ─────────────────────────────────────────────────────────────────────────────

def _get_sys_admin_context(request):
    """
    Validates the incoming request is from an active system-admin session
    that belongs to a real, active organisation.

    Returns one of:
        dict  — { "user": User, "org": Organization } on success
        Response — 401/403 DRF Response on failure

    Security checks (in order):
    1. Session flag: session["is_sys_admin"] must be True.
    2. Session data: org_slug and user_id must be present.
    3. DB check: OrgMembership must exist with
           is_system_admin=True + status=ACTIVE + org__slug matching session.
       This is the critical guard: it ties the session claim to a real DB record
       and ensures cross-org access is impossible even if session data is tampered.
    4. Org is_active check.
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()

    # ── 1. Session flag ───────────────────────────────────────────────────────
    if not request.session.get("is_sys_admin"):
        return Response(
            {"detail": "System admin session required."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    org_slug = request.session.get("org_slug")
    user_id  = request.session.get("user_id")

    if not org_slug or not user_id:
        return Response(
            {"detail": "Session is incomplete. Please log in again."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    # ── 2. Verify user + membership in DB ────────────────────────────────────
    try:
        membership = (
            OrgMembership.objects
            .select_related("user", "org")
            .get(
                user_id=user_id,
                is_system_admin=True,
                status=MembershipStatus.ACTIVE,
                org__slug=org_slug,        # ← org-ownership check
            )
        )
    except OrgMembership.DoesNotExist:
        logger.warning(
            "Sys-admin permission denied: user_id=%s has no active system-admin "
            "membership for org '%s'.", user_id, org_slug
        )
        request.session.flush()  # Invalidate stale/tampered session
        return Response(
            {"detail": "Access denied. Your session is no longer valid."},
            status=status.HTTP_403_FORBIDDEN,
        )

    # ── 3. Org must be active ─────────────────────────────────────────────────
    if not membership.org.is_active:
        return Response(
            {"detail": "Your organisation is currently inactive."},
            status=status.HTTP_403_FORBIDDEN,
        )

    return {"user": membership.user, "org": membership.org}


# ─────────────────────────────────────────────────────────────────────────────
# Views
# ─────────────────────────────────────────────────────────────────────────────

class OrgProfileMeView(APIView):
    """
    GET  /api/org/profile/me/   — Retrieve own org's profile
    PATCH /api/org/profile/me/  — Partial update own org's profile

    Both methods are scoped to the org stored in the session.
    Cross-org access is impossible by design.
    """
    authentication_classes = []
    permission_classes     = []

    def get(self, request):
        ctx = _get_sys_admin_context(request)
        if isinstance(ctx, Response):
            return ctx

        org = ctx["org"]

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
        ctx = _get_sys_admin_context(request)
        if isinstance(ctx, Response):
            return ctx

        org = ctx["org"]

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
                actor=ctx.get("user"),
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
