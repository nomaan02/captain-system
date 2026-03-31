// DEAD CODE: USE_CUSTOM_CHART = false means this component never renders.
// Safe to delete if custom chart feature is permanently abandoned.
import useChartStore from "../../stores/chartStore";

const OVERLAYS = [
  { key: "or", label: "OR" },
  { key: "entry", label: "Entry" },
  { key: "sl", label: "SL" },
  { key: "tp", label: "TP" },
  { key: "vwap", label: "VWAP" },
];

const ChartOverlayToggles = () => {
  const overlays = useChartStore((s) => s.overlays);
  const toggleOverlay = useChartStore((s) => s.toggleOverlay);

  return (
    <div className="flex items-center gap-1">
      {OVERLAYS.map(({ key, label }) => (
        <button
          key={key}
          onClick={() => toggleOverlay(key)}
          className={`px-1.5 py-0.5 text-[8px] font-mono leading-[12px] cursor-pointer border border-solid ${
            overlays[key]
              ? "bg-[rgba(6,182,212,0.15)] border-[rgba(6,182,212,0.4)] text-[#06b6d4]"
              : "bg-transparent border-[#1e293b] text-[#64748b] hover:bg-[rgba(100,116,139,0.1)]"
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  );
};

export default ChartOverlayToggles;
