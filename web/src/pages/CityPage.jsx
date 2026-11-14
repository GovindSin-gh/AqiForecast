import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useFetch } from "../api.js";
import Status from "../components/Status.jsx";
import Badge from "../components/Badge.jsx";
import Chart from "../components/Chart.jsx";
import ExplainButton from "../components/ExplainButton.jsx";

export default function CityPage() {
  const { id } = useParams();
  const [horizon, setHorizon] = useState(24);
  const hist = useFetch(`/history/${id}?hours=48`);
  const fc = useFetch(`/forecast/${id}?horizon=24`);   // fetch once, slice locally

  const points = fc.data ? fc.data.points.slice(0, horizon) : [];
  const headline = points.length
    ? horizon === 1 ? points[0] : points.reduce((a, b) => (b.pm25_p50 > a.pm25_p50 ? b : a))
    : null;

  return (
    <section>
      <p><Link to="/">← Map</Link></p>
      <h1 style={{ textTransform: "capitalize" }}>{id}</h1>
      <div className="ctl" role="group" aria-label="Forecast range">
        <button aria-pressed={horizon === 1} onClick={() => setHorizon(1)}>Next hour</button>
        <button aria-pressed={horizon === 24} onClick={() => setHorizon(24)}>Next 24 hours</button>
      </div>
      <Status state={fc}>
        {fc.data?.stale && <p className="warn" role="status">Data for this city is stale. The forecast may be out of date.</p>}
        {headline && (
          <p aria-live="polite">
            {horizon === 1 ? "Next hour" : "Peak in the next 24 hours"}:{" "}
            <Badge aqi={headline.aqi_p50} category={headline.category} />{" "}
            <span className="small">likely {headline.aqi_p10}–{headline.aqi_p90}</span>
          </p>
        )}
        <Status state={hist}>
          {hist.data && <Chart history={hist.data.points} forecast={points} />}
        </Status>
        <ul className="legend small">
          <li><i style={{ background: "#1B2B3A" }} />Observed (48 h)</li>
          <li><i style={{ background: "#2F5D8A" }} />Forecast median</li>
          <li><i style={{ background: "#2F5D8A", opacity: 0.3 }} />10th–90th percentile band</li>
        </ul>
        <ExplainButton city={id} horizon={horizon} />
        <p className="small">Model version {fc.data?.model_version}. Estimates come from a model, not a ground sensor.</p>
      </Status>
    </section>
  );
}
