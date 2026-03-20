"""
seed_default_roles.py
---------------------
Seeds the default custom roles (Student, Teacher, Staff) for all existing organizations
that don't already have them.

Usage:
    python manage.py seed_default_roles
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from Orgs.models import Organization
from Users.models.roles import OrgRole

DEFAULT_ROLES = [
    {
        "name": "Student",
        "description": "General student role with access to courses and grades."
    },
    {
        "name": "Teacher",
        "description": "Faculty member role with permissions to manage classes and grade students."
    },
    {
        "name": "Staff",
        "description": "Administrative staff role."
    }
]

class Command(BaseCommand):
    help = "Seeds default custom roles (Student, Teacher, Staff) for all existing organizations."

    def handle(self, *args, **options):
        orgs = Organization.objects.all()
        if not orgs.exists():
            self.stdout.write(self.style.WARNING("No organizations found to seed roles for."))
            return

        seeded_count = 0
        with transaction.atomic():
            for org in orgs:
                for role_data in DEFAULT_ROLES:
                    role, created = OrgRole.objects.get_or_create(
                        org=org,
                        name=role_data["name"],
                        defaults={
                            "is_system_role": False,
                            "description": role_data["description"]
                        }
                    )
                    if created:
                        seeded_count += 1
                        self.stdout.write(f"Created role '{role.name}' for org '{org.slug}'.")

        self.stdout.write(self.style.SUCCESS(f"Successfully seeded {seeded_count} default roles."))
