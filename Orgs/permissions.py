from rest_framework.permissions import BasePermission

class IsSysAdmin(BasePermission):
    """
    Checks if the user has a valid sys admin session context.
    - session["is_sys_admin"] must be True
    - session["org_slug"] must not be None
    Requires a valid cookie-based session, separate from JWT.
    """
    def has_permission(self, request, view):
        # We check the session store attached to the request
        if not hasattr(request, 'session'):
            return False
            
        is_sys_admin = request.session.get('is_sys_admin', False)
        org_slug = request.session.get('org_slug')
        
        return bool(is_sys_admin and org_slug)
