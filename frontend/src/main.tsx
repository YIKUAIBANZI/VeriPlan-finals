import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { AuthGate } from "./components/AuthGate";

// Development-only opt-in: ?fixtures=1 uses no backend and no external requests.
const fixtureApi = import.meta.env.DEV && new URLSearchParams(location.search).get("fixtures") === "1"
  ? (await import("./fixtures/mockApi")).createFixtureApi()
  : undefined;
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {fixtureApi ? <App api={fixtureApi} /> : <AuthGate />}
  </StrictMode>,
);
