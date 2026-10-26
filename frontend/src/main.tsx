import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/app.css";
import "./i18n";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import { App } from "./App";
import { AuthProvider } from "./auth/AuthContext";
import { AppBoundary } from "./components/AppBoundary";
import { reserveChunkReload } from "./lib/chunkRecovery";

window.addEventListener("vite:preloadError", (event) => {
  try {
    if (!reserveChunkReload(window.sessionStorage)) return;
    event.preventDefault();
    window.location.reload();
  } catch {
    // The boundary still offers an explicit retry if browser storage is blocked.
  }
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AppBoundary>
      <BrowserRouter>
        <AuthProvider>
          <App />
        </AuthProvider>
      </BrowserRouter>
    </AppBoundary>
  </StrictMode>,
);
