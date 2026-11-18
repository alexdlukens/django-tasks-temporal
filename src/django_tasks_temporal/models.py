"""Database-free model backing the optional Temporal admin page."""

from django.db import models


class TemporalOverview(models.Model):
    """Read-only admin page listing workflow executions and schedules.

    The page reads from the Temporal server; this model has no table and is
    never queried by the database.
    """

    class Meta:
        managed = False
        verbose_name = "Temporal"
        verbose_name_plural = "Temporal"
