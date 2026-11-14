# AQI Forecast

Hour-by-hour PM2.5 / US AQI forecasts for 8 Indian cities (10/50/90 percentile bands), with a self-retraining
model, hourly self-scoring, a promotion gate, and an OpenAQ ground-station check. Values are model-based, not street sensors.

- **Go live:** read `SETUP.md` (step-by-step, including every key and secret).
- **Understand it:** open `docs/PROJECT_GUIDE.html` in a browser (flowcharts, structure, data model).
- **Local run:** see the end of `SETUP.md` step 2, then `uvicorn api.main:app --reload` and `cd web && npm install && npm run dev`.
- **Preflight check:** `python -m scripts.check_setup`
