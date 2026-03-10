"""
base.py
-------
Abstract base model providing common fields for all models.
Every model in this system inherits from TimeStampedModel.
"""

import uuid
from django.db import models


class TimeStampedModel(models.Model):
    """
    Abstract base class that provides:
    - UUID primary key (avoids sequential ID enumeration attacks)
    - created_at / updated_at auto timestamps
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
