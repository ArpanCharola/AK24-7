"""Fixture tests for the two-signal label classifier.

Run from the backend/ directory:
    python -m unittest tests.test_label_classify -v

Stdlib unittest only — no new test dependency. Each case is a
(subject, snippet, sender, expected_labels) tuple. expected_labels is a SET so
order doesn't matter. A new fixture is the right way to add a regression.

Cases cover:
  - True positives we must preserve (recruiter mails, ATS platforms).
  - False positives the old single-signal rules fired on (fitness "challenge",
    "personality quiz" newsletters, vendor demo mails with Calendly links,
    interview-prep newsletters).
  - Sender-domain intelligence (ATS overrides body veto; untrusted does not).
  - Triage buckets that drive the AI tier.
"""
from __future__ import annotations

import unittest

from app.services.email_classifiers import (
    LABEL_ASSESSMENT, LABEL_INTERVIEW, classify, triage,
)


def labels(subject: str, snippet: str, sender: str = "noreply@example.com") -> set[str]:
    return set(classify(subject, snippet, sender))


class TestAssessmentTruePositives(unittest.TestCase):
    """Cases that SHOULD fire the assessment label."""

    def test_hackerrank_invitation(self):
        result = labels(
            "Your HackerRank assessment invitation from Acme Corp",
            "You've been invited to complete the assessment for the Software Engineer role. Click the link below.",
            "noreply@hackerrank.com",
        )
        self.assertIn(LABEL_ASSESSMENT, result)

    def test_take_home_with_deadline(self):
        result = labels(
            "Take-home assignment - Frontend Engineer",
            "Please find your take-home assignment link below. Submit by Sunday.",
            "talent@startup.io",
        )
        self.assertIn(LABEL_ASSESSMENT, result)

    def test_coding_test_please_complete(self):
        result = labels(
            "Online Coding Test - Backend Engineer",
            "Please complete the coding test by Friday to move to the next round.",
            "recruiting@acme.com",
        )
        self.assertIn(LABEL_ASSESSMENT, result)

    def test_codility_reminder(self):
        result = labels(
            "Reminder: Your Codility assessment is ready",
            "This is a reminder to complete your assessment for the Backend Engineer role.",
            "no-reply@codility.com",
        )
        self.assertIn(LABEL_ASSESSMENT, result)


class TestAssessmentFalsePositives(unittest.TestCase):
    """Cases the OLD rules incorrectly fired on. The two-signal rule must reject them."""

    def test_fitness_challenge_newsletter(self):
        result = labels(
            "Take our 30-day fitness challenge!",
            "Join thousands of people in our 30-day fitness challenge for a healthier lifestyle.",
            "newsletter@gymapp.com",
        )
        self.assertNotIn(LABEL_ASSESSMENT, result)

    def test_test_drive_dealership(self):
        result = labels(
            "Test drive the new Mustang",
            "Take the Ford Mustang for a test drive this weekend at your local dealership.",
            "dealership@ford.com",
        )
        self.assertNotIn(LABEL_ASSESSMENT, result)

    def test_personality_quiz_newsletter(self):
        result = labels(
            "Personality quiz: which superhero are you?",
            "Find out your archetype with our fun personality quiz!",
            "newsletter@buzzfeed.com",
        )
        self.assertNotIn(LABEL_ASSESSMENT, result)

    def test_personality_test_without_hiring_context(self):
        result = labels(
            "Personality test for fun",
            "Discover your personality type with our free personality test.",
            "newsletter@buzzfeed.com",
        )
        self.assertNotIn(LABEL_ASSESSMENT, result)


class TestInterviewTruePositives(unittest.TestCase):
    """Cases that SHOULD fire the interview label."""

    def test_interview_invitation_calendly(self):
        result = labels(
            "Interview invitation: Software Engineer at Acme",
            "We'd like to invite you for an interview. Please book a time using calendly.com.",
            "recruiting@acme.com",
        )
        self.assertIn(LABEL_INTERVIEW, result)

    def test_phone_screen_schedule(self):
        result = labels(
            "Phone screen for Backend Engineer role",
            "Hi, can we schedule a 30-minute phone screen this week?",
            "hiring@startup.io",
        )
        self.assertIn(LABEL_INTERVIEW, result)

    def test_onsite_interview_confirmation(self):
        result = labels(
            "Onsite interview confirmation",
            "Please confirm your availability for the onsite interview next week.",
            "talent@bigco.com",
        )
        self.assertIn(LABEL_INTERVIEW, result)

    def test_recruiter_followup_zoom(self):
        result = labels(
            "Next step: technical interview",
            "Great chatting earlier! For the next step we'd like to schedule a technical interview over Zoom.",
            "recruiter@scaleup.io",
        )
        self.assertIn(LABEL_INTERVIEW, result)


class TestInterviewFalsePositives(unittest.TestCase):
    """Cases the OLD rules incorrectly fired on. The two-signal rule must reject them."""

    def test_sales_demo_calendly(self):
        result = labels(
            "Schedule a demo with our sales team",
            "We'd love to show you our product. Pick a time on calendly.com.",
            "sales@vendor.com",
        )
        self.assertNotIn(LABEL_INTERVIEW, result)

    def test_zoom_team_standup(self):
        result = labels(
            "Zoom invitation - daily team standup",
            "Please join our daily team standup tomorrow at 10am.",
            "manager@mycompany.com",
        )
        self.assertNotIn(LABEL_INTERVIEW, result)

    def test_interview_prep_newsletter(self):
        result = labels(
            "5 best practices for technical interviews",
            "How to ace your next technical interview: tips from hiring managers.",
            "blog@techcrunch.com",
        )
        self.assertNotIn(LABEL_INTERVIEW, result)

    def test_calendly_booking_notification(self):
        result = labels(
            "New booking received on Calendly",
            "John Smith just booked a 15-minute call on your calendly.com page.",
            "notifications@calendly.com",
        )
        self.assertNotIn(LABEL_INTERVIEW, result)

    def test_zoom_recording_ready(self):
        result = labels(
            "Your Zoom recording is ready",
            "Click here to watch the recording from your meeting on Zoom.",
            "no-reply@zoom.us",
        )
        self.assertNotIn(LABEL_INTERVIEW, result)


class TestCrossLabelSeparation(unittest.TestCase):
    """An interview email should not get the assessment label and vice versa."""

    def test_pure_interview_does_not_get_assessment(self):
        result = labels(
            "Interview invitation: Backend Engineer",
            "We'd like to invite you for an interview next week. Please share your availability.",
            "recruiter@acme.com",
        )
        self.assertNotIn(LABEL_ASSESSMENT, result)

    def test_pure_assessment_does_not_get_interview(self):
        result = labels(
            "Your HackerRank assessment is ready",
            "Please complete the take-home coding exercise by Sunday.",
            "noreply@hackerrank.com",
        )
        self.assertNotIn(LABEL_INTERVIEW, result)


class TestVetoBlockList(unittest.TestCase):
    """Mail that reuses recruiting words but is really marketing / promo /
    newsletter / job-board junk. The veto layer must keep these untagged."""

    def test_webinar_with_technical_interview(self):
        result = labels(
            "Webinar: how to ace your technical interview",
            "Register now for our free live session. Reserve your spot today!",
            "events@learnplatform.com",
        )
        self.assertNotIn(LABEL_INTERVIEW, result)

    def test_course_promo_with_skills_assessment(self):
        result = labels(
            "Enroll today: Data Science Bootcamp with skills assessment",
            "Complete your assessment and earn a certificate. Limited-time discount on tuition.",
            "admissions@bootcamp.com",
        )
        self.assertNotIn(LABEL_ASSESSMENT, result)

    def test_survey_with_complete_assessment(self):
        result = labels(
            "Complete our quick assessment survey",
            "Take our 2-minute satisfaction survey. Unsubscribe anytime.",
            "feedback@saasco.com",
        )
        self.assertNotIn(LABEL_ASSESSMENT, result)

    def test_aggregator_job_nudge_gets_nothing(self):
        result = labels(
            "Complete your application — 12 new jobs for you",
            "You have a draft application. 50 jobs near you match your profile.",
            "jobs-noreply@indeed.com",
        )
        self.assertNotIn(LABEL_ASSESSMENT, result)
        self.assertNotIn(LABEL_INTERVIEW, result)


class TestRecallAdditions(unittest.TestCase):
    """Real recruiter / assessment phrasings the rules should now catch."""

    def test_greenhouse_interview_invite(self):
        result = labels(
            "Interview invitation — Software Engineer",
            "We'd like to invite you to interview. Please find a time that works.",
            "no-reply@us.greenhouse-mail.io",
        )
        self.assertIn(LABEL_INTERVIEW, result)

    def test_online_assessment_from_ats_domain(self):
        result = labels(
            "Your online assessment for the Backend role",
            "Please complete your assessment within 3 days.",
            "no-reply@hire.lever.co",
        )
        self.assertIn(LABEL_ASSESSMENT, result)

    def test_hirevue_one_way_video_is_assessment(self):
        result = labels(
            "Your video interview invitation",
            "Record your one-way video interview at your convenience.",
            "no-reply@hirevue.com",
        )
        self.assertIn(LABEL_ASSESSMENT, result)

    def test_lets_set_up_a_call_recruiter(self):
        result = labels(
            "Next steps for your application",
            "Great talking today — let's set up a call for your first round interview.",
            "recruiter@startup.io",
        )
        self.assertIn(LABEL_INTERVIEW, result)

    def test_final_onsite_loop(self):
        result = labels(
            "Final onsite interview loop — Senior Engineer",
            "Please confirm your availability for the onsite loop next week.",
            "talent@bigco.com",
        )
        self.assertIn(LABEL_INTERVIEW, result)


class TestDomainVetoOverride(unittest.TestCase):
    """A trusted recruiting domain beats a body-text veto; an untrusted one does not."""

    BODY_SUBJECT = "Complete your coding assessment"
    BODY_SNIPPET = "You're invited to complete the assessment. Manage your preferences or unsubscribe here."

    def test_trusted_ats_overrides_unsubscribe_footer(self):
        result = labels(self.BODY_SUBJECT, self.BODY_SNIPPET, "no-reply@greenhouse.io")
        self.assertIn(LABEL_ASSESSMENT, result)

    def test_untrusted_same_body_stays_untagged(self):
        result = labels(self.BODY_SUBJECT, self.BODY_SNIPPET, "newsletter@randomsaas.com")
        self.assertNotIn(LABEL_ASSESSMENT, result)


class TestTriageBuckets(unittest.TestCase):
    """triage() splits each decision so the pipeline knows what to send the AI."""

    def test_trusted_match_is_confident_tag(self):
        t = triage(
            "Interview invitation — Software Engineer",
            "We'd like to invite you to interview. Please find a time that works.",
            "no-reply@us.greenhouse-mail.io",
        )
        self.assertIn(LABEL_INTERVIEW, t["tag"])
        self.assertNotIn(LABEL_INTERVIEW, t["review_yes"])

    def test_untrusted_match_goes_to_review_yes(self):
        t = triage(
            "Next steps for your application",
            "Great talking today — let's set up a call for your first round interview.",
            "recruiter@startup.io",
        )
        self.assertIn(LABEL_INTERVIEW, t["review_yes"])
        self.assertNotIn(LABEL_INTERVIEW, t["tag"])

    def test_topical_but_unsure_goes_to_review_no(self):
        t = triage(
            "5 best practices for technical interviews",
            "How to ace your next technical interview: tips from hiring managers.",
            "blog@techcrunch.com",
        )
        self.assertIn(LABEL_INTERVIEW, t["review_no"])
        self.assertNotIn(LABEL_INTERVIEW, t["tag"])
        self.assertNotIn(LABEL_INTERVIEW, t["review_yes"])

    def test_aggregator_sends_nothing_to_ai(self):
        t = triage(
            "Complete your application — 12 new jobs for you",
            "You have a draft application. 50 jobs near you match your profile.",
            "jobs-noreply@indeed.com",
        )
        for bucket in ("tag", "review_yes", "review_no"):
            self.assertEqual(t[bucket], set(), f"{bucket} should be empty for aggregator mail")

    def test_vetoed_untrusted_promo_is_not_reviewed(self):
        t = triage(
            "Enroll today: Data Science Bootcamp with skills assessment",
            "Complete your assessment and earn a certificate. Limited-time discount on tuition.",
            "admissions@bootcamp.com",
        )
        self.assertNotIn(LABEL_ASSESSMENT, t["tag"])
        self.assertNotIn(LABEL_ASSESSMENT, t["review_yes"])
        self.assertNotIn(LABEL_ASSESSMENT, t["review_no"])


class TestEmptyAndEdgeInputs(unittest.TestCase):
    def test_empty_inputs_return_no_labels(self):
        self.assertEqual(classify("", "", ""), [])

    def test_none_safe(self):
        self.assertEqual(classify(None, None, None), [])  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
