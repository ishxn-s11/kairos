# Kairos — Financial Decision Engine

Technical guide for the engine and Flask API in the open-source Kairos project.
See the [project README](../README.md) for setup, accounts, and contribution instructions.

For every row of `dataset/requests.csv` the agent decides whether the user can
safely complete the requested financial commitment and emits
`output.csv` in the repository root.

## Local-first open-weight AI (KAIROS)

Kairos uses its built-in evidence interpreter when `MODEL_PROVIDER` is unset.
Optional **local, open-weight models** can interpret evidence through Ollama;
cloud adapters send relevant evidence to the configured provider. The deterministic
finance engine owns every number; the model turns a message or document image
into candidate facts that the engine then verifies.

The provider is chosen by `MODEL_PROVIDER` and injected through
`buy_or_wait/providers.py` (`build_provider()`):

| `MODEL_PROVIDER` | Provider | Network | Cost |
|---|---|---|---|
| `ollama` (or `local`) | `OllamaProvider` | loopback only | $0 |
| `mock` (or `test`) | `MockProvider` | none | $0 |
| `openai` / `anthropic` / `google` | cloud adapters in `llm.py` | outbound | metered |
| *(unset)* | deterministic-only engine | none | $0 |

### Run with a local open-weight model (Ollama)

No Python SDK is required — KAIROS talks to a running `ollama serve` over its
REST API using the standard library.

```bash
# one-time setup
curl -fsSL https://ollama.com/install.sh | sh   # or install from ollama.com
ollama pull qwen3:4b                             # text / explanations
ollama pull qwen2.5vl:3b                         # screenshots & scanned docs (vision)

# run the pipeline fully local
MODEL_PROVIDER=ollama python3 code/main.py
```

Defaults are `TEXT_MODEL=qwen3:4b` and `VISION_MODEL=qwen2.5vl:3b`. Override the
endpoint with `OLLAMA_HOST` (default `http://127.0.0.1:11434`). Any open-weight
instruct/VL model pulled into Ollama works — swap models freely without code changes.

> **Why `qwen2.5vl` and not `qwen3-vl` for vision?** `qwen3-vl` is a *thinking*
> model that, on Ollama 0.40.5, ignores both `think:false` and `/no_think` and
> spends its entire output budget reasoning before emitting any JSON
> (`done_reason=length`, empty content) — verified against the real runtime.
> `qwen2.5vl` is non-thinking and is Ollama's documented choice for structured
> invoice/form extraction. Revert `VISION_MODEL=qwen3-vl:4b` once a release fixes
> thinking-off handling.

> `OLLAMA_THINK=true` re-enables reasoning if you ever want it (off by default —
> structured extraction is faster and cleaner with thinking disabled).

### Run with no model at all (offline / CI)

```bash
MODEL_PROVIDER=mock python3 code/main.py --output /tmp/offline.csv
```

The `MockProvider` returns deterministic, schema-valid payloads so the whole
extract → validate → engine path runs with zero network and zero cost — useful on
a plane or in CI. With `MODEL_PROVIDER` unset, the engine is fully deterministic
and makes no model calls at all.

Structured model output is validated by `buy_or_wait/schemas.py` (Pydantic when
installed, an equivalent stdlib check otherwise); an invalid reply triggers **one
bounded repair re-prompt** before degrading to a conservative "irrelevant" fact.
Unknown amounts/dates stay `null` — the model can never fabricate a number that
reaches a decision.

## Architecture (hybrid, deterministic-first)

```
retrieve -> inspect evidence -> reconstruct -> forecast ->
generate candidates -> simulate -> reject unsafe plans ->
rank safe plans -> verify -> explain -> output.csv
```

- **Deterministic finance engine** (`code/buy_or_wait/`): money arithmetic
  (Decimal), dated FX conversion, linked-event lifecycle folding, message/image
  evidence precedence, recurrence detection, 90-day cash-flow simulation,
  safe-to-pay bisection, earliest-full-date search, candidate generation,
  independent verification, plan ranking, explanation templates.
- **LLM/VLM as evidence interpreter only** (`code/buy_or_wait/llm.py`): real
  providers are supported (OpenAI, Anthropic, Google/Gemini). When
  `MODEL_PROVIDER` + API key are set, unparseable messages are re-read by the
  text model and image evidence is extracted by the vision model (cached by
  content hash in `code/.cache/image_facts.json` so no image is ever sent
  twice). The model never decides affordability — every fact it returns is
  verified by the deterministic engine.

The **included baseline run** used the deterministic engine with no provider
configured (see `code/evaluation/usage_report.md`), so all outputs are exactly
reproducible. Message understanding is implemented by the deterministic
multilingual interpreter in `code/buy_or_wait/messages.py`; the live model
layer is exercised whenever credentials are supplied.

## Run

```bash
pip install -r code/requirements.txt
python3 code/main.py                          # dataset/requests.csv -> output.csv
python3 code/main.py --requests dataset/requests.csv --output output.csv
python3 code/main.py --debug request_101      # structured diagnostics
python3 code/evaluation/main.py               # score against the 25 solved samples
python3 code/evaluation/validate_output.py    # 22-point final validation
python3 -m pytest code/tests -q               # unit tests (engine + live API + frontend parity)
python3 code/tools/check_parity.py            # static site vs Next.js port
```

## Frontend parity guard (`code/tools/check_parity.py`)

The showcase ships two frontends over one set of shared material — the static
multi-page site in `frontend/` and the React/Next.js port in `frontend-next/`.
The port re-uses the same stylesheet, artwork, data files and logic, wrapped for
ES modules, and because both copies are edited by hand they drift silently. The
guard exists because every one of these bugs was found in a browser first, not
by a check:

| Bug it would have caught | Tier |
|---|---|
| `.pull-ghost` CSS in `main.css` never copied into the Next stylesheet | byte twin |
| `favicon-48.png` present in the static image set but missing from the port | tree twin |
| a transform injecting the static `const D = window.Decisions;` into the ES copy, shadowing the import and killing the explorer | mirror body |
| a helper added to one copy's hand-out object only | mirror surface |
| a new status/method literal added to one copy only | adapted vocabulary |

Four tiers, because the two copies are not identical by nature:

- **byte twins** — pure assets (stylesheet, `manifest.json`, `output.csv`,
  `baseline.json`) must match byte for byte.
- **tree twins** — mirrored directories (the image set) match by file name and
  contents; extra *and* missing files are both drift.
- **mirror twins** — logic copied verbatim (`art.js`, `data.js`, `evidence.js`,
  the decision explorer renderer). Compared on a normalised body *and* their
  exported surface. Normalisation folds away the sanctioned differences: the
  module wrapper (`window.X = (() => { ... })();` vs `export ...`), comments,
  whitespace, CRLF vs LF, and `assets/` vs `/assets/` paths.
- **adapted twins** — ports that deliberately restructured their API (the
  renamed `loadDecisions`, the SSR-safe base-URL resolution, three static
  modules merged into the Next client). Bodies are not comparable, so the guard
  asserts **shared vocabulary**: every domain string in one copy must appear in
  the other unless it is explicitly sanctioned in the manifest with a reason.

Exit code is non-zero on any drift, so it works in CI. `--list` prints the
manifest, `--quiet` prints nothing when clean. `code/tests/test_parity.py`
pins the behaviour: it asserts the real repository is clean **and** injects
broken fixtures into every tier to prove the guard can actually fail.

> The scanner is string- and regex-literal aware on purpose. An earlier naive
> version read the `"` inside `/[&<>"]/g` as a string opener, desynchronised for
> the rest of the file and manufactured phantom drift — that regression is
> pinned by `test_scanner_keeps_regex_class_containing_a_quote`.

## Freelancer mode, uncertainty scenarios, explainable reports

Three additive capabilities on top of the same deterministic engine (the
saved `output.csv` is unchanged; these features use the same core rules).

### Freelancer mode (`buy_or_wait/freelancer.py`)
Invoice-aware, variable-income cash-flow projection for irregular earners. Each
receivable is classified by certainty:

| Certainty | Statuses | Treated as |
|---|---|---|
| settled | `paid`, `received`, `settled` | already in the starting balance — not re-projected |
| confirmed | `confirmed` | projected income on its expected date (reliable) |
| at_risk | `expected`, `pending`, `overdue`, … | **excluded from the baseline** (never a guaranteed deposit) — only shown under scenarios |

Foreign-currency invoices convert at the dated FX rate. `build_freelancer_ledger`
returns `(ledger_with_confirmed_income, at_risk_flows)`; users with no confirmed
invoices get the unchanged baseline ledger, so personal-finance behaviour is
preserved.

### Uncertainty scenarios (`buy_or_wait/scenarios.py`)
Four **separate simulator runs** (never averaged), each a full re-decision on a
perturbed ledger:

1. `on_time` — expected income arrives on its expected date
2. `delayed` — expected income arrives `delay_days` later (default 14)
3. `never` — expected income never arrives inside the horizon (== baseline)
4. `shock` — income on time **plus** an unexpected expense (default 15% of the request, day 15)

Confirmed income (confirmed invoices, projected salary) is present in every
scenario; only at-risk income is varied. Each result reports its own status, safe
amount, plan, and reserve safety with the breach date.

### Explainable reports (`buy_or_wait/report.py`)
A decision report whose numbers all come from **verified profile input** or the
**deterministic simulator**: financial position, recommendation, a dated
`91`-day cash-flow table (opening/credits/debits/purchase/closing/reserve/margin,
satisfying `closing == opening + credits - debits`), upcoming confirmed
obligations, forecast income, payment options compared, optional scenarios, and
an assumptions/missing-information section. Rendered as Markdown (`to_markdown`)
or JSON (`to_dict`), plus a clear "forecast, not a guarantee" disclaimer.

### New API endpoints

```bash
# explainable report (add "invoices": [...] and "scenarios": true for freelancer mode)
curl -s -X POST http://127.0.0.1:8000/api/report \
  -H 'Content-Type: application/json' -d '{"request_id":"request_26"}'

# four uncertainty scenarios (optional invoices, delay_days, shock_amount, shock_date)
curl -s -X POST http://127.0.0.1:8000/api/scenarios \
  -H 'Content-Type: application/json' \
  -d '{"request_id":"request_26","invoices":[{"invoice_id":"i1","amount":"5000","status":"expected","due_date":"2026-11-01"}]}'
```

## Live engine API (for the showcase test bench)

`code/serve_api.py` is a small Flask server that runs the **real** pipeline on
demand, so the showcase's Test Bench can execute *modified* requests — a new
requested amount, a moved request date, or the partial-payment flag — instead of
replaying the precomputed baseline.

```bash
python3 code/serve_api.py                 # http://127.0.0.1:8000 (loopback only)
python3 code/serve_api.py --port 8010 --debug
```

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | engine status, dataset size, model-call usage |
| `GET /api/requests` | every dataset request with its facts (fills the overrides form) |
| `POST /api/decide` | run the pipeline with optional overrides → `{decision, baseline, changed[], modified[], request, usage}` |
| `POST /api/report` | explainable decision report → `{markdown, report}` (dated cash-flow table; optional `invoices` + `scenarios`) |
| `POST /api/scenarios` | four uncertainty scenarios as separate runs → `{invoices, scenarios}` |

```bash
curl -s -X POST http://127.0.0.1:8000/api/decide \
  -H 'Content-Type: application/json' \
  -d '{"request_id":"request_26","requested_amount":78000000}' | python3 -m json.tool
```

Guarantees, all covered by `code/tests/test_api.py`:

- **No overrides reproduce the baseline row exactly** — `changed == []`,
  `modified == []`, and the decision is byte-identical to `output.csv`.
- **Deterministic on modified requests** — the same override always yields the
  same decision (the endpoint is `lru_cache`d; the engine is deterministic).
- **Honest errors** — unknown request → 404, bad amount/date → 400, each with a
  specific message.
- **Honest accounting** — every response reports that run's model calls, tokens,
  and cost (zero with no provider configured).

CORS is open for local development (`KAIROS_API_CORS` to restrict), and responses
are `no-store`. The server persists account, session, and activity records in
`.kairos/accounts.sqlite3` by default; use `KAIROS_AUTH_DB` to choose another path.
See the [account and API documentation](../README.md#configuration-and-data)
in the project README for authentication details.

Optional environment variables (never store keys in files):

```text
MODEL_PROVIDER=openai|anthropic|google
TEXT_MODEL=gpt-5-mini            # or claude-3-5-haiku-latest / gemini-2.5-flash
VISION_MODEL=gpt-5-mini          # or claude-sonnet-4-5 / gemini-2.5-flash
OPENAI_API_KEY=...               # or ANTHROPIC_API_KEY / GOOGLE_API_KEY / GEMINI_API_KEY
```

## Financial assumptions (documented decisions)

1. `current_available_balance` already reflects settled history; the forecast
   projects only future cash flow.
2. Salary is projected **only when explicitly confirmed** (a scheduled salary
   event in the horizon, or a payroll message amendment) — settled history
   alone is not reliable future income (financially safer reading).
3. Fixed monthly commitments (25–35 day median cadence, stable amounts) are
   projected on their observed day of month; irregular/weekly variable spend
   is treated as already reflected in the available balance.
4. Pending debits are reserved; pending credits are never relied upon;
   cancelled/failed lifecycles are folded to their final state; non-cash
   investment valuations are ignored.
5. Foreign events convert at the provided dated rate for the settlement date.
6. `amount_safe_to_pay` is computed before any optional spending changes, by
   bisection through the 90-day simulator.
