"""Regression tests for the promotional-email guard that keeps job-board alerts
out of the Job Tracker.

Run from the backend/ directory:
    python -m unittest tests.test_email_classifiers -v

Stdlib unittest only — no new test dependency.
"""
from __future__ import annotations

import unittest

from app.services.email_classifiers import is_promotional


class TestPromotionalGuard(unittest.TestCase):
    """Job-board blasts that must NOT become tracker cards."""

    def test_unstop_profile_match(self):
        self.assertTrue(is_promotional("Your profile is a match!", "Jia from Unstop"))

    def test_genpact_hiring_alert(self):
        self.assertTrue(is_promotional("Genpact Hiring Alert! Your profile is a match!"))

    def test_discover_top_jobs(self):
        self.assertTrue(is_promotional("Discover top jobs & internships near you!"))

    def test_still_interested(self):
        self.assertTrue(is_promotional("Arpan, are you still interested in these jobs?"))

    def test_job_alert(self):
        self.assertTrue(is_promotional("New job alert", "Jobs matching your profile"))


class TestGenuineConfirmationsNotPromotional(unittest.TestCase):
    """Real application confirmations the guard must let through."""

    def test_application_submitted(self):
        self.assertFalse(is_promotional("Your application has been submitted", "Thank you for applying"))

    def test_wellfound_submitted(self):
        self.assertFalse(is_promotional("Application to iClinic AI successfully submitted"))

    def test_thanks_for_applying(self):
        self.assertFalse(is_promotional("Thank you for applying to Acme Corp"))

    def test_we_received_your_application(self):
        self.assertFalse(is_promotional("We received your application", "Our team will review it shortly"))


if __name__ == "__main__":
    unittest.main()
