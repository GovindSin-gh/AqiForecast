import { useState } from "react";
import { Link } from "react-router-dom";
import { CircleMarker, MapContainer, Popup, TileLayer } from "react-leaflet";
import { useFetch } from "../api.js";
import Status from "../components/Status.jsx";
import Badge from "../components/Badge.jsx";
import { CATS, catFor } from "../categories.js";

const MODES = [["now", "Now"], ["next_hour", "Next hour"], ["peak_24h", "24 h peak"]];

export default function MapPage() {
  const [mode, setMode] = useState("now");
  const state = useFetch("/summary");
  return (
    <section>
      <h1>Air quality across India</h1>
      <p>Model-based estimates and forecasts, not readings from a street-level sensor.</p>
      <div className="ctl" role="group" aria-label="Map view">
        {MODES.map(([k, t]) => (
          <button key={k} aria-pressed={mode === k} onClick={() => setMode(k)}>{t}</button>
        ))}
      </div>
      <Status state={state}>
        {state.data && (
          <MapContainer center={[22.5, 79]} zoom={5} scrollWheelZoom={false} className="map">
            <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
              url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" />
            {state.data.map((c) => {
              const cell = c[mode];
              const col = catFor(cell?.category).color;
              return (
                <CircleMarker key={c.id} center={[c.lat, c.lon]} radius={14}
                  pathOptions={{ color: "#1B2B3A", weight: 2, fillColor: col, fillOpacity: 0.9 }}>
                  <Popup>
                    <strong>{c.name}</strong><br />
                    {cell ? <Badge aqi={cell.aqi} category={cell.category} /> : "No data yet"}<br />
                    <Link to={`/city/${c.id}`}>Open city page</Link>
                  </Popup>
                </CircleMarker>
              );
            })}
          </MapContainer>
        )}
      </Status>
      <ul className="legend">
        {CATS.map((c) => (<li key={c.name}><i style={{ background: c.color }} />{c.name}</li>))}
      </ul>
    </section>
  );
}
