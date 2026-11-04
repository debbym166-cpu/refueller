/*
 * Price History page - a small hand-rolled SVG line chart.
 * No charting library: just enough JS to turn a list of {date, price}
 * points (rendered into the page by Django via `json_script`) into an SVG
 * polyline. Good enough for a teaching project, and easy to read.
 */
document.addEventListener("DOMContentLoaded", function () {
  const dataEl = document.getElementById("price-data");
  const svg = document.getElementById("price-chart");
  if (!dataEl || !svg) return;

  const points = JSON.parse(dataEl.textContent); // oldest -> newest: [{date, price}, ...]
  if (points.length < 2) {
    svg.parentElement.innerHTML = '<p class="text-faint text-sm">Not enough price history yet to draw a chart.</p>';
    return;
  }

  const width = 600;
  const height = 200;
  const padding = 16;

  const prices = points.map((p) => p.price);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const range = max - min || 1;

  const coords = points.map((p, i) => {
    const x = padding + (i / (points.length - 1)) * (width - padding * 2);
    const y = height - padding - ((p.price - min) / range) * (height - padding * 2);
    return [x, y];
  });

  const linePoints = coords.map(([x, y]) => `${x},${y}`).join(" ");
  const areaPoints = `${padding},${height - padding} ${linePoints} ${width - padding},${height - padding}`;

  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.innerHTML = `
    <polygon points="${areaPoints}" fill="var(--green-100)" opacity="0.6"></polygon>
    <polyline points="${linePoints}" fill="none" stroke="var(--green-600)" stroke-width="2.5"
      stroke-linecap="round" stroke-linejoin="round"></polyline>
    ${coords.map(([x, y]) => `<circle cx="${x}" cy="${y}" r="3" fill="var(--green-700)"></circle>`).join("")}
  `;
});
