from django.contrib import admin
from .models.activity_log import OrgActivityLog

@admin.register(OrgActivityLog)
class OrgActivityLogAdmin(admin.ModelAdmin):
    list_display = ('org', 'actor_email', 'category', 'severity', 'action', 'created_at')
    list_filter = ('category', 'severity', 'org')
    search_fields = ('actor_email', 'actor_name', 'action')
    readonly_fields = (
        'org', 'actor', 'actor_email', 'actor_name', 'category',
        'severity', 'action', 'detail', 'ip_address', 'user_agent',
        'session_id', 'created_at'
    )
    ordering = ('-created_at',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
