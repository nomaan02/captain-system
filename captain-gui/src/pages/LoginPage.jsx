import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

const LoginPage = () => {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [apiKey, setApiKey] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await login(apiKey);
      navigate("/");
    } catch {
      setError("Invalid API key");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="h-screen bg-surface flex items-center justify-center">
      <div className="w-[340px] bg-surface-card border border-border-subtle p-6">
        <h1 className="text-lg font-mono text-white tracking-[2px] uppercase mb-1 text-center">
          Captain
        </h1>
        <p className="text-[10px] font-mono text-[#64748b] uppercase tracking-wider text-center mb-6">
          Trading System
        </p>

        <form onSubmit={handleSubmit}>
          <label className="block text-[10px] font-mono text-[#64748b] uppercase tracking-wider mb-1.5">
            API Key
          </label>
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="Enter API key"
            aria-describedby={error ? "login-error" : undefined}
            className="w-full bg-surface border border-border-subtle text-white font-mono text-xs px-3 py-2 mb-4 outline-none focus:border-captain-green"
          />

          {error && (
            <div id="login-error" role="alert" className="text-captain-red text-[10px] font-mono mb-3">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={submitting || !apiKey}
            className="w-full min-h-[44px] py-2 text-[10px] font-mono uppercase tracking-wider border border-solid cursor-pointer bg-[rgba(16,185,129,0.15)] border-[rgba(16,185,129,0.3)] text-[#10b981] hover:bg-[rgba(16,185,129,0.25)] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {submitting ? "Authenticating..." : "Login"}
          </button>
        </form>
      </div>
    </div>
  );
};

export default LoginPage;
