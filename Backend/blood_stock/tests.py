from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone

from .stock_utils import is_nearing_expiry


class StockExpiryUtilsTests(TestCase):
    def test_is_nearing_expiry_false_when_none(self):
        self.assertFalse(is_nearing_expiry(None, days=5, today=date(2026, 1, 1)))

    def test_is_nearing_expiry_false_when_expired(self):
        today = date(2026, 1, 10)
        self.assertFalse(is_nearing_expiry(today - timedelta(days=1), days=5, today=today))

    def test_is_nearing_expiry_true_on_same_day(self):
        today = date(2026, 1, 10)
        self.assertTrue(is_nearing_expiry(today, days=5, today=today))

    def test_is_nearing_expiry_true_within_window_inclusive(self):
        today = date(2026, 1, 10)
        self.assertTrue(is_nearing_expiry(today + timedelta(days=5), days=5, today=today))

    def test_is_nearing_expiry_false_outside_window(self):
        today = date(2026, 1, 10)
        self.assertFalse(is_nearing_expiry(today + timedelta(days=6), days=5, today=today))

    def test_is_nearing_expiry_defaults_to_localdate(self):
        today = timezone.localdate()
        self.assertTrue(is_nearing_expiry(today, days=5))
