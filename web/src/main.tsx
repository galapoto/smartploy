// PORTED from komplyint/komplyint-website@76c00948638cd2db699f78c58d6885117f676014
// src/app/layout.tsx — pinned, local OFL-1.1 Fontsource packages (no CDN).
import "@fontsource/lato/latin-400.css";
import "@fontsource/lato/latin-ext-400.css";
import "@fontsource/lato/latin-700.css";
import "@fontsource/lato/latin-ext-700.css";
import "@fontsource/manrope/latin-400.css";
import "@fontsource/manrope/latin-ext-400.css";
import "@fontsource/manrope/latin-700.css";
import "@fontsource/manrope/latin-ext-700.css";
import "@fontsource/eb-garamond/latin-400.css";
import "@fontsource/eb-garamond/latin-ext-400.css";
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles.css";
import "./career-atlas.css";
import "./document-coach.css";
import "./document-comparison.css";
import "./finland-shell.css";
import "./sp125-workspace-theme.css";
import "./sp126-premium-dashboard.css";
import "./sp127-mobile-shell.css";
import "./sp128-mobile-workflow.css";
import "./sp-v4-monochrome.css";
import "./sp-v4-card-surfaces.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
