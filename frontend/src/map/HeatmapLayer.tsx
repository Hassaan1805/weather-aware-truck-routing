import L from "leaflet";
import { useEffect, useRef } from "react";
import { useMap } from "react-leaflet";
import { heatColor } from "../lib/risk";
import type { HeatMetric, Heatmap } from "../types";

interface Frame {
  heatmap: Heatmap | null;
  metric: HeatMetric;
  hour: number;
}

/**
 * Canvas layer that paints one forecast hour of the corridor grid.
 *
 * Every frame is already in memory, so changing the hour is just a repaint of a
 * few hundred rectangles. CSS blur turns the grid into a smooth heat surface.
 */
class GridHeatLayer extends L.Layer {
  private canvas = L.DomUtil.create("canvas", "heat-canvas") as HTMLCanvasElement;
  private frame: Frame = { heatmap: null, metric: "risk", hour: 0 };
  private frameRequest = 0;

  onAdd(map: L.Map): this {
    const pane = map.getPane("heat") ?? map.createPane("heat");
    pane.style.zIndex = "350"; // above tiles, below route lines
    pane.style.pointerEvents = "none";
    pane.appendChild(this.canvas);
    map.on("moveend zoomend resize viewreset", this.reset, this);
    map.on("zoomstart", this.hide, this);
    this.reset();
    return this;
  }

  onRemove(map: L.Map): this {
    cancelAnimationFrame(this.frameRequest);
    this.canvas.remove();
    map.off("moveend zoomend resize viewreset", this.reset, this);
    map.off("zoomstart", this.hide, this);
    return this;
  }

  setFrame(frame: Frame) {
    this.frame = frame;
    this.scheduleDraw();
  }

  private hide() {
    this.canvas.style.opacity = "0";
  }

  private reset() {
    const map = this._map;
    if (!map) return;
    const size = map.getSize();
    const ratio = window.devicePixelRatio || 1;
    L.DomUtil.setPosition(this.canvas, map.containerPointToLayerPoint([0, 0]));
    this.canvas.width = size.x * ratio;
    this.canvas.height = size.y * ratio;
    this.canvas.style.width = `${size.x}px`;
    this.canvas.style.height = `${size.y}px`;
    this.draw();
  }

  private scheduleDraw() {
    cancelAnimationFrame(this.frameRequest);
    this.frameRequest = requestAnimationFrame(() => this.draw());
  }

  private draw() {
    const map = this._map;
    const ctx = this.canvas.getContext("2d");
    if (!map || !ctx) return;
    const ratio = window.devicePixelRatio || 1;
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

    const { heatmap, metric, hour } = this.frame;
    const values = heatmap?.frames[metric]?.[hour];
    if (!heatmap || !values) return;

    const [dLat, dLon] = heatmap.cell_size;
    let cellPx = 0;
    heatmap.cells.forEach(([lat, lon], i) => {
      const color = heatColor(metric, values[i]);
      if (!color) return;
      const nw = map.latLngToContainerPoint([lat + dLat / 2, lon - dLon / 2]);
      const se = map.latLngToContainerPoint([lat - dLat / 2, lon + dLon / 2]);
      cellPx = se.x - nw.x;
      ctx.fillStyle = `rgba(${color[0]},${color[1]},${color[2]},${color[3]})`;
      // +1px overlap avoids hairline seams between neighbouring cells.
      ctx.fillRect(nw.x, nw.y, se.x - nw.x + 1, se.y - nw.y + 1);
    });

    const blur = Math.max(2, Math.min(24, cellPx * 0.45));
    this.canvas.style.filter = `blur(${blur.toFixed(1)}px)`;
    this.canvas.style.opacity = "1";
  }
}

export default function HeatmapLayer({ heatmap, metric, hour, visible }: Frame & { visible: boolean }) {
  const map = useMap();
  const layer = useRef<GridHeatLayer | null>(null);

  useEffect(() => {
    const l = new GridHeatLayer();
    l.addTo(map);
    layer.current = l;
    return () => {
      l.remove();
      layer.current = null;
    };
  }, [map]);

  useEffect(() => {
    layer.current?.setFrame({ heatmap: visible ? heatmap : null, metric, hour });
  }, [heatmap, metric, hour, visible]);

  return null;
}
