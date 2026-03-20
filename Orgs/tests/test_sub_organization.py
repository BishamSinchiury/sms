from django.test import TestCase
from django.db.utils import IntegrityError
from django.db import transaction
from Orgs.models import SubOrganization
from .factories import make_org, make_sub_org

class SubOrganizationTests(TestCase):
    def test_creates_under_parent_org_with_valid_code(self):
        org = make_org()
        sub = make_sub_org(org, code="math-dept")
        self.assertEqual(sub.parent_org, org)
        self.assertEqual(sub.code, "math-dept")

    def test_rejects_duplicate_code_within_same_parent_org(self):
        org = make_org()
        make_sub_org(org, code="sci-dept")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                make_sub_org(org, code="sci-dept")

    def test_allows_same_code_under_different_parent_orgs(self):
        org1 = make_org(slug="school-one")
        org2 = make_org(slug="school-two")
        sub1 = make_sub_org(org1, code="art-dept")
        sub2 = make_sub_org(org2, code="art-dept")
        self.assertEqual(sub1.code, "art-dept")
        self.assertEqual(sub2.code, "art-dept")

    def test_is_active_defaults_to_true(self):
        org = make_org()
        sub = make_sub_org(org)
        self.assertTrue(sub.is_active)

    def test_str_returns_parent_slug_arrow_code(self):
        org = make_org(slug="big-school")
        sub = make_sub_org(org, code="cs-dept")
        self.assertEqual(str(sub), "big-school › cs-dept")

    def test_soft_delete_setting_is_active_false_does_not_remove_record(self):
        org = make_org()
        sub = make_sub_org(org, code="history")
        sub.is_active = False
        sub.save()
        self.assertEqual(SubOrganization.objects.count(), 1)
        sub.refresh_from_db()
        self.assertFalse(sub.is_active)
