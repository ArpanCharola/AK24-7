from types import SimpleNamespace

from app.api.routes.matches import _ensure_manual_resume_text


def _user(**overrides):
    data = {
        "resume_text": None,
        "desired_roles": "Software Engineer",
        "preferred_locations": '["Bengaluru", "Remote India"]',
        "skills": ["Python", "React"],
        "experience_years": 2,
        "experience_months": 6,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_manual_complete_profile_gets_synthetic_resume_text():
    user = _user()

    changed = _ensure_manual_resume_text(user)

    assert changed is True
    assert user.resume_text is not None
    assert "Manual profile completed" in user.resume_text
    assert "Software Engineer" in user.resume_text
    assert "Bengaluru" in user.resume_text
    assert "2 years 6 months" in user.resume_text
    assert "Python, React" in user.resume_text


def test_manual_profile_without_skills_is_not_marked_ready():
    user = _user(skills=[])

    changed = _ensure_manual_resume_text(user)

    assert changed is False
    assert user.resume_text is None


def test_existing_resume_text_is_preserved():
    user = _user(resume_text="Uploaded resume text")

    changed = _ensure_manual_resume_text(user)

    assert changed is False
    assert user.resume_text == "Uploaded resume text"
