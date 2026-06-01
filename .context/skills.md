# Preferred Coding Patterns

## Python / Backend
- Use `async`/`await` throughout FastAPI and SQLAlchemy; no sync DB calls in route handlers
- SQLAlchemy models use `Mapped` + `mapped_column` (declarative v2 style), not Column()
- Pydantic v2 schemas for request/response; use `model_config = ConfigDict(from_attributes=True)` instead of `class Config`
- Celery tasks use `asyncio.run()` to bridge into async code; create a fresh engine per task to avoid closed event loop errors
- Keep Celery tasks thin — heavy logic lives in service classes or agent classes, not in the task function itself
- No print() — use `logging.getLogger(__name__)` everywhere
- No bare `except:` — catch specific exceptions or at minimum `except Exception as e`

## AI / OpenAI
- All AI calls go through OpenAI — `gpt-4o` via the `/v1/chat/completions` endpoint
- One shared async helper: `_generate(system, user, max_tokens)` in `app/services/resume_tailor.py`. Other services (e.g. `job_scorer.py`) import and reuse it — do not create a second client
- Set `temperature=0` for deterministic output; pass `max_tokens` sized to the expected JSON/text length
- Parse JSON from model output with a regex fallback (`re.search(r"\{.*\}", text, re.DOTALL)`) — the model sometimes wraps JSON in markdown
- Keep system prompts short and imperative; end with "Output only X — no explanation"
- Never re-introduce `transformers`, `torch`, or local model loading — the dev machine cannot host a large model, and we now use a hosted API anyway
- API key lives in `settings.OPENAI_API_KEY` (loaded from `.env`); never hardcode
- Do not switch back to Groq, langchain-groq, Ollama, or local Mistral/Phi-3/Gemma without an explicit user request — those were tried and rejected

## Playwright / Agents
- Always `await page.wait_for_load_state("networkidle")` after navigation and clicks
- Use `locator.first` + `count() > 0 and is_visible()` checks before clicking — never assume an element exists
- Try the most specific selector first (`data-automation-id`), fall through to text selectors
- Send a screenshot after every meaningful action (`await self._send_screenshot()`)
- Publish logs via `await self._log(message)` so they stream to the AgentConsole in real time
- Agents must call `await self.close()` in a `finally` block — never leak browser processes

## React / Frontend
- TanStack Query for all server state; no manual `useEffect` for data fetching
- Hooks live in `src/hooks/`; API calls live in `src/services/api.js`
- Tailwind only — no inline styles, no CSS modules
- Keep pages thin; extract reusable UI into `src/components/`
- `PrivateRoute` wraps all authenticated pages; token stored in `localStorage`

## General
- No comments explaining *what* code does — only *why* when non-obvious
- No backwards-compat shims, no feature flags, no dead code
- Prefer editing existing files over creating new ones
- Migrations via Alembic (`alembic revision --autogenerate`)
