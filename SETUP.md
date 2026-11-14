# Setup manual: from zip to a live site

Follow the steps in order. Each step ends with a check. Website menus change, so if a label
differs, follow the provider's current docs. Everything here uses free tiers; confirm current limits.

**You will end up with:** a GitHub repo running the schedules, a Supabase database, a model on DagsHub,
an API on Render, and a website on Vercel.

## 0. Accounts to create (all free)
GitHub, Supabase, DagsHub, Render, Vercel, Groq (console.groq.com), OpenAQ (explore.openaq.org).
Optional: a Discord or Slack channel with an incoming webhook for alerts.

## 1. Put the code on GitHub
1. Unzip, open a terminal in the folder `aqi-forecast`.
2. Create an **empty** GitHub repo (no README), then:
   ```
   git init && git add . && git commit -m "first commit"
   git branch -M main
   git remote add origin https://github.com/YOUR_USER/YOUR_REPO.git
   git push -u origin main
   ```
3. Open the **Actions** tab. If asked, click to enable workflows.

Check: the `ci` workflow runs. The `web` job should pass. (The first run may fail on lint; read the log.)

## 2. Database (Supabase)
1. New project. Save the database password somewhere safe.
2. Click **Connect** (or Project Settings, then Database) and copy the **Session pooler** connection string.
   It works from GitHub and Render (they may not support the direct IPv6 connection).
3. Replace `[YOUR-PASSWORD]` in it. If the password has symbols like `@ # / :` URL-encode them.
   This full string is your `SUPABASE_DB_URL`.
4. On your computer:
   ```
   python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
   pip install -r requirements-monitor.txt
   cp .env.example .env     # fill SUPABASE_DB_URL, then load it: set -a; source .env; set +a
   python -m scripts.init_db
   python -m scripts.check_setup
   ```
Check: the preflight shows "Database connection" and "Tables created" with a tick.
(Alternative to the script: paste `db/schema.sql` into the Supabase SQL editor.)

## 3. DagsHub (data versions + experiment tracking)
1. Create a DagsHub repo by connecting your GitHub repo (or create one and mirror it).
2. Settings, then Tokens: create a token. Note your DagsHub username.
3. Edit `.dvc/config` and replace `YOUR_USER/YOUR_REPO` in `endpointurl`
   (`https://dagshub.com/<user>/<repo>.s3`). Commit and push. Confirm the exact remote format in DagsHub's current docs.
4. Your MLflow address is `https://dagshub.com/<user>/<repo>.mlflow`.

## 4. GitHub secrets
Repo, then Settings, then Secrets and variables, then Actions, then **New repository secret**. Add:

| Secret | Value | Used by |
|---|---|---|
| `SUPABASE_DB_URL` | the session pooler string from step 2 | all workflows |
| `DAGSHUB_USER` | your DagsHub username | retrain |
| `DAGSHUB_TOKEN` | the DagsHub token | retrain |
| `MLFLOW_TRACKING_URI` | `https://dagshub.com/<user>/<repo>.mlflow` | retrain |
| `OPENAQ_API_KEY` | OpenAQ key (step 8) | validation |
| `ALERT_WEBHOOK_URL` | optional Discord/Slack webhook | failure + alert messages |

Secrets are never written to the repo. Do not paste them into files that get committed.

## 5. Load history and start the hourly jobs
1. Actions, then **backfill-history**, then Run workflow, start date `2024-01-01`.
   (Check Open-Meteo's docs for how far back air quality data exists; earlier dates just return less.)
   This can take a while. Check: the log prints rows per city.
2. Actions, then **hourly-ingest**, then Run workflow. Check: it succeeds. It now repeats every hour.
   (GitHub may start scheduled runs late. Public repos can have schedules paused after long inactivity: check GitHub's current rules.)

## 6. Train the first model
1. Actions, then **daily-retrain**, then Run workflow. It takes a while.
2. Open the run log and find the last lines: `PROMOTED` means the model is live; `REJECTED` lists why
   (for example too little history). Fix the cause and run it again.
3. Run **hourly-monitor** once by hand. It makes the first forecasts so the map has data.
4. Locally: `python -m scripts.check_setup` should now show a "Production model".

## 7. API (Render)
1. Render, then New, then **Blueprint**, pick your repo. It reads `render.yaml`.
2. Fill the prompted values:
   - `SUPABASE_DB_URL`: same string as before
   - `GROQ_API_KEY`: from console.groq.com, API Keys
   - `ALLOWED_ORIGINS`: for now `http://localhost:5173` (you will change it in step 9)
3. Deploy. Your API address looks like `https://aqi-api-xxxx.onrender.com`.
4. Open `<your-api>/health`, then `<your-api>/docs` (interactive docs), then `<your-api>/summary`.
Note: free Render services may sleep when idle, so the first request can take a minute.
The app shows a "waking the server" message while it waits.

## 8. OpenAQ ground-truth check
1. Register at explore.openaq.org and create an API key (see OpenAQ's docs for the current steps).
2. Add it as the GitHub secret `OPENAQ_API_KEY` (step 4).
3. Actions, then **daily-openaq-validation**, then Run workflow.
4. Check: the log prints one line per city, or "no PM2.5 stations with data nearby" for cities without stations.
   Results appear on the Model health page. Validation only measures; it never trains the model.

## 9. Website (Vercel)
1. Vercel, then Add New, then Project, import the repo.
2. Set **Root Directory** to `web`. Framework should detect Vite.
3. Environment variable `VITE_API_URL` = your Render URL (no trailing slash).
4. Deploy. You get `https://your-app.vercel.app`.
5. Go back to Render, then your service, then Environment. Set `ALLOWED_ORIGINS` to your Vercel URL
   (comma-separate extra ones; no trailing slash, no `*`). Save; it redeploys.

Check: open the site. The map shows coloured dots, a city page shows the chart, "Explain this forecast" returns text,
and Model health shows status. A browser console error mentioning CORS means step 9.5 is wrong.

## 10. Final live check
Run `python -m scripts.check_setup --api-url https://your-api.onrender.com --test-llm`.
All ticks (OpenAQ and Groq are optional) means you are live.

## Run it on your own computer (optional)
```
pip install -r requirements-monitor.txt -r api/requirements.txt
uvicorn api.main:app --reload            # API at http://localhost:8000/docs
cd web && cp .env.example .env && npm install && npm run dev    # site at http://localhost:5173
```
Training locally also needs PyTorch (see pytorch.org) and `pip install -r requirements.txt`.

## Day-to-day
- Roll back a bad model: with your `.env` loaded, run `python -m src.models.rollback`.
- Alerts: with a webhook set you get messages when ingest or retrain fails or the model alerts.
- Change cities: edit `params.yaml`, push, run backfill, then retrain (the old model is replaced only if the gate allows).
- Keep the API awake (optional): a free uptime pinger hitting `/health` every few minutes. Check Render's current policy first.

## Troubleshooting
| Symptom | Likely cause and fix |
|---|---|
| `password authentication failed` | wrong password or not URL-encoded; use the session pooler string |
| Map empty, API says "No production model yet" | run retrain (step 6) and read PROMOTED/REJECTED |
| Map dots grey | run **hourly-monitor** once; it stores the first forecasts |
| Retrain REJECTED on first run | read the printed reasons; usually too little history or coverage outside 75-85%; backfill more |
| Retrain fails at `dvc push` | check `.dvc/config` endpoint, DagsHub token secrets |
| CORS error in browser | `ALLOWED_ORIGINS` must equal the exact Vercel URL |
| Explain shows a plain sentence | no `GROQ_API_KEY`, quota used, wrong `GROQ_MODEL`, or the AI text contained an unknown number (by design) |
| Render fails at start with ALLOWED_ORIGINS message | set it (production mode refuses `*`) |
| Workflows never run on schedule | Actions disabled, or repo inactive; run once by hand |
| OpenAQ lines say no stations | normal for some cities; try a larger radius in `src/validation/openaq.py` |

## What I could not test for you
The Python code was syntax-checked and 17 unit tests were written (the ones that could run here pass). I could not
run the full pipeline, the Vite build, or any hosted service from this environment, so run step 10 and read the first
workflow logs carefully. Provider details (DagsHub remote format, OpenAQ endpoints, Groq model names, free-tier limits)
change; verify them in the providers' current docs.
