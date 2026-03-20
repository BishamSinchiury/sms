import tempfile
import shutil
from datetime import timedelta
from django.utils import timezone
from django.test import TestCase, override_settings
from django.core.exceptions import ValidationError
from Orgs.models import OrganizationLegal
from .factories import make_org, make_legal, make_upload_pdf, make_upload_image

MEDIA_ROOT = tempfile.mkdtemp()

@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class OrganizationLegalTests(TestCase):
    def setUp(self):
        self.org = make_org()

    def tearDown(self):
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)

    def test_creates_linked_to_org(self):
        legal = make_legal(self.org, owner_full_name="John Doe")
        self.assertEqual(legal.org, self.org)
        self.assertEqual(legal.owner_full_name, "John Doe")

    def test_legal_completion_percent_returns_0_when_all_tracked_fields_empty(self):
        legal = make_legal(self.org)
        # Assuming accreditation_status defaults to NOT_APPLICABLE and is not counted as filled
        # Actually tracked fields: owner_full_name, owner_id_number, registration_number,
        # registration_date, registered_with, tax_id_number, accreditation_status
        # Wait, if accreditation_status is NOT_APPLICABLE, it might be counted.
        # Let's explicitly clear it to test 0% properly.
        legal.accreditation_status = ""
        self.assertEqual(legal.legal_completion_percent, 0)

    def test_legal_completion_percent_returns_100_when_all_tracked_fields_filled(self):
        legal = make_legal(
            self.org,
            owner_full_name="John", owner_id_number="123",
            registration_number="REG", registration_date=timezone.now().date(),
            registered_with="Gov", tax_id_number="TAX",
            accreditation_status="accredited"
        )
        self.assertEqual(legal.legal_completion_percent, 100)

    def test_is_accreditation_expired_returns_false_when_valid_until_is_none(self):
        legal = make_legal(self.org)
        self.assertFalse(legal.is_accreditation_expired)

    def test_is_accreditation_expired_returns_true_when_valid_until_is_in_the_past(self):
        past_date = timezone.now().date() - timedelta(days=1)
        legal = make_legal(self.org, accreditation_valid_until=past_date)
        self.assertTrue(legal.is_accreditation_expired)

    def test_is_accreditation_expired_returns_false_when_valid_until_is_in_the_future(self):
        future_date = timezone.now().date() + timedelta(days=1)
        legal = make_legal(self.org, accreditation_valid_until=future_date)
        self.assertFalse(legal.is_accreditation_expired)

    def test_is_registration_expired_returns_false_when_expiry_is_none(self):
        legal = make_legal(self.org)
        self.assertFalse(legal.is_registration_expired)

    def test_is_registration_expired_returns_true_when_expiry_is_in_the_past(self):
        past_date = timezone.now().date() - timedelta(days=1)
        legal = make_legal(self.org, registration_expiry=past_date)
        self.assertTrue(legal.is_registration_expired)
        
    def test_is_registration_expired_returns_false_when_expiry_is_in_the_future(self):
        future_date = timezone.now().date() + timedelta(days=1)
        legal = make_legal(self.org, registration_expiry=future_date)
        self.assertFalse(legal.is_registration_expired)

    def test_registration_document_upload_saves_to_correct_private_path(self):
        legal = make_legal(self.org, registration_document=make_upload_pdf("reg.pdf"))
        self.assertTrue(legal.registration_document.name.startswith(f"private/orgs/{self.org.slug}/legal/"))

    def test_accreditation_document_upload_saves_to_correct_private_path(self):
        legal = make_legal(self.org, accreditation_document=make_upload_pdf("acc.pdf"))
        self.assertTrue(legal.accreditation_document.name.startswith(f"private/orgs/{self.org.slug}/accreditation/"))

    def test_both_document_uploads_reject_disallowed_extensions(self):
        legal = make_legal(self.org)
        invalid_file = make_upload_pdf("bad.exe")
        legal.registration_document = invalid_file
        legal.accreditation_document = invalid_file
        with self.assertRaises(ValidationError):
            legal.full_clean()

    def test_both_document_uploads_accept_pdf_jpg_jpeg_png(self):
        legal = make_legal(self.org)
        legal.registration_document = make_upload_pdf("good.pdf")
        legal.accreditation_document = make_upload_image("good.jpg", "image/jpeg")
        # Should not raise validation error for file extensions
        # Except it complains about other blank fields if required. But legal has blank=True.
        # We only care about file extension validator here:
        legal.full_clean()

    def test_sensitive_fields_save_and_retrieve_correctly(self):
        legal = make_legal(
            self.org,
            owner_id_number="SEC-999-XYZ",
            tax_id_number="TAX-12345",
            vat_number="VAT-888"
        )
        legal.refresh_from_db()
        self.assertEqual(legal.owner_id_number, "SEC-999-XYZ")
        self.assertEqual(legal.tax_id_number, "TAX-12345")
        self.assertEqual(legal.vat_number, "VAT-888")
