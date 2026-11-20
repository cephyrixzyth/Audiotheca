import { StrictMode, useEffect, useState } from "react";
import { getApiBase, isTauri } from "./platform";
import { LoadingStatus } from "./ui/LoadingStatus";
import { createRoot } from "react-dom/client";
import { HashRouter } from "react-router-dom";
// Self-hosted fonts (air-gap friendly — replaces the Google Fonts CDN link).
import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import App from "./App";
import { ThemeProvider } from "./contexts/ThemeContext";
import { TooltipProvider } from "./ui";
import { bootstrapTheme } from "./themes/themeEngine";
import "./index.css";

bootstrapTheme();

function DesktopStartup() {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let stopped = false;
    const abort = new AbortController();
    let timer = 0;
    const deadline = Date.now() + 30_000;
    async function connect() {
      try {
        const base = await getApiBase();
        const response = await fetch(`${base}/health`, { signal: abort.signal });
        if (!response.ok || !(await response.json()).engine_version) throw new Error("Service is starting");
        if (!stopped) setReady(true);
      } catch (err) {
        if (stopped) return;
        if (Date.now() < deadline) timer = window.setTimeout(connect, 450);
        else setError(`Could not start the local library service. ${String(err)}`);
      }
    }
    void connect();
    return () => { stopped = true; abort.abort(); window.clearTimeout(timer); };
  }, [attempt]);

  if (ready) return <App />;
  return <main className="desktop-startup">
    <h1>Audiotheca</h1>
    {error ? <><p role="alert">{error}</p><button onClick={() => { setError(""); setAttempt(n => n + 1); }}>Retry</button></> :
      <LoadingStatus>Opening your local workspace…</LoadingStatus>}
  </main>;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <HashRouter>
      <ThemeProvider>
        <TooltipProvider>
          {isTauri() ? <DesktopStartup /> : <App />}
        </TooltipProvider>
      </ThemeProvider>
    </HashRouter>
  </StrictMode>,
);
