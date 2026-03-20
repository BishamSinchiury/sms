"""
create_org_and_admin.py
-----------------------
Management command to provision a new organization and its system admin in one step.

What this command does (in a single atomic transaction):
    1. Creates the Organization with the given slug.
    2. Seeds the 3 system OrgRoles: system_admin, admin, member.
    3. Creates the User (or uses an existing one by email).
    4. Creates OrgMembership with:
           - is_system_admin = True
           - status          = ACTIVE
           - role            = system_admin OrgRole

Usage:
    python manage.py create_org_and_admin \\
        --slug "bisham-org" \\
        --email "bishamsinchiury1116@gmail.com" \\
        --password "Bisham@0411" \\
        --first-name "Bisham" \\
        --last-name "Sinchiury"

    # Password can be omitted — the command will prompt for it interactively.

Safety:
    - Wrapped in db.transaction.atomic() — any failure rolls back everything.
    - Refuses to run if the slug already exists (use --force to override check).
    - Refuses to assign an email that already has an OrgMembership.
"""

import getpass

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from Orgs.models import Organization, OrganizationProfile, OrganizationLegal
from Users.models.user import User
from Users.models.roles import OrgRole, SYSTEM_ADMIN_ROLE, ADMIN_ROLE, MEMBER_ROLE
from Users.models.membership import OrgMembership, MembershipStatus


class Command(BaseCommand):
    help = (
        "Provision a new Organization and its System Admin user in one atomic step. "
        "Also seeds the 3 system roles (system_admin, admin, member) and creates "
        "blank OrganizationProfile and OrganizationLegal records."
    )

    # ─────────────────────────────────────────────
    # Argument definition
    # ─────────────────────────────────────────────

    def add_arguments(self, parser):
        parser.add_argument(
            "--slug",
            required=True,
            help="URL-safe org identifier (immutable). e.g. 'greenwood-high'",
        )
        parser.add_argument(
            "--email",
            required=True,
            help="Email address for the system admin user.",
        )
        parser.add_argument(
            "--password",
            default=None,
            help="Password for the system admin. Prompted interactively if omitted.",
        )
        parser.add_argument(
            "--first-name",
            default="",
            help="System admin's first name (optional).",
        )
        parser.add_argument(
            "--last-name",
            default="",
            help="System admin's last name (optional).",
        )

    # ─────────────────────────────────────────────
    # Entry point
    # ─────────────────────────────────────────────

    def handle(self, *args, **options):
        slug       = options["slug"].strip().lower()
        email      = options["email"].strip().lower()
        password   = options["password"]
        first_name = options["first_name"].strip()
        last_name  = options["last_name"].strip()

        # ── Validate slug format ──────────────────────────────────────────
        import re
        if not re.match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", slug):
            raise CommandError(
                f"Invalid slug '{slug}'. "
                "Use only lowercase letters, digits, and hyphens (e.g. 'greenwood-high')."
            )

        # ── Prompt for password if not supplied ───────────────────────────
        if not password:
            self.stdout.write("")
            password = getpass.getpass(f"Password for {email}: ")
            confirm  = getpass.getpass("Confirm password: ")
            if password != confirm:
                raise CommandError("Passwords do not match. Aborting.")

        if len(password) < 8:
            raise CommandError("Password must be at least 8 characters.")

        # ── Pre-flight checks (before opening the transaction) ────────────
        if Organization.objects.filter(slug=slug).exists():
            raise CommandError(
                f"Organization with slug '{slug}' already exists. "
                "Each org slug must be globally unique."
            )

        if User.objects.filter(email=email).exists():
            user = User.objects.get(email=email)
            if hasattr(user, "membership"):
                raise CommandError(
                    f"User '{email}' already belongs to an organization. "
                    "A user can only be the system admin of one org."
                )
            self.stdout.write(
                self.style.WARNING(
                    f"  User '{email}' already exists — will reuse and assign as system admin."
                )
            )

        # ── Atomic provisioning ───────────────────────────────────────────
        try:
            with transaction.atomic():
                org, user = self._provision(
                    slug, email, password, first_name, last_name
                )
        except Exception as exc:
            raise CommandError(f"Provisioning failed and was rolled back.\n  Reason: {exc}")

        # ── Success output ────────────────────────────────────────────────
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("✓ Organization provisioned successfully!"))
        self.stdout.write(self.style.SUCCESS(f"  Org slug      : {org.slug}"))
        self.stdout.write(self.style.SUCCESS(f"  System admin  : {user.email}"))
        self.stdout.write(self.style.SUCCESS(f"  Roles seeded  : system_admin, admin, member"))
        self.stdout.write("")
        self.stdout.write(
            "  Next steps:"
        )
        self.stdout.write(
            "    1. System admin logs in at /api/sys/auth/login/"
        )
        self.stdout.write(
            "    2. Fill in OrganizationProfile and OrganizationLegal via the sys dashboard."
        )
        self.stdout.write(
            "    3. Assign a domain via the sys dashboard or create_org_domain command."
        )
        self.stdout.write("")

    # ─────────────────────────────────────────────
    # Private helpers
    # ─────────────────────────────────────────────

    def _provision(self, slug, email, password, first_name, last_name):
        """
        Core provisioning logic — runs inside an atomic transaction.
        Returns (org, user).
        """

        # 1. Create Organization
        self.stdout.write(f"  Creating organization '{slug}' ...")
        org = Organization.objects.create(slug=slug, is_active=True)

        # 2. Seed system OrganizationProfile and OrganizationLegal (blank records)
        OrganizationProfile.objects.create(org=org, name=slug)
        OrganizationLegal.objects.create(org=org)
        self.stdout.write("  Created blank OrganizationProfile and OrganizationLegal.")

        # 4. Seed system OrgRoles
        self.stdout.write("  Seeding system roles ...")
        sys_admin_role = OrgRole.objects.create(
            org=org, name=SYSTEM_ADMIN_ROLE, is_system_role=True, role_type="system_admin",
            description="Reserved for the organization's designated system administrator.",
        )
        OrgRole.objects.create(
            org=org, name=ADMIN_ROLE, is_system_role=True, role_type="admin",
            description="Administrative role. Can manage users and most settings.",
        )
        OrgRole.objects.create(
            org=org, name=MEMBER_ROLE, is_system_role=True, role_type="staff",
            description="Base role for all organization members.",
        )

        # 4.5 Seed default custom roles
        self.stdout.write("  Seeding default custom roles ...")
        default_roles = [
            {"name": "Owner", "role_type": "owner", "description": "Owner of the organization."},
            {"name": "Student", "role_type": "student", "description": "General student role."},
            {"name": "Teacher", "role_type": "teacher", "description": "Faculty member role."},
            {"name": "Staff", "role_type": "staff", "description": "Administrative staff role."},
            {"name": "Parent", "role_type": "parent", "description": "Guardian of a student."},
        ]
        for role_data in default_roles:
            OrgRole.objects.create(
                org=org, name=role_data["name"], is_system_role=False,
                role_type=role_data["role_type"], description=role_data["description"]
            )

        # 5. Create or fetch the User
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "first_name": first_name,
                "last_name":  last_name,
                "is_active":  True,
            },
        )
        if created:
            user.set_password(password)
            user.save(update_fields=["password"])
            self.stdout.write(f"  Created user '{email}'.")
        else:
            # Existing user — still update password so the admin can log in
            user.set_password(password)
            user.save(update_fields=["password"])
            self.stdout.write(f"  Reusing existing user '{email}' (password updated).")

        # 5. Create OrgMembership as system admin
        self.stdout.write("  Creating system admin membership ...")
        OrgMembership.objects.create(
            user=user,
            org=org,
            role=sys_admin_role,
            status=MembershipStatus.ACTIVE,
            is_system_admin=True,
            approved_by=None,
        )

        return org, user
