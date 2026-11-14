import { useState } from "react";
import { api } from "../api.js";

export default function ExplainButton({ city, horizon }) {
  const [state, setState] = useState({ busy: false, text: null, source: null, error: null });

  async function run() {
    setState({ busy: true, text: null, source: null, error: null });
    try {
      const r = await api("/explain", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ city, horizon }),
      });
      setState({ busy: false, text: r.text, source: r.source, error: null });
    } catch (e) {
      setState({ busy: false, text: null, source: null, error: e.message });
    }
  }

  return (
    <div className="explain">
      <button className="go" onClick={run} disabled={state.busy}>
        {state.busy ? "Explaining…" : "Explain this forecast"}
      </button>
      <div aria-live="polite">
        {state.text && (
          <>
            <p>{state.text}</p>
            <p className="small">
              {state.source === "llm" ? "AI-written summary of the model’s numbers." : "Plain summary (AI unavailable)."}{" "}
              The forecast itself comes from the LSTM model.
            </p>
          </>
        )}
        {state.error && <p className="err">Could not explain: {state.error}</p>}
      </div>
    </div>
  );
}
