"use client";

import { useEffect, useRef } from "react";

export function TradingViewChart({ symbol }: { symbol: string }) {
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = host.current;
    if (!node) {
      return;
    }
    node.innerHTML = "";
    const container = document.createElement("div");
    container.className = "tradingview-widget-container";
    container.style.height = "100%";
    container.style.width = "100%";
    const widget = document.createElement("div");
    widget.className = "tradingview-widget-container__widget";
    widget.style.height = "100%";
    widget.style.width = "100%";
    container.appendChild(widget);
    const script = document.createElement("script");
    script.src = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
    script.async = true;
    script.type = "text/javascript";
    script.text = JSON.stringify({
      autosize: true,
      symbol,
      interval: "D",
      timezone: "America/New_York",
      theme: "dark",
      style: "1",
      locale: "en",
      backgroundColor: "#070707",
      gridColor: "rgba(34, 34, 34, 0.6)",
      hide_top_toolbar: false,
      allow_symbol_change: false,
      calendar: false,
      support_host: "https://www.tradingview.com",
    });
    container.appendChild(script);
    node.appendChild(container);
    return () => {
      node.innerHTML = "";
    };
  }, [symbol]);

  return <div ref={host} className="h-[420px] w-full overflow-hidden rounded border border-line bg-panel" />;
}
