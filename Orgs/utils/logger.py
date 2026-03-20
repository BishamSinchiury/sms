import logging
from django.utils import timezone
from Orgs.models import Organization, OrgActivityLog

logger = logging.getLogger(__name__)

def log_org_activity(org, actor, category, severity, action, detail=None, request=None):
    """
    Safely writes an append-only log entry for organization activities.
    Fails safely — if an exception occurs during writing, it is caught
    and sent to standard python logger to prevent breaking the request cycle.
    """
    try:
        ip_address = None
        user_agent = ""
        session_id = ""
        
        if request:
            # Extract IP
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip_address = x_forwarded_for.split(',')[0].strip()
            else:
                ip_address = request.META.get('REMOTE_ADDR')
            
            # Extract User Agent
            user_agent = request.META.get('HTTP_USER_AGENT', '')
            
            # Extract Session Key
            if hasattr(request, 'session') and request.session.session_key:
                session_id = request.session.session_key[-8:]
                
        actor_email = ""
        actor_name = ""
        
        if actor:
            actor_email = getattr(actor, 'email', '')
            # Try to build full name intelligently, fallback to first_name/last_name
            if hasattr(actor, 'get_full_name'):
                actor_name = actor.get_full_name()
            else:
                fname = getattr(actor, 'first_name', '')
                lname = getattr(actor, 'last_name', '')
                actor_name = f"{fname} {lname}".strip() or actor_email
                
            if not actor_name:
                actor_name = "System Auto"
        
        OrgActivityLog.objects.create(
            org=org,
            actor=actor,
            actor_email=actor_email,
            actor_name=actor_name,
            category=category,
            severity=severity,
            action=action,
            detail=detail or {},
            ip_address=ip_address,
            user_agent=user_agent,
            session_id=session_id
        )
    except Exception as e:
        logger.error(f"Failed to write OrgActivityLog: {str(e)}", exc_info=True)
