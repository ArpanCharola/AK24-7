from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.api.routes.profile import ProfileUpdate, _profile_readiness


def _user(**overrides):
    data = {
        "resume_text": None,
        "desired_roles": "Software Engineer, Backend Developer",
        "preferred_locations": '["Rajkot", "Remote India"]',
        "skills": ["Python", "FastAPI"],
        "experience_years": 0,
        "experience_months": 6,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_profile_update_rejects_unknown_frontend_fields():
    with pytest.raises(ValidationError):
        ProfileUpdate(desired_roles="Software Engineer", unsupported_field=True)


def test_complete_manual_profile_is_recommendation_ready():
    assert _profile_readiness(_user()) == (True, 3)


def test_profile_readiness_reports_missing_roles():
    assert _profile_readiness(_user(desired_roles=None)) == (False, 2)


def test_zero_experience_is_a_valid_explicit_experience():
    assert _profile_readiness(_user(experience_years=0, experience_months=0)) == (True, 3)
