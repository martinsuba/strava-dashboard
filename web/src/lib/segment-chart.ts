// "Time by date" scatter chart (docs/DESIGN.md "Segment page"). Chart.js with only the parts used:
// scatter controller, two linear scales, points, tooltip. x = epoch ms (year ticks formatted here,
// so no date adapter), y = elapsed seconds, reversed so that faster is higher.
import {
  Chart,
  LinearScale,
  PointElement,
  ScatterController,
  Tooltip,
  type Plugin,
} from "chart.js";
import { formatDate, formatDuration } from "./format";
import { chartLabel, visibleYears, type ChartModel, type Effort } from "./segment-data";

Chart.register(ScatterController, LinearScale, PointElement, Tooltip);

const ORANGE = "#FC4C02";
const EFFORT = "#8A8A96";
const MUTED = "#5E5E6A";
const GRID = "#ECECF2";
const AXIS = "#C4C4CF";
const FONT = '"Public Sans", system-ui, sans-serif';

let current: Chart | null = null;

export function disposeSegmentChart(): void {
  current?.destroy();
  current = null;
}

/** Draws "PR m:ss" next to the PR point (right of it, or left when it is near the right edge). */
function prLabelPlugin(model: ChartModel): Plugin<"scatter"> {
  return {
    id: "prLabel",
    afterDatasetsDraw(chart) {
      const { ctx, chartArea, scales } = chart;
      const x = scales["x"]?.getPixelForValue(model.pr.x);
      const y = scales["y"]?.getPixelForValue(model.pr.y);
      if (x === undefined || y === undefined) return;
      const left = x > chartArea.left + (chartArea.right - chartArea.left) * 0.75;
      ctx.save();
      ctx.fillStyle = ORANGE;
      ctx.font = `600 14px ${FONT}`;
      ctx.textBaseline = "middle";
      ctx.textAlign = left ? "right" : "left";
      ctx.fillText(`PR ${formatDuration(model.pr.y)}`, x + (left ? -14 : 14), y);
      ctx.restore();
    },
  };
}

/** Publishes the plot area (CSS px, canvas-relative) as data attributes; used by acceptance tests. */
const plotAreaPlugin: Plugin<"scatter"> = {
  id: "plotArea",
  afterDraw(chart) {
    // Largest horizontal distance (CSS px) between a drawn point and where the scale puts its date.
    const xs = chart.scales["x"];
    let worst = 0;
    chart.data.datasets.forEach((ds, i) => {
      chart.getDatasetMeta(i).data.forEach((el, j) => {
        const raw = ds.data[j] as { x: number } | undefined;
        if (xs && raw) worst = Math.max(worst, Math.abs(el.x - xs.getPixelForValue(raw.x)));
      });
    });
    chart.canvas.dataset["dotError"] = worst.toFixed(2);
    chart.canvas.dataset["plotLeft"] = String(chart.chartArea.left);
    chart.canvas.dataset["plotRight"] = String(chart.chartArea.right);
  },
};

export function mountSegmentChart(
  canvas: HTMLCanvasElement,
  model: ChartModel,
  efforts: Effort[],
): () => void {
  disposeSegmentChart();
  canvas.setAttribute("role", "img");
  canvas.setAttribute("aria-label", chartLabel(efforts));
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const tick = { color: MUTED, font: { family: FONT, size: 11 } };
  current = new Chart(canvas, {
    type: "scatter",
    data: {
      datasets: [
        {
          label: "Efforts",
          data: model.efforts,
          backgroundColor: EFFORT,
          borderWidth: 0,
          pointRadius: 4.5,
          pointHoverRadius: 6,
        },
        {
          label: "Slower efforts above the cap",
          data: model.capped,
          backgroundColor: EFFORT,
          borderWidth: 0,
          pointStyle: "triangle",
          pointRadius: 6,
          pointHoverRadius: 7,
          clip: false,
        },
        {
          label: "PR",
          data: [model.pr],
          backgroundColor: ORANGE,
          borderColor: "#FFFFFF",
          borderWidth: 3,
          pointRadius: 8,
          pointHoverRadius: 9,
          pointHoverBorderWidth: 3,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      // Only the vertical position animates: a dot can never move away from its date horizontally.
      animation: reduced ? false : { duration: 300 },
      animations: { x: { duration: 0 } },
      layout: { padding: { right: 12, top: 8 } },
      scales: {
        x: {
          type: "linear",
          min: model.xMin,
          max: model.xMax,
          border: { color: AXIS },
          grid: { display: false },
          afterBuildTicks(scale) {
            scale.ticks = visibleYears(model.years, scale.maxWidth || scale.chart.width).map(
              (y) => ({ value: Date.UTC(y, 0, 1), label: String(y) }),
            );
          },
          ticks: {
            ...tick,
            maxRotation: 0,
            autoSkip: true,
            callback: (v) => String(new Date(Number(v)).getUTCFullYear()),
          },
        },
        y: {
          type: "linear",
          reverse: true,
          min: model.yMin,
          max: model.yMax,
          border: { color: AXIS },
          grid: { color: GRID },
          ticks: {
            ...tick,
            stepSize: model.yStep,
            callback: (v) => formatDuration(Number(v)),
          },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          displayColors: false,
          callbacks: {
            title: (items) => (items[0] ? formatDate((items[0].parsed.x ?? 0) / 1000) : ""),
            label: (item) => {
              const p = item.raw as { y: number; ride: string; actual?: number };
              return `${formatDuration(p.actual ?? p.y)} · ${p.ride}`;
            },
          },
        },
      },
    },
    plugins: [prLabelPlugin(model), plotAreaPlugin],
  });
  const chart = current;
  void document.fonts?.ready?.then(() => {
    if (current !== chart) return;
    // update("none") writes positions straight onto the points but leaves a running animation alone,
    // which would then finish at targets from the layout before the font arrived.
    chart.stop();
    chart.update("none");
  });
  return disposeSegmentChart;
}
