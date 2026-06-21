"""Precision-first email classifiers for the application tracker.

Vendored from skilluence/Gmail-Automation ("Automail") and made source-agnostic:
every function works on a plain message dict `{subject, snippet, from_email}`,
so it doesn't matter whether the mail came from the Gmail API, IMAP, or a test.

Two classifiers:
  - is_genuine_application(msg)  → real HR application confirmation (high precision)
  - classify(subject, snippet, from) → ["assessment"]/["interview"] via a strict
    two-signal (primary AND contextual) rule

`classify_email(msg)` combines them into a single lifecycle "kind":
    "interview" > "assessment" > "confirmed" > None
(later-stage signals win, so an interview invite isn't downgraded to confirmed).
"""
from __future__ import annotations

import re
from email.utils import parseaddr


# ── Genuine application-confirmation filter ─────────────────────────────────

# Gmail full-text search anchors (used to narrow the server-side query).
_APPLICATION_PHRASES = [
    "thank you for applying", "thanks for applying", "thank you for your application",
    "thank you for submitting", "we received your application",
    "we have received your application", "we've received your application",
    "received your application", "application received",
    "application has been received", "your application has been received",
    "your application was received", "your application has been submitted",
    "your application is under review", "received your resume", "received your cv",
    "application has been successfully submitted",
]


# ── Promotional / job-alert guard ───────────────────────────────────────────
# Job boards (Unstop, Wellfound, Naukri, Internshala, LinkedIn, …) send "your
# profile is a match!" / "hiring alert" / "jobs near you" blasts. These are NOT
# application confirmations and must never become Job Tracker cards, even when an
# upstream filter let them through. Used as a subtractive veto at card creation.
_PROMO_PHRASES = (
    "your profile is a match", "profile is a perfect match", "profile is perfect for",
    "hiring alert", "jobs near you", "jobs for you", "internships near you",
    "are you still interested", "don't forget to finish applying",
    "discover top jobs", "discover internships", "recommended for you",
    "check out these jobs", "job alert", "new jobs matching", "jobs matching your profile",
    "similar jobs", "top internships", "top jobs", "new openings", "apply now",
    "don't miss out", "complete your application to", "still accepting applications",
)


def is_promotional(subject: str, snippet: str = "") -> bool:
    """True when the email reads like a job-board alert/promo rather than a real
    application confirmation. Conservative — only fires on unambiguous promo
    phrasing so genuine confirmations are never dropped."""
    text = f"{subject or ''} {snippet or ''}".lower()
    return any(phrase in text for phrase in _PROMO_PHRASES)


_PERSONAL_DOMAINS = frozenset({
    "gmail.com", "googlemail.com",
    "yahoo.com", "yahoo.co.in", "yahoo.co.uk", "yahoo.ca", "ymail.com",
    "hotmail.com", "hotmail.co.uk", "outlook.com", "live.com", "msn.com",
    "aol.com", "icloud.com", "me.com", "mac.com",
    "protonmail.com", "proton.me", "tutanota.com", "tuta.io",
    "rediffmail.com", "zoho.com", "fastmail.com", "gmx.com", "mail.com",
})

_AGGREGATOR_DOMAINS = (
    "indeed.com", "linkedin.com", "linkedin-jobs.com",
    "ziprecruiter.com", "monster.com", "glassdoor.com", "careerbuilder.com",
    "dice.com", "simplyhired.com", "naukri.com", "shine.com", "iimjobs.com",
    "instahyre.com", "hirist.com", "cutshort.io",
    "angel.co", "wellfound.com", "otta.com", "builtin.com", "remoteok.com",
    "weworkremotely.com", "y-combinator.com", "ycombinator.com",
    # India boards/aggregators — their digests/alerts are not application
    # confirmations, so a sender on these domains is a hard veto for every label.
    "foundit.in", "monsterindia.com", "timesjobs.com", "apna.co",
    "internshala.com", "glassdoor.co.in",
    # Unstop (ex-Dare2Compete) blasts "Hiring Alert" / "your profile is a match"
    # promos from no-reply addresses — never application confirmations.
    "unstop.com", "dare2compete.com",
)

# Sender-domain intelligence (see classify_domain). A trusted assessment- or
# scheduling-platform domain may SUPPLY the contextual signal for its matching
# label, but never substitutes for the primary signal. An ATS domain corroborates
# either label and lets a positive beat a body veto. An aggregator domain is a
# hard veto for every label.
_ASSESSMENT_DOMAINS = (
    "hackerrank.com", "codility.com", "codesignal.com", "coderbyte.com",
    "hackerearth.com", "mettl.com", "imocha.io", "devskiller.com",
    "coderpad.io", "codingame.com", "testdome.com", "testgorilla.com",
    "karat.com", "qualified.io", "woven.com", "byteboard.dev",
    "hirevue.com",
    # India assessment platforms
    "doselect.com", "wheebox.com", "cocubes.com",
)

_ATS_DOMAINS = (
    "greenhouse.io", "greenhouse-mail.io",
    "lever.co", "hire.lever.co",
    "ashbyhq.com",
    "myworkday.com", "workday.com", "myworkdayjobs.com",
    "smartrecruiters.com", "smartrecruiters.net",
    "icims.com", "jobvite.com",
    "workable.com", "workablemail.com",
    "bamboohr.com", "teamtailor.com", "recruitee.com", "breezy.hr",
    "jazz.co", "applytojob.com",
    "successfactors.com", "taleo.net", "eightfold.ai", "gem.com",
    # India-prevalent ATS/HRMS — emails from these corroborate an application
    # regardless of whether we can discover jobs from them.
    "keka.com", "darwinbox.com", "darwinbox.in", "zohorecruit.com",
    "freshteam.com", "peoplestrong.com",
)

_SCHEDULING_DOMAINS = (
    "calendly.com", "savvycal.com", "cal.com", "x.ai",
    "goodtime.io", "modernloop.io", "prelude.co",
    "youcanbook.me", "acuityscheduling.com",
)

_DISQUALIFY_PHRASES = (
    "jobs near you", "jobs for you", "new jobs", "matching jobs",
    "trending jobs", "popular jobs", "daily digest", "weekly digest",
    "job alert", "job recommendations", "job suggestions",
    "saved search", "open positions", "opportunities for you",
    "complete your profile", "complete your application", "finish your application",
    "continue your application", "continue to apply", "resume your application",
    "draft application", "draft job application",
    "application update", "application status update", "status update",
    "% match",
)

_SCAM_PHRASES = (
    "bank account", "bank details", "wire transfer", "money transfer",
    "western union", "moneygram",
    "processing fee", "registration fee", "deposit required",
    "send money", "send us money",
    "social security number", "ssn number", "aadhaar number", "aadhar number",
    "click here to claim", "claim your reward",
)

_CONFIRMATION_PHRASES = (
    "thank you for applying", "thanks for applying", "thank you for your application",
    "thank you for submitting your application", "thank you for submitting your resume",
    "thank you for submitting your candidacy",
    "we received your application", "we have received your application",
    "we've received your application", "your application has been received",
    "your application was received", "your application has been submitted",
    "application has been received", "application has been submitted",
    "application received", "successfully submitted your application",
    "application has been successfully submitted",
)

# Indian-English application acknowledgements. These phrases also surface in
# non-confirmation mail ("we regret to inform you about your candidature"), so
# they only count when a JOB-context signal is also present — the gate keeps
# precision while extending recall to Indian HR/ATS wording.
_INDIA_CONFIRMATION_PHRASES = (
    "your candidature", "received your candidature", "candidature has been received",
    "thank you for your candidature", "profile has been received",
    "we have received your profile", "your profile has been received",
)

# Minimal job-context gate for the India confirmation phrases above. Kept local
# (application_tracker imports FROM this module, so we can't import its copy).
_JOB_CONTEXT_RE = (
    re.compile(r"\b(?:position|role|vacancy|opening|openings|requisition)\b"),
    re.compile(r"\b(?:job|career|careers|employment|hiring|recruit(?:ing|ment|er)?|talent acquisition)\b"),
    re.compile(r"\b(?:candidate|candidacy|candidature|applicant)\b"),
    re.compile(r"\bapplied (?:for|to)\b"),
    re.compile(r"\b(?:ctc|lpa|notice period)\b"),
)


def _has_job_context(haystack: str) -> bool:
    return any(p.search(haystack) for p in _JOB_CONTEXT_RE)


REJECTION_CATEGORIES = (
    "personal_domain", "aggregator_domain", "digest_phrase",
    "scam_phrase", "no_confirmation_phrase",
)

# Terminal outcomes. Precision-first: each requires one strong, hiring-specific
# phrase (a false "rejected"/"offer" badge is worse than a miss). These are only
# ever attributed to an application that also matches by company, which further
# bounds false positives.
_OFFER_PHRASES = (
    "pleased to offer", "excited to offer", "happy to offer", "delighted to offer",
    "offer of employment", "offer letter", "your offer letter",
    "extend an offer", "extend you an offer", "would like to offer you",
    "we are offering you", "formal offer", "letter of offer",
    "offer you the position", "offer you the role",
)
_REJECTION_PHRASES = (
    "decided not to move forward", "will not be moving forward",
    "not be moving forward with your application", "not moving forward with your application",
    "move forward with other candidates", "moving forward with other candidates",
    "pursue other candidates", "proceed with other candidates",
    "decided to go with another candidate", "selected another candidate",
    "decided not to proceed", "will not be proceeding",
    "not be progressing", "will not be progressing",
    "position has been filled", "role has been filled",
    "we regret to inform", "regret to inform you",
    "unfortunately, we have decided", "unfortunately we have decided",
    "unable to offer you the", "not be advancing", "no longer under consideration",
    "decided not to continue with your application", "were not selected",
    "not selected for this", "not selected to move",
)


def _sender_domain(from_header: str) -> str:
    _, addr = parseaddr(from_header or "")
    addr = addr.lower()
    return addr.split("@", 1)[1].strip() if "@" in addr else ""


def _matches_aggregator(domain: str) -> bool:
    return bool(domain) and any(domain == k or domain.endswith("." + k) for k in _AGGREGATOR_DOMAINS)


def _domain_in(domain: str, group: tuple[str, ...]) -> bool:
    if not domain:
        return False
    return any(domain == k or domain.endswith("." + k) for k in group)


def classify_domain(domain: str) -> str:
    """Bucket a sender domain: aggregator | assessment | scheduling | ats | ''."""
    if _domain_in(domain, _AGGREGATOR_DOMAINS):
        return "aggregator"
    if _domain_in(domain, _ASSESSMENT_DOMAINS):
        return "assessment"
    if _domain_in(domain, _SCHEDULING_DOMAINS):
        return "scheduling"
    if _domain_in(domain, _ATS_DOMAINS):
        return "ats"
    return ""


# Local-parts that signal an unattended / non-repliable sender.
_NOREPLY_LOCAL = re.compile(
    r"no-?reply|do-?not-?reply|donotreply|noreply|mailer-?daemon|notifications?|"
    r"bounce|postmaster|automated|auto-?confirm|no_reply|jobs-?noreply"
)


def is_repliable_human(from_header: str) -> bool:
    """True only if a message looks like it came from a real, repliable person —
    the gate for autonomous follow-ups. No-reply confirmations fail this, so an
    application whose only mail is a no-reply confirmation never triggers a send."""
    _, addr = parseaddr(from_header or "")
    addr = addr.lower().strip()
    if "@" not in addr:
        return False
    local, domain = addr.split("@", 1)
    if _NOREPLY_LOCAL.search(local):
        return False
    if _matches_aggregator(domain):
        return False
    return True


def is_genuine_application(msg: dict) -> tuple[bool, str]:
    """Classify a candidate message. Returns (is_genuine, category). Never raises."""
    subject = (msg.get("subject") or "").lower()
    snippet = (msg.get("snippet") or "").lower()
    haystack = f"{subject}\n{snippet}"
    domain = _sender_domain(msg.get("from_email") or "")

    if domain in _PERSONAL_DOMAINS:
        return False, "personal_domain"
    if _matches_aggregator(domain):
        return False, "aggregator_domain"
    if any(p in haystack for p in _DISQUALIFY_PHRASES):
        return False, "digest_phrase"
    if any(p in haystack for p in _SCAM_PHRASES):
        return False, "scam_phrase"
    if not any(p in haystack for p in _CONFIRMATION_PHRASES):
        # India-English acknowledgements count only alongside a job-context signal.
        if any(p in haystack for p in _INDIA_CONFIRMATION_PHRASES) and _has_job_context(haystack):
            return True, "ok"
        return False, "no_confirmation_phrase"
    return True, "ok"


# ── Assessment / interview two-signal classifier ────────────────────────────

LABEL_ASSESSMENT = "assessment"
LABEL_INTERVIEW = "interview"

RULES: dict[str, dict[str, list[re.Pattern]]] = {
    LABEL_ASSESSMENT: {
        "primary": [
            re.compile(r"\bassessment\b"),
            re.compile(r"\b(?:coding|technical|online|skills?) (?:test|challenge|assessment|evaluation|exercise)\b"),
            re.compile(r"\btake[- ]home (?:assignment|test|task|project|exercise)\b"),
            re.compile(r"\b(?:hackerrank|codility|codesignal|coderbyte|leetcode|hackerearth|mettl|devskiller|coderpad|codingame|codinggame|testdome|imocha|hirevue|karat|doselect|wheebox|cocubes|amcat|aspiringminds)\b"),
            re.compile(r"\bcoding (?:exercise|round|challenge|problem)\b"),
            re.compile(r"\b(?:aptitude|cognitive|personality|behavioral|psychometric) (?:test|assessment)\b"),
            re.compile(r"\bproctored (?:test|exam|assessment)\b"),
        ],
        "contextual": [
            re.compile(r"\b(?:invite|invitation|invited)\b"),
            re.compile(r"\b(?:assessment|test|challenge|exercise|coding) (?:link|portal|access|invitation|invite)\b"),
            re.compile(r"\byour (?:assessment|test|challenge|coding) (?:link|invitation|is ready|details)\b"),
            re.compile(r"\bplease (?:complete|take|attempt|finish|submit|start|begin)\b"),
            re.compile(r"\b(?:deadline|expires?|expir(?:ed|ing|y)|due (?:by|date|on)|complete by|submit by)\b"),
            re.compile(r"\b(?:next step|next round|round \d|final round)\b"),
            re.compile(r"\b(?:assessment|test|challenge) reminder\b"),
            re.compile(r"\b(?:candidate|application|hiring|recruitment|recruiter) (?:portal|process|status|update|stage|step|round)\b"),
            re.compile(r"\b(?:complete|finish|submit|attempt|access) (?:the |your |this )?(?:assessment|test|challenge|exercise|coding)\b"),
            re.compile(r"\binvited to (?:complete|take|attempt|start|begin) (?:the |your |a |an )?(?:assessment|test|challenge|exercise)\b"),
        ],
    },
    LABEL_INTERVIEW: {
        "primary": [
            re.compile(r"\binterview\b"),
            re.compile(r"\b(?:phone|video|virtual|onsite|on-site|hr|recruiter|hiring manager) (?:screen|interview|round|call|chat)\b"),
            re.compile(r"\b(?:first|second|third|final|technical|behavioral|panel) (?:round|interview|screen)\b"),
        ],
        "contextual": [
            re.compile(r"\b(?:schedule|book|reschedule)\b"),
            re.compile(r"\bset up\b"),
            re.compile(r"\b(?:invitation|invited|scheduled|confirmation|confirmed|reminder|details|confirm)\b"),
            re.compile(r"\bwe(?:'d| would) like to (?:invite|speak|schedule|meet|chat|talk|see)\b"),
            re.compile(r"\b(?:calendly\.com|savvycal\.com|cal\.com|x\.ai)\b"),
            re.compile(r"\b(?:google meet|zoom|microsoft teams|ms teams|webex)\b"),
            re.compile(r"\bplease (?:book|schedule|pick|confirm|share|let us know)\b"),
            re.compile(r"\b(?:next step|next round|moving forward|next stage)\b"),
            re.compile(r"\b(?:availability|availabilities|time slots?)\b"),
            re.compile(r"\b(?:candidate|application|hiring|recruitment|recruiter|hiring team) (?:portal|process|status|update|stage|step|round)\b"),
            re.compile(r"\b(?:looking forward to|excited to) (?:chatting|speaking|meeting|talking|connecting)\b"),
        ],
    },
}


# Veto / block-list — phrases that mean sales / marketing / newsletter / webinar
# / course-promo / job-board-digest mail that merely reuses recruiting vocabulary.
# A veto suppresses a positive even when both rule signals matched, UNLESS the
# sender is a trusted recruiting channel (assessment / scheduling / ats).
_VETO_PATTERNS: list[re.Pattern] = [
    # Webinars / live events / masterclasses
    re.compile(r"\b(?:webinar|masterclass|master class|live (?:session|workshop|demo|event)|fireside chat|ama session)\b"),
    re.compile(r"\b(?:register|sign up|save your seat|reserve your spot|rsvp)\b"),
    # Course / bootcamp / certification promos
    re.compile(r"\b(?:enroll|enrol|enrollment|enrolment|cohort|bootcamp|boot camp|curriculum|syllabus|tuition|scholarship)\b"),
    re.compile(r"\b(?:free|online|self[- ]paced) (?:course|class|training|certification|certificate|program|programme)\b"),
    re.compile(r"\b(?:earn|get) (?:your |a )?(?:certificate|certification|badge|diploma)\b"),
    # Sales / product demo / marketing CTAs
    re.compile(r"\b(?:book|schedule|request|get) (?:a |your |the )?(?:demo|product demo|sales call|sales demo|consultation|walkthrough|walk-through|free trial)\b"),
    re.compile(r"\b(?:our|the) (?:sales|account|customer success) (?:team|rep|representative|executive)\b"),
    re.compile(r"\b(?:upgrade|pricing|subscription|renew(?:al)?|invoice|billing|special offer|limited[- ]time|discount|coupon|promo code|% off|black friday|cyber monday)\b"),
    # Newsletters / digests / blog content
    re.compile(r"\b(?:newsletter|weekly roundup|this week in|read more on our blog|blog post|new article|new post)\b"),
    re.compile(r"\b(?:unsubscribe|manage (?:your )?(?:preferences|subscription)|view (?:this|in) (?:your )?browser|email preferences)\b"),
    # Job-board / aggregator digests & nudges
    re.compile(r"\b\d+\+? (?:new |open )?(?:jobs|roles|positions|openings)\b"),
    re.compile(r"\bjobs (?:near you|for you|matching|recommended)\b"),
    re.compile(r"\b(?:job alert|job recommendations?|recommended (?:jobs|roles)|saved search)\b"),
    re.compile(r"\b(?:complete|finish|continue|resume) your (?:profile|application)\b"),
    re.compile(r"\b\d+% match\b"),
    # Surveys / feedback
    re.compile(r"\b(?:take|complete) (?:our|this|a) (?:survey|questionnaire|poll|feedback (?:survey|form))\b"),
    re.compile(r"\b(?:customer|product|satisfaction|nps) survey\b"),
]


def _veto(haystack: str) -> bool:
    return any(p.search(haystack) for p in _VETO_PATTERNS)


def _any(patterns: list[re.Pattern], text: str) -> bool:
    return any(p.search(text) for p in patterns)


def _evaluate(subject: str, snippet: str, sender: str) -> dict:
    """Shared rule evaluation used by both classify() and triage().

    Returns, per label, the booleans the two callers need:
        {label: {"primary": bool, "contextual": bool, "rules_yes": bool}}
    plus top-level "domain_class", "trusted", and "vetoed".

    A trusted assessment/scheduling domain may SUPPLY the contextual signal for
    its matching label, but never the primary one. A veto suppresses a positive
    unless the sender is a trusted recruiting channel.
    """
    haystack = f"{subject or ''}\n{snippet or ''}\n{sender or ''}".lower()
    domain_class = classify_domain(_sender_domain(sender))
    trusted = domain_class in ("assessment", "scheduling", "ats")
    vetoed = _veto(haystack)

    out: dict = {"domain_class": domain_class, "trusted": trusted, "vetoed": vetoed}
    for label_name, signals in RULES.items():
        primary = _any(signals["primary"], haystack)
        contextual = _any(signals["contextual"], haystack)
        if domain_class == "assessment" and label_name == LABEL_ASSESSMENT:
            contextual = True
        if domain_class == "scheduling" and label_name == LABEL_INTERVIEW:
            contextual = True
        # Aggregator senders are a hard veto for every label.
        rules_yes = (
            domain_class != "aggregator"
            and primary
            and contextual
            and (not vetoed or trusted)
        )
        out[label_name] = {
            "primary": primary,
            "contextual": contextual,
            "rules_yes": rules_yes,
        }
    return out


def classify(subject: str, snippet: str, sender: str) -> list[str]:
    """Return the list of labels (assessment/interview) the RULES assign to a
    message. Two-signal: at least one PRIMARY and one CONTEXTUAL pattern both
    match, strengthened by sender-domain trust and suppressed by the veto list.
    This is the fully-private fallback used whenever the AI is unavailable."""
    ev = _evaluate(subject, snippet, sender)
    return [name for name in RULES if ev[name]["rules_yes"]]


def triage(subject: str, snippet: str, sender: str) -> dict[str, set[str]]:
    """Split each label decision into three buckets for the AI tier:

        {"tag": set, "review_yes": set, "review_no": set}

    - tag:        confident — a rules match from a domain that corroborates
                  this label. Apply without asking the AI.
    - review_yes: the rules matched but the sender is untrusted — could be
                  marketing dressed in recruiting words. Ask the AI to confirm;
                  if AI is unavailable, keep it (preserves rules behaviour).
    - review_no:  rules did NOT match but the mail is plausibly about this
                  label (a primary hint, not obvious junk). Ask the AI to
                  rescue real ones; if AI is unavailable, skip it.

    classify() == tag ∪ review_yes (the rules-only verdict).
    """
    ev = _evaluate(subject, snippet, sender)
    result: dict[str, set[str]] = {"tag": set(), "review_yes": set(), "review_no": set()}
    domain_class = ev["domain_class"]
    if domain_class == "aggregator":
        return result  # hard, non-overridable no for everything

    def _corroborates(label_name: str) -> bool:
        # An assessment-platform sender shouldn't auto-confirm an interview tag
        # (HireVue's "video interview" is really an async assessment).
        if label_name == LABEL_ASSESSMENT:
            return domain_class in ("assessment", "ats")
        if label_name == LABEL_INTERVIEW:
            return domain_class in ("scheduling", "ats")
        return False

    vetoed = ev["vetoed"]
    for label_name in RULES:
        info = ev[label_name]
        if info["rules_yes"]:
            if _corroborates(label_name):
                result["tag"].add(label_name)
            else:
                result["review_yes"].add(label_name)
        elif info["primary"] and not vetoed:
            result["review_no"].add(label_name)
    return result


def classify_outcome(msg: dict) -> str | None:
    """Detect a terminal hiring outcome: "offer" or "rejected" (else None)."""
    haystack = f"{(msg.get('subject') or '').lower()}\n{(msg.get('snippet') or '').lower()}"
    if any(p in haystack for p in _OFFER_PHRASES):
        return "offer"
    if any(p in haystack for p in _REJECTION_PHRASES):
        return "rejected"
    return None


def classify_email(msg: dict) -> str | None:
    """Single lifecycle kind for a message — rules only (sync, no AI).

    Priority: offer > rejected > interview > assessment > confirmed > None.
    Used by the inbox view where per-message AI cost is prohibitive. The
    periodic scan in ``email_tracker`` uses ``decide_email_kind`` instead so it
    can apply the AI double-check to the ambiguous band.
    """
    outcome = classify_outcome(msg)
    if outcome:
        return outcome
    labels = classify(msg.get("subject", ""), msg.get("snippet", ""), msg.get("from_email", ""))
    if LABEL_INTERVIEW in labels:
        return "interview"
    if LABEL_ASSESSMENT in labels:
        return "assessment"
    genuine, _ = is_genuine_application(msg)
    return "confirmed" if genuine else None


async def decide_email_kind(msg: dict) -> tuple[str | None, bool]:
    """Lifecycle kind for a message, with the AI tier on the ambiguous band.

    Returns ``(kind, ai_used)``. ``kind`` follows the same priority as
    ``classify_email``. ``ai_used`` is True when an AI verify call decided the
    label (so callers can tally the scan summary). Falls back cleanly to the
    rules verdict when the AI is unavailable. Never raises.
    """
    outcome = classify_outcome(msg)
    if outcome:
        return outcome, False

    msg_id = msg.get("id") or ""
    subject = msg.get("subject", "")
    snippet = msg.get("snippet", "")
    sender = msg.get("from_email", "")

    decision = triage(subject, snippet, sender)
    names: set[str] = set(decision["tag"])
    review = decision["review_yes"] | decision["review_no"]
    ai_used = False
    if review:
        # Lazy import — label_ai imports from this module.
        from app.services import label_ai
        verdict = await label_ai.verify(msg_id, subject, snippet, sender)
        if verdict is None:
            names |= decision["review_yes"]  # AI down → rules verdict
        else:
            ai_used = True
            names |= {n for n in review if verdict.get(n)}

    if LABEL_INTERVIEW in names:
        return "interview", ai_used
    if LABEL_ASSESSMENT in names:
        return "assessment", ai_used

    genuine, _ = is_genuine_application(msg)
    return ("confirmed" if genuine else None), ai_used


def build_scan_query(days: int = 30) -> str:
    """Gmail search query that narrows to mail relevant to all three kinds. The
    local classifiers then filter precisely, so this just needs to not miss."""
    anchors = list(_APPLICATION_PHRASES) + [
        "interview", "assessment", "phone screen", "coding challenge",
        "coding test", "take home", "online assessment", "technical interview",
        # outcome anchors
        "offer", "regret to inform", "moving forward", "other candidates",
        "not selected", "position has been filled", "unfortunately",
        # India-English anchors
        "candidature", "your profile has been received", "shortlisted",
    ]
    or_clause = " OR ".join(f'"{a}"' if " " in a else a for a in anchors)
    return f"in:inbox newer_than:{days}d ({or_clause})"
