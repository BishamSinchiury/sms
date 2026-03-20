from django.test import TestCase
from django.db.utils import IntegrityError
from django.core.exceptions import ValidationError
from django.db import transaction
from Orgs.models import Organization
from .factories import make_org, make_profile, make_domain

class OrganizationTests(TestCase):
    def test_creates_with_valid_slug(self):
        org = make_org(slug="valid-slug")
        self.assertEqual(org.slug, "valid-slug")

    def test_rejects_duplicate_slug(self):
        make_org(slug="dup-slug")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                make_org(slug="dup-slug")

    def test_rejects_blank_slug(self):
        org = Organization(slug="")
        with self.assertRaises(ValidationError):
            org.full_clean()

    def test_is_active_defaults_to_true(self):
        org = make_org()
        self.assertTrue(org.is_active)

    def test_deactivated_at_and_reason_start_empty(self):
        org = make_org()
        self.assertIsNone(org.deactivated_at)
        self.assertEqual(org.deactivation_reason, "")

    def test_str_returns_slug(self):
        org = make_org(slug="my-org")
        self.assertEqual(str(org), "my-org")

    def test_name_property_returns_profile_name(self):
        org = make_org(slug="test-org")
        make_profile(org, name="A Great School")
        self.assertEqual(org.name, "A Great School")

    def test_name_property_returns_slug_when_no_profile_exists(self):
        org = make_org(slug="test-org")
        # Removing any auto-created profiles
        if hasattr(org, "profile"):
            org.profile.delete()
        org.refresh_from_db()
        self.assertEqual(org.name, "test-org")

    def test_primary_domain_returns_domain(self):
        org = make_org()
        domain = make_domain(org, domain="school.edu", is_primary=True, is_verified=True)
        self.assertEqual(org.primary_domain, domain)

    def test_primary_domain_returns_none(self):
        org = make_org()
        self.assertIsNone(org.primary_domain)

    def test_get_domain_list_empty(self):
        org = make_org()
        self.assertEqual(list(org.get_domain_list()), [])

    def test_get_domain_list_populated(self):
        org = make_org()
        domain1 = make_domain(org, domain="alias.edu", is_primary=False, is_verified=True)
        domain2 = make_domain(org, domain="main.edu", is_primary=True, is_verified=True)
        domains = list(org.get_domain_list())
        self.assertEqual(len(domains), 2)
        # Primary should be first (and returns flat strings according to the method)
        self.assertEqual(domains[0], "main.edu")
        self.assertEqual(domains[1], "alias.edu")
