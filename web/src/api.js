import { useEffect, useState } from "react";

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export async function api(path, options) {
  const res = await fetch(BASE + path, options);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail ?? detail; } catch { /* not JSON */ }
    throw new Error(detail);
  }
  return res.json();
}

/** Fetch on mount / path change. `slow` flips on after 3 s: a free Render server may be waking up. */
export function useFetch(path) {
  const [s, set] = useState({ data: null, error: null, loading: true, slow: false });
  useEffect(() => {
    let alive = true;
    set({ data: null, error: null, loading: true, slow: false });
    const t = setTimeout(() => alive && set((p) => (p.loading ? { ...p, slow: true } : p)), 3000);
    api(path)
      .then((data) => alive && set({ data, error: null, loading: false, slow: false }))
      .catch((e) => alive && set({ data: null, error: e.message, loading: false, slow: false }))
      .finally(() => clearTimeout(t));
    return () => { alive = false; clearTimeout(t); };
  }, [path]);
  return s;
}
