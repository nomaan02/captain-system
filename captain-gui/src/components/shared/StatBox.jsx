const StatBox = ({ label, value, color }) => {
  return (
    <div className="bg-surface-card border border-border-accent flex flex-col py-2 px-3 min-h-[55px]">
      <div className="text-[10px] text-[rgba(226,232,240,0.5)] font-mono uppercase tracking-wider">
        {label}
      </div>
      <div className={`text-lg font-mono leading-tight mt-1 ${color || "text-white"}`}>
        {value ?? "\u2014"}
      </div>
    </div>
  );
};

export default StatBox;
