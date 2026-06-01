"""One-shot builder for app/data/company_slugs.json.

Strategy (Tier 1): massively expand the Greenhouse / Lever / Ashby company
universe, US-tech-tilted. We ship a generous *candidate* list and validate each
slug against its ATS public API; only slugs that resolve survive. The validator
is the source of truth — invented or stale tokens get dropped silently.

Run from backend/:  .\\venv\\Scripts\\python.exe build_slugs.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT = Path(__file__).parent / "app" / "data" / "company_slugs.json"
CONCURRENCY = 12
TIMEOUT = 10.0


# ────────────────────────────────────────────────────────────────────────────
# Candidate slugs — US-tech tilt (the validator drops anything that doesn't
# resolve to a real, active ATS board). Bias: SaaS, dev-tools, AI/ML, fintech,
# infra, cybersec, marketplaces, devtools, modern HR/CRM. Skip consulting,
# big-pharma, F500 conglomerates, US-gov.
# ────────────────────────────────────────────────────────────────────────────

GREENHOUSE = [
    # Big-name scaleups & unicorns
    "stripe", "airbnb", "lyft", "doordash", "instacart", "dropbox", "pinterest",
    "reddit", "twitch", "roblox", "discord", "figma", "miro", "calendly",
    "notion", "airtable", "asana", "monday", "clickup", "linear",
    # Fintech
    "brex", "ramp", "mercury", "rippling", "gusto", "carta", "robinhood",
    "chime", "sofi", "affirm", "marqeta", "plaid", "square", "betterment",
    "wealthfront", "ethena", "pave", "alloy", "modern-treasury", "stitch-money",
    # Dev infrastructure / DevTools / platforms
    "vercel", "netlify", "cloudflare", "fastly", "hashicorp", "gitlab",
    "mongodb", "elastic", "datadog", "newrelic", "pagerduty", "opsgenie",
    "twilio", "segment", "sendgrid", "okta", "auth0", "launchdarkly",
    "split-software", "optimizely", "amplitude", "mixpanel", "heap", "pendo",
    "fullstory", "intercom", "klaviyo", "braze", "iterable", "customerio",
    "rudderstack", "fivetran", "tray", "workato", "make", "n8n", "retool",
    "airbyte", "dbt-labs",
    # Databases / data
    "cockroachlabs", "yugabyte", "snowflake", "databricks", "confluent",
    "redis", "singlestore", "materialize", "clickhouse", "starburst",
    "dremio", "thoughtspot", "datarobot", "palantir", "dataiku", "alation",
    "atlan", "monte-carlo-data", "datafold", "fishtown-analytics",
    # AI / ML
    "anthropic", "openai", "scale-ai", "weights-and-biases", "labelbox",
    "huggingface", "cohere", "perplexity-ai", "character-ai", "runwayml",
    "stability-ai", "adept", "harvey", "glean", "writer", "jasper",
    "copy-ai", "you-ai", "tome", "luma-ai", "pika",
    # Security
    "okta-greenhouse", "snyk", "wiz", "crowdstrike", "sentinelone", "darktrace",
    "abnormal-security", "armis", "expel", "huntress", "lacework",
    "tenable", "rapid7", "sumologic", "splunk", "dynatrace",
    "netskope", "zscaler", "cyberark", "ping-identity", "beyondtrust",
    "1password", "dashlane", "drata", "vanta", "secureframe",
    "trustpilot", "trust", "tugboat", "doppler", "infisical",
    # Comms / video / docs / collab
    "zoom", "webex", "loom", "miro-app", "mural", "lucid", "framer",
    "descript", "otter-ai", "gong", "salesloft", "outreach", "apollo-io",
    "drift", "kustomer", "freshworks", "zendesk", "front", "helpscout",
    # Marketplaces / commerce
    "doordash-careers", "instacart-careers", "uber", "airbnb-careers",
    "shopify", "etsy", "ebay", "stockx", "goat", "thredup",
    "faire", "flexport", "carvana", "vroom", "openstore",
    # Health / biotech tech
    "hims", "ro", "oscar", "cedar", "devoted-health", "headspace", "calm",
    "modern-health", "oura", "whoop", "lyra-health", "doximity",
    "benchling", "ginkgo-bioworks", "tempus", "recursion-pharma",
    "hinge-health", "k-health", "maven-clinic",
    # Vertical SaaS
    "checkr", "verkada", "samsara", "coreweave", "lob", "klaviyo-app",
    "duolingo", "udemy", "coursera", "masterclass", "khanacademy",
    "udacity", "skillshare",
    # PLG/devtools-y B2B
    "hubspot", "pendo-app", "amplitude-app", "lattice",
    "betterup", "modernhealth",
    # Logistics / industrial tech
    "flexport-app", "convoy", "trucker-path", "kodiak-robotics",
    # Crypto/web3 (mixed but listed for completeness)
    "coinbase", "kraken", "circle", "anchorage", "fireblocks",
    "alchemy", "moralis", "thirdweb", "magiclabs", "dynamic-labs",
    # Recently added scaleups
    "anyscale", "modal-labs", "pinecone", "weaviate", "chroma",
    "langchain", "llamaindex", "context-ai", "humanloop",
    "vellum", "promptlayer", "braintrust", "openrouter",
    # Big consumer/internet
    "duolingo-app", "patreon", "kickstarter", "indiegogo",
    "eventbrite", "ticketmaster", "stubhub", "vivid-seats",
    "thumbtack", "taskrabbit", "rover", "wag",
    # Misc tech
    "asana-app", "zapier", "automattic", "buffer", "doist",
    "basecamp", "github-greenhouse", "gitlab-app",
    "pulumi", "spacelift", "env0", "scalr", "atlantis",
    "circleci", "buildkite", "harness", "codefresh", "dagger",
    "tetrate", "isovalent", "buoyant", "solo-io",
    "kong", "ambassador", "tyk", "apigee",
    "imply", "rockset", "tinybird", "materialize-app",
    "redpanda", "warpstream",
    # Cybersec/identity continuation
    "snyk-app", "github-advanced-security", "checkmarx",
    "veracode", "fossa", "endor-labs", "phylum",
    "socket-dev", "stepsecurity", "chainguard",
    # Productivity / async
    "loom-app", "tella", "vidyard", "wistia",
    # 2024-2025 hot names
    "harvey-ai", "physintell", "magic-dev",
    "magic", "exa", "tavily", "valyu", "you-com",
    "cognition", "factory", "codeium-app",
    "cursor-ai",
    # Already verified seeds from current file
    "pagerduty-app", "elastic-app", "intercom-app", "fivetran-app",
    "airtable-app", "lattice-app", "carta-app",
    "verkada-app", "flexport-careers", "faire-app",
    "robinhood-app", "chime-app", "sofi-app", "affirm-app",
    "marqeta-app",
    "contentful", "webflow", "vercel-app", "netlify-app",
    "runpod", "instacart-app", "peloton",
    "checkr-app", "udemy-app", "coursera-app",
    "klaviyo-careers", "squarespace", "braze-app", "pendo-careers",
    "zuora", "samsara-app", "coreweave-app", "mercury-app",
    "cockroachlabs-app",
    "launchdarkly-app", "netskope-app", "zscaler-app",
    "trustpilot-app", "roblox-app",
    "kong-app", "imply-app",
]

LEVER = [
    "netflix", "atlassian", "spotify", "gopuff", "labelbox",
    "shopify", "github", "kabam", "wealthfront", "lever",
    "patreon", "eventbrite", "etsy", "kickstarter", "indiegogo",
    "khanacademy", "duolingo", "discord-lever", "snap", "niantic",
    "yelp", "yelp-eat24", "doordash-lever", "lyft-lever",
    "blockfi", "ledger", "polygon-technology", "matter-labs",
    "cisco-meraki", "meraki", "asana-lever", "datadog-lever",
    "hashicorp-lever", "elastic-lever", "twilio-lever", "stripe-lever",
    "openai-lever", "anthropic-lever",
    "thumbtack-lever", "instabase", "primer-io",
    "klue", "ironclad", "guideline",
    "modernhealth-lever", "alma-lever", "headspace-lever",
    "betterment-lever", "mercury-lever",
    "showpad", "sumup", "transferwise", "wise",
    "kraken-lever", "blockchain-com", "consensys",
    "stitch-fix", "stitchfix", "rappi", "deliveryhero",
    "asapp", "movableink", "movable-ink", "freshworks-lever",
    "veho", "matera", "fundera",
    "vimeo", "discordapp",
    "ghost", "automattic-lever", "buffer-lever",
    "convoy", "trulia", "trulia-careers", "zillow",
    "doximity-lever", "calm-lever",
    "cleancapital", "neeva", "kagi",
    "everlaw", "outschool",
    "fundthrough", "lemonade", "metromile",
    "policygenius", "insurify", "ethos",
    "embed", "embedded-finance",
    "discord-app", "twitch-lever",
    "robinhood-lever", "plaid-lever",
    "openzeppelin", "alchemy-lever",
    "celonis", "guidewire", "klarna",
    "fanduel", "draftkings", "betr", "underdog-fantasy",
    "loft", "loft-orbital", "axiom-space", "varda-space",
    "anduril", "shield-ai", "epirus", "saronic-tech",
    "scaleflux", "vast-data",
    "deel-lever", "remote-lever", "oyster-lever",
]

ASHBY = [
    # Carry over the ones from the existing file that look real (drop dead suffixes)
    "linear", "vercel", "cal", "railway", "posthog", "liveblocks", "dub",
    "highlight", "resend", "trigger", "inngest", "planetscale", "turso",
    "neon", "supabase", "xata", "upstash", "clerk", "stytch", "ory",
    "permit", "cerbos", "axiom", "betterstack", "checkly", "mailtrap",
    "loops", "customerio", "vero", "june", "mixpanel",
    "heap", "fullstory", "logrocket", "sentry", "rollbar", "bugsnag",
    "grafana", "last9", "chronosphere", "lightstep",
    "honeycomb", "opentelemetry",
    "notion", "loom", "pitch", "retool", "descript", "causal",
    "rows", "motherduck", "rill", "evidence", "lightdash",
    "cursor", "codeium", "tabnine", "sourcegraph", "gitpod",
    "stackblitz", "codesandbox",
    "raycast", "zed", "warp", "arc",
    "fig", "charm",
    # AI & infra
    "together", "groq", "mistral-ai", "perplexity-ai",
    "character-ai", "stability-ai", "runway",
    "modal", "banana", "beam",
    # HR
    "deel", "remote", "oyster",
    # PM / design
    "plane", "height", "basecamp", "craft", "fibery",
    # CI / infra
    "buildkite", "depot", "earthly", "flox", "devzero", "daytona",
    # Incidents / on-call
    "incident-io", "rootly", "firehydrant",
    # BI / analytics
    "metabase", "redash", "count", "mode", "sigma", "omni", "steep",
    # ETL / data ops
    "airbyte", "meltano", "hevo", "stitch-data",
    "dbt-labs",
    "datafold", "monte-carlo", "acceldata",
    # Orchestration
    "temporal", "restate", "windmill", "prefect",
    # Feature flags
    "flagsmith", "growthbook", "unleash",
    # Identity / auth-ish
    "unkey", "workos",
    # New 2024-2025 wave
    "exa-ai", "tavily-ai", "valyu", "kagi-search",
    "cognition", "factory-ai", "magic-dev", "harvey",
    "writer-ai", "vellum-ai", "humanloop", "braintrust",
    "openrouter-ai", "context-ai",
    "framer", "framer-ai", "rest-app",
    "polar", "polar-sh", "openpanel", "tinybird",
    "warpstream", "redpanda-data", "rockset-ai",
    "chainguard", "endor-labs", "phylum-io",
    "socket-security", "stepsecurity",
    "magic-ai", "stack-auth", "kinde",
    "pylon", "plain", "frontapp",
    "novu", "engagespot", "knock-app",
    "highlight-run",
    "browserbase", "anthropic-app", "luma-ai",
    "supadata", "spice-ai",
    "deno", "bun-sh", "wasmer", "fastly-ashby",
    # Schema/data tools
    "atlas-go", "ariga",
    # Vector DBs
    "pinecone-ai", "weaviate", "qdrant", "chroma-db", "lancedb",
    # AI infra
    "modal-com", "replicate-ai", "fireworks-ai",
    "anyscale-ai",
    # Misc
    "browserstack", "saucelabs",
    "stedi", "merge-dev", "finch-api",
    "knot", "rutter", "codat", "ramp-ashby",
    "openphone", "dialpad-app", "openphone-app",
]


async def check_greenhouse(client: httpx.AsyncClient, slug: str) -> bool:
    try:
        r = await client.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", timeout=TIMEOUT)
        return r.status_code == 200 and "jobs" in (r.json() or {})
    except Exception:
        return False


async def check_lever(client: httpx.AsyncClient, slug: str) -> bool:
    try:
        r = await client.get(f"https://api.lever.co/v0/postings/{slug}?mode=json", timeout=TIMEOUT)
        return r.status_code == 200 and isinstance(r.json(), list)
    except Exception:
        return False


async def check_ashby(client: httpx.AsyncClient, slug: str) -> bool:
    try:
        r = await client.get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}", timeout=TIMEOUT)
        if r.status_code != 200:
            return False
        d = r.json() or {}
        # An empty board still returns 200 with a structure; treat any 200 as alive.
        return isinstance(d, dict)
    except Exception:
        return False


async def validate(name: str, candidates: list[str], check) -> list[str]:
    sem = asyncio.Semaphore(CONCURRENCY)
    candidates = sorted(set(s.strip() for s in candidates if s and s.strip()))

    async def one(slug):
        async with sem:
            ok = await check(client, slug)
            return slug, ok

    async with httpx.AsyncClient(headers={"User-Agent": "ai-apply-slug-validator/1.0"}) as client:
        results = await asyncio.gather(*(one(s) for s in candidates))
    valid = sorted(s for s, ok in results if ok)
    print(f"  {name:10}  candidates={len(candidates):4}  valid={len(valid):4}  ({100*len(valid)/max(1,len(candidates)):.0f}% hit)")
    return valid


# Smartrecruiters: tech-tilt by dropping consulting / big-pharma / F500 conglomerates.
SMARTRECRUITERS_TECH_ONLY = [
    "linkedin",  # MS-owned, tech
    "cerner", "epic-systems", "allscripts",  # healthcare IT — borderline tech, keep
]


async def main():
    print("Validating ATS slugs (US-tech tilt) — this hits public APIs, ~2-3 min …\n")
    gh, lv, ah = await asyncio.gather(
        validate("greenhouse", GREENHOUSE, check_greenhouse),
        validate("lever",      LEVER,      check_lever),
        validate("ashby",      ASHBY,      check_ashby),
    )

    # Preserve the existing non-tier-1 sections (we're not touching them this round)
    existing = json.loads(OUT.read_text(encoding="utf-8"))
    out = {
        "greenhouse":      gh,
        "lever":           lv,
        "ashby":           ah,
        "workday":         existing.get("workday", []),
        "icims":           existing.get("icims", []),
        "smartrecruiters": SMARTRECRUITERS_TECH_ONLY,  # tech-tilted
        "bamboohr":        existing.get("bamboohr", []),
        "custom":          existing.get("custom", []),
    }
    OUT.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {OUT.relative_to(OUT.parent.parent.parent)}")
    print(f"  total Tier-1 companies: {len(gh) + len(lv) + len(ah)}")
    print(f"    greenhouse: {len(gh)}\n    lever:      {len(lv)}\n    ashby:      {len(ah)}")


asyncio.run(main())
