import logging
from rest_framework.permissions import BasePermission
from rest_framework.exceptions import NotAuthenticated, PermissionDenied

logger = logging.getLogger(__name__)

class IsSysAdmin(BasePermission):
    """
    Checks if the user has a valid sys admin session context.
    Validates the DB membership and ensures the org is active.
    Sets request.sys_admin_user and request.sys_admin_org on success.
    """
    def has_permission(self, request, view):
        if not hasattr(request, 'session'):
            return False
            
        is_sys_admin = request.session.get('is_sys_admin', False)
        org_slug = request.session.get('org_slug')
        user_id = request.session.get('user_id')
        
        if not is_sys_admin:
            raise NotAuthenticated(detail="System admin session required.")
            
        if not org_slug or not user_id:
            raise NotAuthenticated(detail="Session is incomplete. Please log in again.")
            
        from Users.models.membership import OrgMembership, MembershipStatus
        
        try:
            membership = (
                OrgMembership.objects
                .select_related("user", "org")
                .get(
                    user_id=user_id,
                    is_system_admin=True,
                    status=MembershipStatus.ACTIVE,
                    org__slug=org_slug,
                )
            )
        except OrgMembership.DoesNotExist:
            logger.warning(
                "Sys-admin permission denied: user_id=%s has no active system-admin "
                "membership for org '%s'.", user_id, org_slug
            )
            request.session.flush()
            raise PermissionDenied(detail="Access denied. Your session is no longer valid.")
            
        if not membership.org.is_active:
            raise PermissionDenied(detail="Your organisation is currently inactive.")
            
        # Attach to request for views to use
        request.sys_admin_user = membership.user
        request.sys_admin_org = membership.org
        
        return True
