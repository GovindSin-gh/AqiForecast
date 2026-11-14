import { catFor } from "../categories.js";

export default function Badge({ aqi, category }) {
  const c = catFor(category);
  return (
    <span className="badge" style={{ background: c.color, color: c.text }}>
      <b>{aqi}</b> {category}
    </span>
  );
}
