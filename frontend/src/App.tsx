import { FormEvent, useEffect, useState } from "react";
import { api, LabSettings, ModelOption } from "./api/client";
import { AboutThisApp } from "./components/AboutThisApp";
import { LabPage } from "./pages/Lab";

function LoginScreen({ onLoggedIn }: { onLoggedIn: (username: string | null) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await api.login({ username, password });
      onLoggedIn(res.username);
      setPassword("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-screen">
      <div className="card login-card">
        <h2>Sign in</h2>
        <p className="muted small">Use the credentials configured on the backend.</p>
        <form onSubmit={onSubmit}>
          <label htmlFor="login-username">Username</label>
          <input id="login-username" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required />
          <label htmlFor="login-password">Password</label>
          <input id="login-password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          {error ? <p className="small bad-text">{error}</p> : null}
          <div style={{ marginTop: 12 }}>
            <button type="submit" disabled={loading}>{loading ? "Signing in..." : "Sign in"}</button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function App() {
  const [checkingSession, setCheckingSession] = useState(true);
  const [authEnabled, setAuthEnabled] = useState(false);
  const [authenticated, setAuthenticated] = useState(true);
  const [username, setUsername] = useState<string | null>(null);
  const [models, setModels] = useState<ModelOption[]>([]);
  const [settings, setSettings] = useState<LabSettings | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  async function loadLabData() {
    setLoadError(null);
    try {
      const [loadedSettings, loadedModels] = await Promise.all([api.getSettings(), api.listModels()]);
      setSettings(loadedSettings);
      setModels(loadedModels);
    } catch (err) {
      setSettings(null);
      setLoadError(err instanceof Error ? err.message : "Failed to load lab settings.");
    }
  }

  useEffect(() => {
    let mounted = true;
    async function boot() {
      try {
        const session = await api.getSession();
        if (!mounted) return;
        setAuthEnabled(session.enabled);
        setAuthenticated(session.authenticated);
        setUsername(session.username);
        if (!session.enabled || session.authenticated) {
          await loadLabData();
        }
      } catch {
        if (!mounted) return;
        setAuthEnabled(true);
        setAuthenticated(false);
      } finally {
        if (mounted) setCheckingSession(false);
      }
    }
    boot();
    const onUnauthorized = () => {
      setAuthenticated(false);
      setUsername(null);
      setAuthEnabled(true);
    };
    window.addEventListener("auth:unauthorized", onUnauthorized);
    return () => {
      mounted = false;
      window.removeEventListener("auth:unauthorized", onUnauthorized);
    };
  }, []);

  async function handleLogout() {
    try {
      await api.logout();
    } finally {
      setAuthenticated(false);
      setUsername(null);
    }
  }

  if (checkingSession) {
    return (
      <div className="login-screen">
        <div className="card login-card"><p className="muted">Checking session...</p></div>
      </div>
    );
  }

  if (authEnabled && !authenticated) {
    return <LoginScreen onLoggedIn={(name) => {
      setAuthenticated(true);
      setUsername(name);
      void loadLabData();
    }} />;
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <h1 className="brand">PDP Testing Lab</h1>
        <p className="muted small">{username ? `Signed in as ${username}` : "Internal prompt lab"}</p>
        <AboutThisApp />
        {authEnabled ? (
          <div className="sidebar-footer">
            <button className="secondary" onClick={handleLogout}>Log out</button>
          </div>
        ) : null}
      </aside>
      <main className="main">
        {loadError ? (
          <div className="card">
            <p className="bad-text">{loadError}</p>
            <p className="muted small">
              If you just signed in on production, log out and sign in again so the session cookie is refreshed.
            </p>
            <button type="button" className="secondary" style={{ marginTop: 12 }} onClick={() => void loadLabData()}>
              Retry
            </button>
          </div>
        ) : settings ? (
          <LabPage
            initialSettings={settings}
            models={models}
            onSettingsChange={setSettings}
          />
        ) : (
          <p className="muted">Loading lab settings...</p>
        )}
      </main>
    </div>
  );
}
