# Hirect mobile-API capture — notes & playbook

## Status (verify before investing effort)
- **`hirect.in` does not resolve** (DNS code 000 on `www.hirect.in`, `hirect.in`, `api.hirect.in`). Only the global marketing site `hirect.com` returns 200.
- Hirect's India operation reportedly wound down after RBI/regulatory pressure (~2023–2024). **Confirm the app is still live and serving Indian jobs** (install from Play Store, check it loads listings) before doing the capture below. If the India service is dead, mark Hirect out of scope and move on.
- The adapter [`backend/app/agents/hirect_source.py`](../backend/app/agents/hirect_source.py) ships **dormant**: it returns `[]` until `HIRECT_API_BASE` + `HIRECT_TOKEN` are set in `.env`. Nothing else depends on it.

## Why a capture is required
Hirect is mobile-first (Android/iOS), direct-chat, login-gated, and TLS **certificate-pinned**. There is no public web/JSON endpoint to hit (unlike Instahyre/Cutshort). To get an endpoint you must intercept the app's own HTTPS traffic.

## Capture playbook (Android)
1. **Emulator** with a writable system partition: Android Studio AVD (Google APIs image, API 30/31) or Genymotion. Root it (`adb root` on AVD non-Play images).
2. **Proxy**: run `mitmproxy`/`mitmweb` on the host; point the emulator's Wi-Fi proxy at `host-ip:8080`. Install the mitmproxy CA into the **system** trust store (Android 7+ ignores user CAs for app traffic).
3. **Defeat cert pinning**: install Frida (`frida-server` matching the emulator arch) + `objection`. Launch the app with `objection -g <pkg> explore` then `android sslpinning disable`, or run a Frida universal-unpinning script. Package id is likely `com.hirect.*` (confirm via `adb shell pm list packages | grep -i hirect`).
4. **Drive the app**: log in, run a job search for a tech role in an Indian city. Watch mitmproxy.
5. **Capture these**, then fill `.env`:
   - the API host → `HIRECT_API_BASE` (e.g. `https://api.hirect.in` or whatever it resolves to)
   - the auth header/token → `HIRECT_TOKEN` (note how it's obtained/refreshed; tokens expire — you may need a refresh flow, not a static token)
   - the **job-search request**: exact path (update `_JOB_SEARCH_PATH`), method, query/body params (keyword, city, page), and headers
   - the **response shape**: where the job array lives and the field names (title, company, city, jobId, salary, description) → adjust `_parse_hirect()`

## PII guardrail (non-negotiable)
Hirect's core is recruiter↔candidate chat. **Capture and store job postings only.** Do not persist recruiter/candidate names, phone numbers, or any chat content — that is personal data under the DPDP Act 2023 and carries real penalty exposure. Do not script the chat/messaging endpoints.

## Decision recommendation
Given the dead `.in` domain + mobile-only + pinning + login, expected yield is low and fragile. If a quick Play Store check shows the India app is not serving listings, **stop and leave Hirect dormant** — the other 7 boards cover the market.
