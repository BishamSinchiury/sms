import logging
from django.db import models
from django.conf import settings
from .organization import Organization

class OrgActivityLog(models.Model):
    """
    Append-only audit log for organization scoped events.
    """
    CATEGORY_CHOICES = (
        ('auth', 'Auth'),
        ('membership', 'Membership'),
        ('org_changes', 'Org Changes'),
        ('system', 'System'),
    )

    SEVERITY_CHOICES = (
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('critical', 'Critical'),
    )

    org = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="activity_logs"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="org_activity_logs"
    )
    actor_email = models.CharField(max_length=255, blank=True)
    actor_name = models.CharField(max_length=255, blank=True)

    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    severity = models.CharField(max_length=50, choices=SEVERITY_CHOICES)
    
    action = models.CharField(max_length=255)
    detail = models.JSONField(default=dict, blank=True)

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    session_id = models.CharField(max_length=40, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        app_label = "Orgs"
        db_table = "org_activity_logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["org", "-created_at"]),
            models.Index(fields=["org", "category"]),
            models.Index(fields=["org", "severity"]),
            models.Index(fields=["actor"]),
        ]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("OrgActivityLog entries are immutable and cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("OrgActivityLog entries cannot be deleted.")

    def __str__(self):
        return f"[{self.category.upper()}] {self.severity.upper()} - {self.action} ({self.created_at.isoformat()})"
