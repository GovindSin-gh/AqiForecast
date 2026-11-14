-- Run once in the Supabase SQL editor.
create table if not exists cities (
  id text primary key, name text not null,
  lat double precision not null, lon double precision not null
);
create table if not exists observations (
  city_id text references cities(id), ts timestamptz not null,
  pm25 real, pm10 real, us_aqi real,
  temp_c real, rh real, wind_ms real, wind_dir real, pressure_hpa real, rain_mm real,
  source text default 'open-meteo',
  primary key (city_id, ts)
);
create table if not exists benchmark_forecasts (   -- Open-Meteo's own forecast, saved at ingest time
  city_id text references cities(id), issued_at timestamptz not null,
  valid_at timestamptz not null, pm25 real,
  primary key (city_id, issued_at, valid_at)
);
create table if not exists model_runs (
  version text primary key, stage text not null,     -- production | archived | rejected | rolled_back
  mae real, coverage real, metrics jsonb, reasons text[], mlflow_run_id text,
  created_at timestamptz default now(), promoted_at timestamptz
);
create unique index if not exists one_production on model_runs (stage) where stage = 'production';
create table if not exists model_artifacts (
  version text primary key references model_runs(version),
  onnx bytea not null, scaler jsonb not null
);
create table if not exists forecasts (
  city_id text references cities(id), issued_at timestamptz not null,
  horizon_h smallint not null check (horizon_h between 1 and 24),
  p10 real, p50 real, p90 real, model_version text not null,
  primary key (city_id, issued_at, horizon_h)
);
create table if not exists scores (
  city_id text, ts timestamptz, horizon_h smallint, abs_err real, model_version text,
  primary key (city_id, ts, horizon_h, model_version)
);
create table if not exists monitor_log (
  ts timestamptz primary key default now(), model_version text,
  rolling_mae real, baseline_mae real, ratio real, status text,
  drift_flag boolean default false, stale_cities text[]
);
-- The app talks to Postgres directly, not through Supabase's public API.
-- Row level security with no policies keeps the public API locked out.
alter table cities enable row level security;
alter table observations enable row level security;
alter table benchmark_forecasts enable row level security;
alter table model_runs enable row level security;
alter table model_artifacts enable row level security;
alter table forecasts enable row level security;
alter table scores enable row level security;
alter table monitor_log enable row level security;

-- OpenAQ ground truth + validation results
create table if not exists ground_truth (
  city_id text references cities(id), ts timestamptz not null, pm25 real, n_sensors smallint,
  primary key (city_id, ts)
);
create table if not exists validation_log (
  id bigserial primary key, ts timestamptz default now(), city_id text,
  n integer, mae real, bias real, corr real, n_sensors smallint
);
alter table ground_truth enable row level security;
alter table validation_log enable row level security;
