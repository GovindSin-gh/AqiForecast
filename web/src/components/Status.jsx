/** Shared loading / error wrapper. */
export default function Status({ state, children }) {
  if (state.loading)
    return <p role="status">{state.slow ? "Waking the server (free hosting sleeps when idle). This can take a minute." : "Loading…"}</p>;
  if (state.error) return <p className="err" role="alert">Could not load data: {state.error}</p>;
  return children;
}
