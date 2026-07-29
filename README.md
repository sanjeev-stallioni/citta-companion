# 💚 Citta Companion

**Employee Wellbeing Discovery** — an AI-powered, empathetic chatbot that helps
employees reflect on their wellbeing and identifies useful support, while keeping
personal responses private from employers.

> ⚠️ **Citta Companion is not therapy, diagnosis or an emergency service.**

---

## ✨ Features

- 🤝 **Empathetic discovery chat** — one gentle question at a time, powered by Google Gemini.
- 🔒 **Privacy-first** — employers never see personal responses; only aggregate summaries.
- 🔗 **Signed employee links** — the chat URL is HMAC-signed, so nobody can edit it and open someone else's session.
- 🚨 **Crisis detection** — deterministic keyword safety net that immediately surfaces emergency guidance and alerts an administrator.
- 📊 **Structured summaries** — a JSON wellbeing summary (stress, sleep, burnout, workload, manager relationship, and more).
- 📝 **Google Sheets persistence** — chat summaries, risk flags and support leads.
- 📧 **Email alerts** — admin notifications on risk events and callback requests.
- 🌐 **Seven languages** — en, hi, kn, ta, te, mr, bn.

---

## 🗂️ Project structure

```
citta-companion/
├── app.py                # Streamlit UI — THE DEPLOYED ENTRY POINT
├── styles.py             # All CSS for the Streamlit UI
├── server.py             # Flask server — local-only, pixel-perfect reference UI
├── templates/
│   ├── index.html        # Frontend ported 1:1 from the "Citta Companion Chat" design
│   └── invalid_link.html # Shown when a chat link fails verification
├── link_tokens.py        # Signs and verifies employee links (no framework imports)
├── make_link.py          # CLI to generate a signed link or a new LINK_SECRET
├── config.py             # Env-driven configuration
├── prompts.py            # System prompt, summary prompt, static copy
├── gemini_service.py     # Gemini init + response generation + JSON mode
├── summary_generator.py  # Structured JSON summary
├── risk_detection.py     # Keyword-based crisis detection
├── google_sheets.py      # Google Sheets persistence (framework-independent)
├── email_service.py      # Admin alerts
├── utils.py              # Query params, session state, helpers
├── static/               # favicon + logo mark (served by Flask)
├── assets/               # logo images used by the Streamlit UI
├── .streamlit/config.toml
├── .env.example
└── requirements.txt
```

### Two UIs, one backend

Both entry points share every module below them — Gemini, Sheets, risk
detection, link verification.

| | `app.py` (Streamlit) | `server.py` (Flask) |
|---|---|---|
| Status | **deployed and live** | local only |
| Why | Streamlit Cloud cannot host Flask | pixel-perfect against the approved design |
| Port | 8501 | 8000 |

Streamlit Cloud runs `app.py`. If you change the UI, change it there — editing
`templates/index.html` has no effect on the live app.

---

## 🚀 Installation

### 1. Clone

```bash
git clone <your-repo-url> citta-companion
cd citta-companion
```

### 2. Create a virtual environment

**Python 3.12** is recommended.

```bash
python3.12 -m venv .venv
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate         # Windows (PowerShell)
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
```

Then edit `.env` and fill in your values (see the setup sections below).

---

## ▶️ Run locally

```bash
streamlit run app.py          # the deployed UI, port 8501
python3 server.py             # the reference Flask UI, port 8000
```

Then open a **signed** link — see the next section.

---

## 🔗 Signed employee links

The chat URL carries the employee ID, sector and language. Those must not be
hand-editable, or anyone could open a session as any employee, so they travel
inside a token signed with a shared secret:

```
https://<host>/?t=<payload>.<signature>

payload   = base64url("employee_id|sector|lang|expiry")
signature = HMAC-SHA256(LINK_SECRET, payload)
```

Generate a secret once, put it in `.env` (and in Streamlit's secrets), then mint
links:

```bash
python3 make_link.py --secret                    # print a new LINK_SECRET
python3 make_link.py CITTA-EMP001 IT en          # print a signed link
python3 make_link.py CITTA-EMP001 IT en --ttl-days 30
```

> **Once `LINK_SECRET` is set, plain `?id=...&sector=...&lang=...` links stop
> working** — by design. Leave it empty for local development and the old
> parameters still work.

Signatures are accepted in either base64url or hex, because automation tools
(Make.com) emit hex. Verification is constant-time.

---

## 🔑 Gemini API setup

1. Visit **[Google AI Studio](https://aistudio.google.com/app/apikey)**.
2. Create an API key.
3. Add it to `.env`:

   ```env
   GEMINI_API_KEY=your-gemini-api-key-here
   GEMINI_MODEL_NAME=gemini-flash-latest
   ```

The key is read only from the environment — it is **never hardcoded**.

---

## 📄 Google Sheets setup

1. Go to the **[Google Cloud Console](https://console.cloud.google.com/)**.
2. Create (or select) a project.
3. Enable the **Google Sheets API** and **Google Drive API**.
4. Create a **Service Account** and generate a **JSON key**.
5. Save it in the project root as `service_account.json` (gitignored), or point
   `GOOGLE_CREDENTIALS_FILE` at its path.
6. **Share** the spreadsheet with the service account's email
   (`...@...iam.gserviceaccount.com`) as an **Editor**. Skipping this is the
   most common failure: the app looks like it works, but no rows ever appear.
7. Configure `.env`:

   ```env
   GOOGLE_CREDENTIALS_FILE=service_account.json
   GOOGLE_SHEET_KEY=              # the long id from the spreadsheet URL
   GOOGLE_SHEET_NAME=Citta Companion
   WORKSHEET_SUMMARIES=Chat Summaries
   WORKSHEET_RISK_FLAGS=Risk Flags
   WORKSHEET_SUPPORT_LEADS=Support Leads
   ```

Worksheets and their headers are created automatically on first write — which
means **a typo in a worksheet name produces a second, empty tab rather than an
error**. The names must match the spreadsheet exactly.

Column order in `google_sheets.py` mirrors the live spreadsheet, and rows are
appended positionally. Reordering a column in the sheet without updating
`_HEADERS` will silently write every value one column out of place.

---

## 📧 Email setup

Alerts are **logged instead of sent** while `SMTP_PASSWORD` is `REPLACE_ME`, so
local development works without credentials.

For Gmail you need an [App Password](https://myaccount.google.com/apppasswords)
(2-Step Verification must be on first) — a normal account password will not
work:

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=you@yourdomain.com
SMTP_PASSWORD=your16charapppassword   # spaces removed
SMTP_USE_TLS=true
EMAIL_FROM=Citta Companion <you@yourdomain.com>
ADMIN_ALERT_EMAIL=who-gets-risk-alerts@example.com
```

---

## ☁️ Deployment — Streamlit Community Cloud

1. Push the repo to GitHub.
2. On **[share.streamlit.io](https://share.streamlit.io/)**, create an app
   pointing at **`app.py`**, branch `main`.
3. Add secrets under **Manage app → Settings → Secrets**:

   ```toml
   GEMINI_API_KEY = "..."
   GEMINI_MODEL_NAME = "gemini-flash-latest"

   GOOGLE_SHEET_KEY = "..."
   WORKSHEET_SUMMARIES = "Chat Summaries"
   WORKSHEET_RISK_FLAGS = "Risk Flags"
   WORKSHEET_SUPPORT_LEADS = "Support Leads"
   GOOGLE_CREDENTIALS_JSON = '''
   {  ...the entire service_account.json contents...  }
   '''

   LINK_SECRET = "..."
   LINK_TTL_DAYS = "0"
   APP_BASE_URL = "https://your-app.streamlit.app"

   SMTP_HOST = "smtp.gmail.com"
   SMTP_PORT = "587"
   SMTP_USE_TLS = "true"
   SMTP_USERNAME = "..."
   SMTP_PASSWORD = "..."
   EMAIL_FROM = "Citta Companion <...>"
   ADMIN_ALERT_EMAIL = "..."
   ```

   The deployed app has no writable file system, so `GOOGLE_CREDENTIALS_JSON`
   takes the key's contents directly — there's no need to write
   `service_account.json` at startup. Keep the `'''` triple quotes: with `"""`,
   TOML would turn the `\n` escapes inside the private key into real line breaks
   and the JSON becomes invalid.

4. **Reboot** the app after saving secrets. A plain rerun does not reload
   changed Python modules, which is also why a fresh `git push` often appears to
   have had no effect.

---

## 🛡️ Safety & error handling

- **Crisis keywords** immediately pause normal conversation and display
  emergency guidance — the AI is not relied upon for this decision.
- **Gemini, Google Sheets and network failures** degrade gracefully; a Sheets
  outage never interrupts someone's conversation.
- **Invalid links** are refused before any conversation starts.
- Secrets are kept out of source control via `.gitignore` — `.env` and
  `service_account.json` are both ignored.

---

## 🧪 Development notes

- Code follows **PEP8** and is organised into single-responsibility modules.
- `google_sheets.py`, `email_service.py`, `risk_detection.py` and
  `link_tokens.py` import no web framework, so they can be unit-tested or reused
  elsewhere.
- Conversation state lives in `st.session_state` (Streamlit) or the in-memory
  `SESSIONS` dict (Flask). **Neither survives a restart, and `SESSIONS` has no
  eviction** — fine for a pilot, needs revisiting before sustained use.

---

## 📜 License

Add your preferred license (e.g. MIT) here.
