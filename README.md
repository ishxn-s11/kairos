# Kairos

**An open-source financial decision engine for answering “Can I afford this?”**

Kairos reconstructs a financial picture, forecasts cash flow, and compares payment strategies against a protected minimum balance. It explains whether to pay now, make a partial payment, use installments, wait, or skip a purchase.

The project includes a Python engine, a Flask API, and a responsive Next.js app with light and dark themes, an interactive test bench, and local user accounts. The source code is available under the [MIT License](LICENSE).

## What Kairos does

- Rebuilds a financial state from balances, dated events, recurring commitments, messages, and document evidence.
- Simulates a 90-day cash-flow horizon using exact decimal arithmetic.
- Reserves pending debits and protects essential spending and the user's minimum balance.
- Compares full payment, partial payment, available installment schedules, waiting, and permitted spending changes.
- Produces a safe amount, an earliest full-payment date, a payment plan, and an explanation.
- Supports invoice income, uncertainty scenarios, and Markdown or JSON reports through the API.
- Offers optional local or cloud models for interpreting evidence; the financial calculations remain in Python.

## Current scope

The test bench runs against the included dataset of 250 requests. You can change a request's amount, dates, and partial-payment preference, then run it through the live backend. The results explorer also works with saved engine output.

Accounts provide registration, login, logout, and an activity history for authenticated API runs. They are separate from the financial profiles in the example dataset. Personal financial onboarding, bank connections, email verification, and password recovery are not implemented.

## Quick start

### Requirements

- Python 3.10 or newer
- Node.js 22 or newer, with npm (Vercel uses Node.js 24)
- Git

### 1. Clone the project

```bash
git clone https://github.com/ishxn-s11/kairos.git
cd kairos
python -m venv .venv
```

Activate the virtual environment for your shell:

```bash
# macOS / Linux
source .venv/bin/activate
```

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

### 2. Start the backend

From the repository root:

```bash
python -m pip install -r code/requirements.txt
python code/serve_api.py
```

The API listens on `http://127.0.0.1:8000`. No model API key is required for the default engine.

### 3. Start the frontend

In another terminal:

```bash
cd kairos/frontend-next
npm ci
npm run dev
```

If your terminal is already at the repository root, use `cd frontend-next` instead. Open [Kairos at localhost:8480](http://127.0.0.1:8480/).

| Route | Page |
|---|---|
| `/` | Product homepage |
| `/about/` | Product principles and engine overview |
| `/test/` | Saved-output test bench and live engine controls |
| `/results/` | Decision explorer, evidence, and validation overview |
| `/workflow/` | Interactive pipeline visualization |
| `/account/` | Login, registration, and account activity |

Use **Run live** on the test bench to execute the Python engine. Reading a saved baseline does not create an account activity entry.

## Command-line use

Run these commands from the repository root with the virtual environment active:

```bash
python code/main.py
python code/main.py --requests dataset/requests.csv --output output.csv
python code/main.py --debug request_101
```

The CLI writes one decision per request to `output.csv` and refreshes the model usage report in `code/evaluation/usage_report.md`.

| Output field | Meaning |
|---|---|
| `request_id` | Request identifier |
| `amount_safe_to_pay` | Amount safe on the request date, before optional spending changes |
| `affordability_status` | `affordable_now`, `affordable_with_plan`, `affordable_later`, or `not_affordable` |
| `recommended_payment_method` | `full_payment`, `partial_payment`, `installments`, `wait`, or `not_recommended` |
| `payment_plan` | Dated amounts separated by `\|`, or `none` |
| `earliest_date_for_full_payment` | First projected safe date for a single full payment, when available |
| `spending_changes_needed` | Permitted spending adjustments, or `none` |
| `decision_explanation` | Reasoning grounded in the financial evidence |

## API

The API uses JSON request and response bodies.

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/health` | Engine status and model usage |
| `GET` | `/api/requests` | Dataset requests and their editable facts |
| `POST` | `/api/decide` | Decision with optional request overrides and a baseline comparison |
| `POST` | `/api/report` | Markdown and JSON report, with optional invoices and scenarios |
| `POST` | `/api/scenarios` | Compare on-time, delayed, missing-income, and expense-shock scenarios |
| `POST` | `/api/auth/register` | Create an account with `name`, `email`, and `password` |
| `POST` | `/api/auth/login` | Sign in with `email` and `password`; return a bearer token |
| `GET` | `/api/auth/me` | Authenticated user and activity counts |
| `POST` | `/api/auth/logout` | Revoke the current token |
| `GET` | `/api/activity` | Authenticated user's latest 50 activity entries |

Example for Bash and other POSIX shells:

```bash
curl http://127.0.0.1:8000/api/decide \
  -H 'Content-Type: application/json' \
  -d '{"request_id":"request_26","requested_amount":"4200"}'
```

Example for PowerShell:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/decide `
  -ContentType 'application/json' `
  -Body '{"request_id":"request_26","requested_amount":"4200"}'
```

Decision endpoints support anonymous demo runs. Include `Authorization: Bearer <token>` to attribute successful decisions, reports, and scenario runs to an account. Account identity and activity endpoints require authentication.

## Configuration and data

| Variable | Default | Purpose |
|---|---|---|
| `NEXT_PUBLIC_KAIROS_API` | Local: `http://127.0.0.1:8000`; hosted: same origin | Optional frontend API URL; set before starting or building Next.js |
| `KAIROS_API_CORS` | `*` | Allowed frontend origin for API responses |
| `KAIROS_AUTH_DB` | `.kairos/accounts.sqlite3` | Account database path, relative to the working directory when overridden with a relative path |
| `DATABASE_URL` | Unset | Pooled PostgreSQL connection for hosted accounts; required on Vercel |
| `DATABASE_URL_UNPOOLED` | Unset | Direct PostgreSQL connection for initializing the account schema |
| `MODEL_PROVIDER` | Unset | Built-in evidence interpretation; optional `mock`, `ollama`, `openai`, `anthropic`, or `google` |
| `TEXT_MODEL` / `VISION_MODEL` | Provider dependent | Optional evidence model names |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Local model service URL |

Set environment variables in your shell before launching the relevant process. The Python entry points do not automatically load `.env` files. See the [engine guide](code/README.md) for provider setup and the [frontend guide](frontend-next/README.md) for API URL overrides.

Passwords use Werkzeug password hashes. The server stores session token hashes with a 30-day expiry; the frontend keeps its bearer token in browser local storage. Account records and activity are persisted in SQLite locally or PostgreSQL when `DATABASE_URL` is set. The `.kairos/` directory is excluded from Git. Hosted account endpoints return a clear error if PostgreSQL is not configured instead of using temporary serverless files.

The development server binds to loopback by default. For an externally hosted installation, configure an explicit frontend origin, HTTPS, persistent database storage, and an appropriate production server.

## How the engine works

```text
Evidence → Resolve conflicts → Reconstruct state → Forecast
         → Size and date search → Compare plans → Verify → Explain
```

Money calculations use Python `Decimal`. Currency conversion uses the supplied dated rates. Pending debits reduce available cash; unconfirmed income and unrealized investment values do not become spendable money. Candidate plans are simulated against the protected balance before ranking.

The included CSV data lives in `dataset/`. Request, profile, event, message, image, and payment-option records are linked through their identifiers. Replacing dataset files requires preserving their schemas and relationships. The `--requests` flag selects a request CSV; it does not change the directory used for the other financial records.

## Project structure

```text
code/
  buy_or_wait/     Financial engine, evidence extraction, reports, scenarios
  evaluation/      Output validation and usage reports
  tests/           Engine, API, provider, and shared-asset tests
  main.py          Batch decision entry point
  serve_api.py     Flask API, accounts, and activity persistence
dataset/           Example requests and supporting financial records
frontend-next/     React 18 / Next.js 16 application
frontend/          Earlier framework-free static frontend
output.csv         Saved batch decisions
LICENSE            MIT license
```

The Next.js app is the primary interface. The earlier static frontend remains available, and shared data, artwork, styles, and selected logic are checked by a parity guard. Page layouts and account/theme controls differ between the frontends.

## Build and verification

From the repository root:

```bash
python -m pytest code/tests -q
python code/tools/check_parity.py
python code/evaluation/validate_output.py
```

Build and serve the Next.js static export:

```bash
cd frontend-next
npm run build
python -m http.server 8480 --bind 127.0.0.1 --directory out
```

The export contains the frontend only. Keep the Flask API running for live decisions and accounts.

## Vercel Hobby deployment

The root `vercel.json` publishes the Next.js static export and exposes the
existing Flask backend through `api/index.py`, a Vercel Python Function.
`/api/*` reaches Python; page and asset routes reach the static frontend.
Hosted pages call their own API origin. This does not require beta Services.

1. Link the repository root to your Vercel project using the Vercel CLI.
2. Connect a Neon **Free** database through Vercel Marketplace. Its integration
   supplies `DATABASE_URL` and `DATABASE_URL_UNPOOLED` to the project.
3. Deploy from the repository root with `vercel deploy --prod`.

The account tables are initialized through the direct database connection;
normal account traffic uses the pooled connection. Local accounts are not
automatically uploaded or migrated. Model API keys are optional, and no model
provider is enabled by the deployment configuration.

## Contributing

Issues and pull requests are welcome on [GitHub](https://github.com/ishxn-s11/kairos).

1. Fork the repository and create a focused feature branch.
2. Describe the problem or feature and keep the change small enough to review.
3. Add tests when changing engine, API, or account behavior.
4. Run the relevant checks above. Mirror changes to shared frontend assets before running the parity guard.
5. Open a pull request with a description of the change and how you verified it.

Keep calculations deterministic where possible and document financial assumptions. Use example data in bug reports, and exclude credentials, personal financial records, account databases, caches, and build output from commits.

## License

Kairos source code is released under the [MIT License](LICENSE). You may use, modify, and distribute it subject to the license terms.
