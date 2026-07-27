# 💚 Citta Companion

**Employee Wellbeing Discovery** — an AI-powered, empathetic chatbot that helps
employees reflect on their wellbeing and identifies useful support, while keeping
personal responses private from employers.

> ⚠️ **Citta Companion is not therapy, diagnosis or an emergency service.**

---

## ✨ Features

- 🤝 **Empathetic discovery chat** — one gentle question at a time, powered by Google Gemini.
- 🔒 **Privacy-first** — employers never see personal responses; only aggregate summaries.
- 🚨 **Crisis detection** — deterministic keyword safety net that immediately surfaces emergency guidance and alerts an administrator.
- 📊 **Structured summaries** — a JSON wellbeing summary (stress, sleep, burnout, workload, manager relationship, and more).
- 📝 **Google Sheets persistence** — summaries, risk flags and support leads.
- 📧 **Email alerts** — admin notifications on risk events (placeholder SMTP config).
- 🌐 **URL-driven context** — `?id=...&sector=...&lang=...`.
- 🧩 **Modular, PEP8, production-ready** codebase.

---

## 🗂️ Project structure

```
citta-companion/
├── server.py             # Flask server — primary UI (pixel-perfect reference design)
├── templates/
│   └── index.html        # Frontend ported 1:1 from "Citta Companion Chat" design
├── app.py                # Legacy Streamlit UI & flow orchestration
├── config.py             # Env-driven configuration
├── prompts.py            # System prompt, summary prompt, static copy
├── gemini_service.py     # Gemini init + response generation
├── google_sheets.py      # Google Sheets persistence (Streamlit-independent)
├── risk_detection.py     # Keyword-based crisis detection
├── summary_generator.py  # Structured JSON summary
├── email_service.py      # Admin alert / welcome email (placeholders)
├── utils.py              # Session state & UI helpers
├── requirements.txt
├── README.md
├── .env.example
├── assets/
│   └── logo.png
├── .streamlit/
│   └── config.toml
└── services/
    └── __init__.py
```

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

Then edit `.env` and fill in your values (see setup sections below).

---

## ▶️ Run locally

```bash
python server.py
```

Open the app with context parameters, for example:

```
http://localhost:8000/?id=CITTA-EMP001&sector=IT&lang=en
```

The UI is a pixel-perfect implementation of the approved **"Citta Companion
Chat"** design (dark + light themes, toggle in the header; the choice is
remembered per browser).

> The legacy Streamlit UI is still available via `streamlit run app.py`
> (port 8501), but it only approximates the design — `server.py` is the
> primary entry point.

| Parameter | Meaning              | Example        |
|-----------|----------------------|----------------|
| `id`      | Employee identifier  | `CITTA-EMP001` |
| `sector`  | Business sector      | `IT`           |
| `lang`    | Language code        | `en`           |

---

## 🔑 Gemini API setup

1. Visit **[Google AI Studio](https://aistudio.google.com/app/apikey)**.
2. Create an API key.
3. Add it to `.env`:

   ```env
   GEMINI_API_KEY=your-gemini-api-key-here
   GEMINI_MODEL_NAME=gemini-1.5-flash
   ```

The key is read only from the environment — it is **never hardcoded**.

---

## 📄 Google Sheets setup

1. Go to the **[Google Cloud Console](https://console.cloud.google.com/)**.
2. Create (or select) a project.
3. Enable the **Google Sheets API** and **Google Drive API**.
4. Create a **Service Account** and generate a **JSON key**.
5. Save the JSON key in the project root as `service_account.json`
   (or point `GOOGLE_CREDENTIALS_FILE` at its path).
6. Create a Google Spreadsheet (e.g. named `Citta Companion`).
7. **Share** the spreadsheet with the service account's email
   (`...@...iam.gserviceaccount.com`) as an **Editor**.
8. Configure `.env`:

   ```env
   GOOGLE_CREDENTIALS_FILE=service_account.json
   GOOGLE_SHEET_KEY=            # from the spreadsheet URL, or leave blank
   GOOGLE_SHEET_NAME=Citta Companion
   ```

Worksheets (`Summaries`, `RiskFlags`, `SupportLeads`) and their headers are
created automatically on first write.

---

## 📧 Email setup (optional)

Email uses placeholder SMTP settings. Until a real password is provided
(`SMTP_PASSWORD` other than `REPLACE_ME`), alerts are **logged instead of sent**,
so local development works without credentials.

```env
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=no-reply@example.com
SMTP_PASSWORD=REPLACE_ME
SMTP_USE_TLS=true
EMAIL_FROM=Citta Companion <no-reply@example.com>
ADMIN_ALERT_EMAIL=wellbeing-admin@example.com
```

---

## ☁️ Deployment

### Streamlit Community Cloud

1. Push the repo to GitHub.
2. On **[share.streamlit.io](https://share.streamlit.io/)**, create a new app
   pointing at `app.py`.
3. Add your secrets under **App → Settings → Secrets** (mirroring `.env`):

   ```toml
   GEMINI_API_KEY = "..."
   GEMINI_MODEL_NAME = "gemini-1.5-flash"
   GOOGLE_SHEET_NAME = "Citta Companion"
   # ... etc.
   ```

   For Google credentials, paste the service-account JSON contents into a secret
   and write it to `service_account.json` at startup, or mount it via your
   platform's secret store.

### Docker (generic)

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

```bash
docker build -t citta-companion .
docker run -p 8501:8501 --env-file .env citta-companion
```

---

## 🛡️ Safety & error handling

- **Crisis keywords** immediately pause normal conversation and display
  emergency guidance — the AI is not relied upon for this decision.
- **Gemini, Google Sheets and network failures** degrade gracefully with
  friendly messages; the conversation is never lost mid-session.
- Secrets are kept out of source control via `.gitignore`.

---

## 🧪 Development notes

- Code follows **PEP8** and is organised into single-responsibility modules.
- The persistence and email layers are **independent of Streamlit** and can be
  unit-tested or reused elsewhere.
- Conversation state is held entirely in `st.session_state`.

---

## 📜 License

Add your preferred license (e.g. MIT) here.
