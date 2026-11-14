export const CATS = [
  { name: "Good", color: "#3DBE6B", text: "#10202e" },
  { name: "Moderate", color: "#F2D338", text: "#10202e" },
  { name: "Unhealthy for sensitive groups", color: "#F28C28", text: "#10202e" },
  { name: "Unhealthy", color: "#D93A2F", text: "#ffffff" },
  { name: "Very unhealthy", color: "#8F3F97", text: "#ffffff" },
  { name: "Hazardous", color: "#7E0023", text: "#ffffff" },
];
export const catFor = (name) => CATS.find((c) => c.name === name) ?? { color: "#9AA9B8", text: "#10202e" };
