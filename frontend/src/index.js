import React from "react";
import ReactDOM from "react-dom/client";
import "@/index.css";
import App from "@/App";

// Sentry — only initialises when REACT_APP_SENTRY_DSN is set
const SENTRY_DSN = process.env.REACT_APP_SENTRY_DSN;
if (SENTRY_DSN) {
  import("@sentry/react").then((Sentry) => {
    Sentry.init({
      dsn: SENTRY_DSN,
      tracesSampleRate: 0.1,
      environment: process.env.NODE_ENV,
      release: process.env.REACT_APP_VERSION || "1.0.0",
    });
    // Expose for ErrorBoundary to use
    window.__SENTRY_SDK__ = Sentry;
  });
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
