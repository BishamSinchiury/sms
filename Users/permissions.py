from rest_framework.permissions import BasePermission
from rest_framework.exceptions import PermissionDenied

class IsApprovedMember(BasePermission):
    """
    Allows access only to users with an active membership.
    Returns 403 (not 401) for pending/suspended/rejected users.
    Use on all /app/ routes that require full access.
    """
    def has_permission(self, request, view):
        membership = getattr(request.user, 'membership', None)
        if not membership:
            raise PermissionDenied('No membership found.')
        if membership.status == 'active':
            return True
        raise PermissionDenied(
            f'Access restricted. Your account status is: {membership.status}.'
        )

class HasValidToken(BasePermission):
    """
    Allows access to any authenticated user regardless of membership status.
    Use on /setup/ routes (profile wizard, pending page, etc.)
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)
