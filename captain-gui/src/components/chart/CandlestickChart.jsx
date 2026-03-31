// DEAD CODE: USE_CUSTOM_CHART = false means this component never renders.
// Safe to delete if custom chart feature is permanently abandoned.
import { useEffect, useRef } from "react";
import { createChart, ColorType, CandlestickSeries } from "lightweight-charts";
import useChartStore from "../../stores/chartStore";
import useDashboardStore from "../../stores/dashboardStore";

const CandlestickChart = () => {
  const containerRef = useRef(null);
  const chartRef = useRef(null);
  const seriesRef = useRef(null);
  const priceLinesRef = useRef([]);

  const bars = useChartStore((s) => s.bars);
  const overlays = useChartStore((s) => s.overlays);
  const openPositions = useDashboardStore((s) => s.openPositions);
  const orStatus = useDashboardStore((s) => s.orStatus);

  // Create chart on mount
  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#0a0f0d" },
        textColor: "#64748b",
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 10,
      },
      grid: {
        vertLines: { color: "rgba(30, 41, 59, 0.5)" },
        horzLines: { color: "rgba(30, 41, 59, 0.5)" },
      },
      crosshair: {
        vertLine: { color: "rgba(100, 116, 139, 0.4)", width: 1, style: 3 },
        horzLine: { color: "rgba(100, 116, 139, 0.4)", width: 1, style: 3 },
      },
      rightPriceScale: {
        borderColor: "#1e293b",
        textColor: "#94a3b8",
      },
      timeScale: {
        borderColor: "#1e293b",
        timeVisible: true,
        secondsVisible: false,
      },
      handleScroll: true,
      handleScale: true,
    });

    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#10b981",
      downColor: "#ef4444",
      borderUpColor: "#10b981",
      borderDownColor: "#ef4444",
      wickUpColor: "#10b981",
      wickDownColor: "#ef4444",
    });

    chartRef.current = chart;
    seriesRef.current = series;

    // Handle resize
    const handleResize = () => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight,
        });
      }
    };

    const observer = new ResizeObserver(handleResize);
    observer.observe(containerRef.current);
    handleResize();

    return () => {
      observer.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  // Update bars data — only fitContent on first load, not after user has scrolled
  const hasUserScrolled = useRef(false);
  useEffect(() => {
    if (!chartRef.current) return;
    const ts = chartRef.current.timeScale();
    const onVisibleChange = () => { hasUserScrolled.current = true; };
    ts.subscribeVisibleLogicalRangeChange(onVisibleChange);
    return () => ts.unsubscribeVisibleLogicalRangeChange(onVisibleChange);
  }, []);

  useEffect(() => {
    if (!seriesRef.current || bars.length === 0) return;
    seriesRef.current.setData(bars);
    if (!hasUserScrolled.current) {
      chartRef.current?.timeScale().fitContent();
    }
  }, [bars]);

  // Update price lines (entry, SL, TP, OR)
  useEffect(() => {
    if (!seriesRef.current) return;

    // Remove old price lines
    priceLinesRef.current.forEach((line) => {
      try {
        seriesRef.current.removePriceLine(line);
      } catch {}
    });
    priceLinesRef.current = [];

    const pos = openPositions?.[0];

    if (pos && overlays.entry && pos.entry_price) {
      priceLinesRef.current.push(
        seriesRef.current.createPriceLine({
          price: pos.entry_price,
          color: "#3b82f6",
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: true,
          title: "Entry",
        })
      );
    }

    if (pos && overlays.sl && pos.sl_level) {
      priceLinesRef.current.push(
        seriesRef.current.createPriceLine({
          price: pos.sl_level,
          color: "#ef4444",
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: true,
          title: "SL",
        })
      );
    }

    if (pos && overlays.tp && pos.tp_level) {
      priceLinesRef.current.push(
        seriesRef.current.createPriceLine({
          price: pos.tp_level,
          color: "#10b981",
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: true,
          title: "TP",
        })
      );
    }

    if (overlays.or && orStatus) {
      if (orStatus.or_high) {
        priceLinesRef.current.push(
          seriesRef.current.createPriceLine({
            price: orStatus.or_high,
            color: "#06b6d4",
            lineWidth: 1,
            lineStyle: 0,
            axisLabelVisible: true,
            title: "OR\u2191",
          })
        );
      }
      if (orStatus.or_low) {
        priceLinesRef.current.push(
          seriesRef.current.createPriceLine({
            price: orStatus.or_low,
            color: "#06b6d4",
            lineWidth: 1,
            lineStyle: 0,
            axisLabelVisible: true,
            title: "OR\u2193",
          })
        );
      }
    }
  }, [openPositions, orStatus, overlays]);

  return <div ref={containerRef} className="w-full h-full min-h-[200px]" />;
};

export default CandlestickChart;
