import csv
from datetime import datetime
from django.db.models import Q
from django.http import HttpResponse

from rest_framework import generics, views
from rest_framework.response import Response

from Orgs.models import Organization, OrgActivityLog
from Orgs.serializers import OrgActivityLogSerializer
from Orgs.permissions import IsSysAdmin

class OrgActivityLogFilterMixin:
    """
    Mixin for extracting filters from query params and safely scoping to the org.
    """
    def get_queryset(self):
        org_slug = self.request.session.get('org_slug')
        
        # Safe-guard: guarantee we only get logs for the active org
        qs = OrgActivityLog.objects.filter(org__slug=org_slug)

        query_params = self.request.query_params
        category = query_params.get('category')
        actor_id = query_params.get('actor_id')
        severity = query_params.get('severity')
        date_from = query_params.get('date_from')
        date_to = query_params.get('date_to')
        search = query_params.get('search')

        if category and category.lower() != 'all':
            qs = qs.filter(category__iexact=category)
        
        if severity and severity.lower() != 'all':
            qs = qs.filter(severity__iexact=severity)

        if actor_id and actor_id.lower() != 'all':
            qs = qs.filter(actor_id=actor_id)

        if date_from:
            try:
                # filter created_at__date >= date_from
                # using __gte to support timezone matching correctly
                d = datetime.strptime(date_from, "%Y-%m-%d").date()
                qs = qs.filter(created_at__date__gte=d)
            except ValueError:
                pass

        if date_to:
            try:
                d = datetime.strptime(date_to, "%Y-%m-%d").date()
                qs = qs.filter(created_at__date__lte=d)
            except ValueError:
                pass

        if search:
            qs = qs.filter(
                Q(actor_name__icontains=search) |
                Q(actor_email__icontains=search) |
                Q(action__icontains=search)
            )

        return qs

class OrgActivityLogListView(OrgActivityLogFilterMixin, generics.ListAPIView):
    """
    Paginated endpoint for all org-scoped logs.
    """
    permission_classes = [IsSysAdmin]
    serializer_class = OrgActivityLogSerializer

class OrgActivityLogExportView(OrgActivityLogFilterMixin, views.APIView):
    """
    Exports filtered logs as a CSV file.
    Max 10000 rows.
    """
    permission_classes = [IsSysAdmin]

    def get(self, request, *args, **kwargs):
        qs = self.get_queryset()[:10000] # Hard cap

        org_slug = request.session.get('org_slug', 'unknown')
        date_str = datetime.now().strftime('%Y-%m-%d')
        filename = f"org-logs-{org_slug}-{date_str}.csv"

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        writer = csv.writer(response)
        writer.writerow([
            'Timestamp', 'Actor Name', 'Actor Email', 'Category',
            'Severity', 'Action', 'IP Address', 'User Agent', 'Session ID'
        ])

        for log in qs:
            writer.writerow([
                log.created_at.isoformat(),
                log.actor_name,
                log.actor_email,
                log.category.upper(),
                log.severity.upper(),
                log.action,
                log.ip_address or 'N/A',
                log.user_agent or 'N/A',
                log.session_id[-8:] if log.session_id else 'N/A'
            ])

        return response

class OrgActivityLogActorsView(views.APIView):
    """
    Returns unique actors that have generated logs in this org.
    Used for the dropdown filter.
    """
    permission_classes = [IsSysAdmin]

    def get(self, request, *args, **kwargs):
        org_slug = request.session.get('org_slug')
        
        # Query distinct non-null actor IDs mapping to denormalized names
        logs = OrgActivityLog.objects.filter(org__slug=org_slug, actor__isnull=False) \
                    .values('actor_id', 'actor_name', 'actor_email') \
                    .distinct()

        # Deduplicate explicitly if values() returns multiple variants
        seen = set()
        results = []
        for v in logs:
            if v['actor_id'] not in seen:
                seen.add(v['actor_id'])
                results.append({
                    "id": v['actor_id'],
                    "full_name": v['actor_name'],
                    "email": v['actor_email']
                })

        return Response(results)
