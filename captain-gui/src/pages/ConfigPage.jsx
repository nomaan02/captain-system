const ConfigPage = () => {
  return (
    <div className="h-full bg-surface p-4 overflow-y-auto">
      <h1 className="text-lg font-mono text-white tracking-[2px] uppercase mb-6">
        Configuration
      </h1>
      <div className="bg-surface-card border border-border-subtle p-6 font-mono text-xs text-[#64748b]">
        <p className="mb-2">Strategy parameters, account configuration, and system settings will be available here.</p>
        <p>Pending backend endpoint integration.</p>
      </div>
    </div>
  );
};

export default ConfigPage;
