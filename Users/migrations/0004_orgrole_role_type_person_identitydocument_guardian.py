# ── Users/migrations/0006_identitydocument_extended_types.py ──

"""
0006_identitydocument_extended_types.py
----------------------------------------
Extends IdentityDocument.document_type choices with role-specific
document types: pan_card, cv, recruitment_letter, transfer_certificate,
admission_form.

Also adds a composite index on (person, document_type) to speed up
the hard-validation query that checks whether a required document type
exists for a person before allowing profile submission.

No data migration needed — existing rows have valid document_type values
from the original 5 choices, which are preserved unchanged.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Users', '0003_user_phone_number_alter_orgmembership_status'),
    ]
    operations = [
        # Extend the document_type choices to include new role-specific types.
        # Django CharField choices are not enforced at the DB level (no CHECK
        # constraint by default), so this migration only updates the Python-side
        # choices and does not alter the column type or existing data.
        migrations.AlterField(
            model_name='identitydocument',
            name='document_type',
            field=models.CharField(
                choices=[
                    # Original types — unchanged
                    ('national_id',        'National ID'),
                    ('passport',           'Passport'),
                    ('birth_certificate',  'Birth Certificate'),
                    ('driving_license',    'Driving License'),
                    ('other',              'Other'),
                    # Extended types for role-specific documents
                    ('pan_card',           'PAN Card'),
                    ('cv',                 'CV / Resume'),
                    ('recruitment_letter', 'Recruitment Letter'),
                    ('transfer_certificate', 'Transfer Certificate'),
                    ('admission_form',     'Admission Form'),
                ],
                default='other',
                max_length=50,
            ),
        ),

        # Add file extension validator to front_image.
        # back_image already has blank=True; adding validator here too.
        # Note: FileExtensionValidator is not stored in the DB — this
        # only updates the Django model-level validation.
        migrations.AlterField(
            model_name='identitydocument',
            name='front_image',
            field=models.FileField(
                upload_to='persons/documents/',
                validators=[
                    __import__(
                        'django.core.validators',
                        fromlist=['FileExtensionValidator']
                    ).FileExtensionValidator(
                        allowed_extensions=['pdf', 'jpg', 'jpeg', 'png']
                    )
                ],
            ),
        ),

        migrations.AlterField(
            model_name='identitydocument',
            name='back_image',
            field=models.FileField(
                blank=True,
                upload_to='persons/documents/',
                validators=[
                    __import__(
                        'django.core.validators',
                        fromlist=['FileExtensionValidator']
                    ).FileExtensionValidator(
                        allowed_extensions=['pdf', 'jpg', 'jpeg', 'png']
                    )
                ],
            ),
        ),

        # Composite index on (person, document_type) for the hard-validation
        # query: "does this person have at least one national_id or passport?"
        migrations.AddIndex(
            model_name='identitydocument',
            index=models.Index(
                fields=['person', 'document_type'],
                name='idx_identity_doc_type',
            ),
        ),
    ]