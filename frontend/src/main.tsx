import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { PageErrorBoundary } from "@/components/layout/PageErrorBoundary";
import { reloadForNewBuild } from "@/lib/staleBuild";
import "./styles/index.css";

// Vite reports a page file of a previous build that no longer exists; reload
// once to get the new build instead of failing (see lib/staleBuild.ts).
window.addEventListener("vite:preloadError", (event) => {
  if (reloadForNewBuild()) event.preventDefault();
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <PageErrorBoundary fullPage>
      <App />
    </PageErrorBoundary>
  </StrictMode>,
);
