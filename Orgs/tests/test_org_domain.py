from django.test import TestCase
from django.db.utils import IntegrityError
from django.db import transaction
from Orgs.models import OrgDomain, Organization
from .factories import make_org, make_domain

class OrgDomainTests(TestCase):
    def test_creates_with_is_primary_true(self):
        org = make_org()
        domain = make_domain(org, domain="school.edu", is_primary=True)
        self.assertEqual(domain.org, org)
        self.assertTrue(domain.is_primary)

    def test_creates_alias_domain_with_is_primary_false(self):
        org = make_org()
        domain = make_domain(org, domain="alias.edu", is_primary=False)
        self.assertEqual(domain.org, org)
        self.assertFalse(domain.is_primary)

    def test_rejects_two_primary_domains_for_same_org(self):
        org = make_org()
        make_domain(org, domain="first.edu", is_primary=True)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                make_domain(org, domain="second.edu", is_primary=True)

    def test_allows_two_orgs_to_each_have_their_own_primary_domain(self):
        org1 = make_org(slug="org1")
        org2 = make_org(slug="org2")
        d1 = make_domain(org1, domain="one.edu", is_primary=True)
        d2 = make_domain(org2, domain="two.edu", is_primary=True)
        self.assertTrue(d1.is_primary)
        self.assertTrue(d2.is_primary)

    def test_rejects_duplicate_domain_string_across_different_orgs(self):
        org1 = make_org(slug="org1")
        org2 = make_org(slug="org2")
        make_domain(org1, domain="shared.edu")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                make_domain(org2, domain="shared.edu")

    def test_resolve_org_returns_correct_org_for_verified_active_domain(self):
        org = make_org(is_active=True)
        make_domain(org, domain="verified.edu", is_verified=True)
        resolved = OrgDomain.resolve_org("verified.edu")
        self.assertEqual(resolved, org)

    def test_resolve_org_returns_none_for_unverified_domain(self):
        org = make_org(is_active=True)
        make_domain(org, domain="unverified.edu", is_verified=False)
        self.assertIsNone(OrgDomain.resolve_org("unverified.edu"))

    def test_resolve_org_returns_none_for_inactive_org(self):
        org = make_org(is_active=False)
        make_domain(org, domain="inactive.edu", is_verified=True)
        self.assertIsNone(OrgDomain.resolve_org("inactive.edu"))

    def test_resolve_org_returns_none_for_unknown_domain_string(self):
        self.assertIsNone(OrgDomain.resolve_org("unknown.edu"))

    def test_str_includes_domain_primary_alias_tag_verified_tag_org_slug(self):
        org = make_org(slug="my-org")
        
        d1 = make_domain(org, domain="main.edu", is_primary=True, is_verified=True)
        s1 = str(d1)
        self.assertIn("main.edu", s1)
        self.assertIn("PRIMARY", s1.upper())
        self.assertIn("[✓]", s1)
        self.assertIn("my-org", s1)

        d2 = make_domain(org, domain="alias.edu", is_primary=False, is_verified=False)
        s2 = str(d2)
        self.assertIn("alias.edu", s2)
        self.assertIn("alias", s2.lower())
        self.assertIn("unverified", s2.lower())
        self.assertIn("my-org", s2)
