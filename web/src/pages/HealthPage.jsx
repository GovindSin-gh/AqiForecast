import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useFetch } from "../api.js";
import Status from "../components/Status.jsx";

const PILL = { healthy: "#3DBE6B", watching: "#F2D338", alert: "#D93A2F" };
const fmt = (t) => (t ? new Date(t).toLocaleString() : "n/a");

export default function HealthPage() {
  const s = useFetch("/model/health");
  const v = useFetch("/validation");
  const d = s.data;
  return (
    <section>
      <h1>Model health</h1>
      <Status state={s}>
        {d && (
          <>
            <p>
              <span className="pill" style={{ background: PILL[d.status] ?? "#9AA9B8", color: d.status === "alert" ? "#fff" : "#10202e" }}>
                {d.status}
              </span>{" "}
              model {d.model_version ?? "none yet"}
            </p>
            <dl className="facts">
              <dt>Rolling 24 h error</dt>
              <dd>{d.rolling_mae_24h?.toFixed(1) ?? "n/a"} vs normal {d.baseline_mae?.toFixed(1) ?? "n/a"}</dd>
              <dt>Data drift</dt><dd>{d.drift_flag ? "Flagged, review the drift report" : "None flagged"}</dd>
              <dt>Last data</dt><dd>{fmt(d.last_ingest)}</dd>
              <dt>Last promotion</dt><dd>{fmt(d.last_promotion)}</dd>
              <dt>Stale cities</dt><dd>{d.stale_cities.length ? d.stale_cities.join(", ") : "None"}</dd>
            </dl>
            <h2>Error ratio, last 48 checks</h2>
            <p className="small">1.0 means as accurate as at promotion. The alert line is 1.3.</p>
            <div className="chart" role="img" aria-label="Rolling error ratio over recent hourly checks">
              <ResponsiveContainer width="100%" height={240}>
                <LineChart data={d.recent.map((r) => ({ t: new Date(r.ts).getHours() + ":00", ratio: r.ratio }))}>
                  <CartesianGrid stroke="#C9D6E2" /><XAxis dataKey="t" /><YAxis domain={[0, "auto"]} width={36} /><Tooltip />
                  <ReferenceLine y={1.3} stroke="#D93A2F" strokeDasharray="6 4" />
                  <Line dataKey="ratio" stroke="#2F5D8A" strokeWidth={2.5} dot={false} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <h2>Check against real stations (OpenAQ)</h2>
            <p className="small">How far our model-based values are from ground stations over the last 30 days. “Gap” is the average difference in µg/m³; “bias” above zero means we read higher than the stations.</p>
            <Status state={v}>
              {v.data && v.data.length === 0 && <p>No comparison yet. It appears once the daily validation has run.</p>}
              {v.data && v.data.length > 0 && (
                <div className="scroll"><table>
                  <thead><tr><th>City</th><th>Hours compared</th><th>Gap</th><th>Bias</th><th>Correlation</th><th>Stations</th></tr></thead>
                  <tbody>{v.data.map((r) => (
                    <tr key={r.city}><td style={{ textTransform: "capitalize" }}>{r.city}</td><td>{r.hours}</td>
                      <td>{r.mae.toFixed(1)}</td><td>{r.bias.toFixed(1)}</td><td>{r.corr == null ? "n/a" : r.corr.toFixed(2)}</td><td>{r.stations}</td></tr>
                  ))}</tbody>
                </table></div>
              )}
            </Status>
            <h2>Recent models</h2>
            <ul>{d.runs.map((r) => (<li key={r.version}>{r.version}: {r.stage} ({fmt(r.created_at)})</li>))}</ul>
          </>
        )}
      </Status>
    </section>
  );
}
