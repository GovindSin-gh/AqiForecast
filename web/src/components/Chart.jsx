import { Area, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const label = (x) => (x === 0 ? "now" : x < 0 ? `\u2212${-x} h` : `+${x} h`);

export function buildRows(history, forecast) {
  const rows = history.map((p, i) => ({ x: i - (history.length - 1), hist: p.aqi }));
  const last = rows.length ? rows[rows.length - 1] : null;
  if (last && last.hist != null) Object.assign(last, { p50: last.hist, lo: last.hist, band: 0 });
  forecast.forEach((p) =>
    rows.push({ x: p.h, p50: p.aqi_p50, lo: p.aqi_p10, band: p.aqi_p90 - p.aqi_p10 })
  );
  return rows;
}

export default function Chart({ history, forecast }) {
  const rows = buildRows(history, forecast);
  return (
    <div className="chart" role="img" aria-label="AQI history for 48 hours and forecast with uncertainty band">
      <ResponsiveContainer width="100%" height={320}>
        <ComposedChart data={rows} margin={{ top: 10, right: 16, bottom: 4, left: 0 }}>
          <CartesianGrid stroke="#C9D6E2" />
          <XAxis dataKey="x" type="number" domain={["dataMin", "dataMax"]} tickFormatter={label} tickCount={8} />
          <YAxis domain={[0, "auto"]} width={40} />
          <Tooltip labelFormatter={label}
            formatter={(v, name) => (name === "band" || name === "lo" ? null : [Math.round(v), name === "hist" ? "Observed" : "Forecast (median)"])} />
          <ReferenceLine x={0} stroke="#1B2B3A" strokeDasharray="4 4" />
          <Area dataKey="lo" stackId="b" stroke="none" fill="transparent" isAnimationActive={false} connectNulls />
          <Area dataKey="band" stackId="b" stroke="none" fill="#2F5D8A" fillOpacity={0.25} isAnimationActive={false} connectNulls />
          <Line dataKey="hist" stroke="#1B2B3A" strokeWidth={2} dot={false} isAnimationActive={false} connectNulls />
          <Line dataKey="p50" stroke="#2F5D8A" strokeWidth={2.5} dot={false} isAnimationActive={false} connectNulls />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
