from django.test import TestCase
from Orgs.models import Organization, OrganizationProfile, OrganizationLegal, OrgDomain, SubOrganization
from .factories import make_org, make_profile, make_legal, make_domain, make_sub_org

class OrganizationProvisioningTests(TestCase):
    def test_profile_can_be_created_immediately_after_org_creation_without_errors(self):
        org = make_org(slug="new-school")
        # Test creation doesn't fail due to missing fields (which it shouldn't, all are blank=True)
        profile = OrganizationProfile.objects.create(org=org)
        self.assertEqual(profile.org, org)
        self.assertEqual(profile.name, "")

    def test_attach_legal_profile_and_domain_records_to_one_org(self):
        org = make_org(slug="central-high")
        
        # Attach profile
        profile = make_profile(org, name="Central High School")
        
        # Attach legal
        legal = make_legal(org, owner_full_name="Jane Doe")
        
        # Attach domains
        domain1 = make_domain(org, domain="centralhigh.edu", is_primary=True, is_verified=True)
        domain2 = make_domain(org, domain="ch.edu", is_primary=False, is_verified=True)
        
        # Attach sub-orgs
        sub1 = make_sub_org(org, code="math")
        sub2 = make_sub_org(org, code="science")
        
        # ─────────────────────────────────────────────
        # Assert all reverse relations work
        # ─────────────────────────────────────────────
        
        # Refetch from DB to test relations cleanly
        org.refresh_from_db()
        
        self.assertEqual(org.profile, profile)
        self.assertEqual(org.profile.name, "Central High School")
        
        self.assertEqual(org.legal, legal)
        self.assertEqual(org.legal.owner_full_name, "Jane Doe")
        
        domains = list(org.domains.all().order_by("-is_primary"))
        self.assertEqual(len(domains), 2)
        self.assertIn(domain1, domains)
        self.assertIn(domain2, domains)
        
        sub_orgs = list(org.sub_orgs.all())
        self.assertEqual(len(sub_orgs), 2)
        self.assertIn(sub1, sub_orgs)
        self.assertIn(sub2, sub_orgs)

    def test_deactivating_org_blocks_resolve_org_on_its_domain(self):
        org = make_org(slug="closing-school", is_active=True)
        make_domain(org, domain="closing.edu", is_primary=True, is_verified=True)
        
        # Initially resolves correctly
        self.assertEqual(OrgDomain.resolve_org("closing.edu"), org)
        
        # Deactivate
        org.is_active = False
        org.save()
        
        # Should now block
        self.assertIsNone(OrgDomain.resolve_org("closing.edu"))
