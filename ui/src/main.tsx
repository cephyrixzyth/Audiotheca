import { StrictMode } from "react";
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

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <HashRouter>
      <ThemeProvider>
        <TooltipProvider>
          <App />
        </TooltipProvider>
      </ThemeProvider>
    </HashRouter>
  </StrictMode>,
);
