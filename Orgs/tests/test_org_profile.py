import tempfile
import shutil
from django.test import TestCase, override_settings
from django.core.exceptions import ValidationError
from Orgs.models import OrganizationProfile
from .factories import make_org, make_profile, make_upload_image, make_upload_pdf

MEDIA_ROOT = tempfile.mkdtemp()

@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class OrganizationProfileTests(TestCase):
    def setUp(self):
        self.org = make_org()

    def tearDown(self):
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)

    def test_creates_linked_to_org(self):
        profile = make_profile(self.org, name="My School")
        self.assertEqual(profile.org, self.org)
        self.assertEqual(profile.name, "My School")

    def test_all_blank_by_default_fields_save_as_empty_string_not_null(self):
        profile, _ = OrganizationProfile.objects.get_or_create(org=self.org)
        self.assertEqual(profile.short_name, "")
        self.assertEqual(profile.tagline, "")
        self.assertEqual(profile.description, "")
        self.assertEqual(profile.address_line_1, "")

    def test_profile_completion_percent_returns_0_when_all_tracked_fields_empty(self):
        profile = make_profile(self.org)
        self.assertEqual(profile.profile_completion_percent, 0)

    def test_profile_completion_percent_returns_100_when_all_tracked_fields_filled(self):
        profile = make_profile(
            self.org,
            name="School", school_type="primary", tagline="Motto", description="Desc",
            logo=make_upload_image(), address_line_1="123", city="City", country="Country",
            phone_primary="123456", email_primary="info@school.com", website="http://school.com"
        )
        self.assertEqual(profile.profile_completion_percent, 100)

    def test_profile_completion_percent_returns_correct_partial_percentage(self):
        profile = make_profile(self.org, name="School", city="City", email_primary="info@school.com")
        # 3 out of 11 fields = 27%
        self.assertEqual(profile.profile_completion_percent, 27)

    def test_full_address_joins_only_non_empty_parts(self):
        profile = make_profile(self.org, address_line_1="Suite 5", city="Metropolis", country="USA")
        self.assertEqual(profile.full_address, "Suite 5, Metropolis, USA")

    def test_full_address_returns_empty_string_when_all_blank(self):
        profile = make_profile(self.org)
        self.assertEqual(profile.full_address, "")

    def test_public_data_returns_only_whitelisted_fields(self):
        profile = make_profile(
            self.org, name="The School", short_name="TS", tagline="Build Big",
            description="Good school", school_type="secondary", established_year=1990,
            primary_color="#123456"
        )
        data = profile.public_data()
        self.assertEqual(data["name"], "The School")
        self.assertEqual(data["short_name"], "TS")
        self.assertNotIn("address_line_1", data)
        self.assertIn("address", data)

    def test_public_data_returns_none_for_missing_images(self):
        profile = make_profile(self.org)
        data = profile.public_data()
        self.assertIsNone(data["logo"])
        self.assertIsNone(data["cover_image"])
        self.assertIsNone(data["favicon"])

    def test_logo_upload_saves_to_correct_path(self):
        profile = make_profile(self.org, logo=make_upload_image("logo.jpg"))
        self.assertTrue(profile.logo.name.startswith("org_logos/"))
        self.assertTrue(profile.logo.size > 0)

    def test_favicon_upload_saves_to_correct_path(self):
        profile = make_profile(self.org, favicon=make_upload_image("icon.png", "image/png"))
        self.assertTrue(profile.favicon.name.startswith("org_favicons/"))

    def test_cover_image_upload_saves_to_correct_path(self):
        profile = make_profile(self.org, cover_image=make_upload_image("hero.jpg"))
        self.assertTrue(profile.cover_image.name.startswith("org_covers/"))

    def test_rejects_image_upload_with_disallowed_extension(self):
        profile = make_profile(self.org)
        # Using pdf extension for an image field fails ImageField validation natively
        # or FileExtensionValidator.
        invalid_file = make_upload_pdf("logo.pdf")
        profile.logo = invalid_file
        with self.assertRaises(ValidationError):
            profile.full_clean()
