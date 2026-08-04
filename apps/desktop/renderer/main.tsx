import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/motion.css";
import "./styles.css";
import "./styles/views.css";

// Default dark before first paint of React
if (!document.documentElement.dataset.theme) {
  document.documentElement.dataset.theme = "dark";
}
// Traffic-light inset only on macOS
const mac =
  typeof navigator !== "undefined" &&
  /Mac|Macintosh/.test(navigator.platform || navigator.userAgent || "");
document.documentElement.style.setProperty(
  "--chrome-pad-left",
  mac ? "78px" : "16px"
);

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
