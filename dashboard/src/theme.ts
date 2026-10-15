import { useEffect, useState } from "react";

// Validated categorical order (blue, orange, aqua, yellow, magenta, green), stepped per mode.
const LIGHT = {
  series: ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"],
  pos: "#2a78d6",
  neg: "#e34948",
  neutral: "#c3c2b7",
  grid: "#e1e0d9",
  axis: "#c3c2b7",
  muted: "#898781",
  surface: "#fcfcfb",
  band: "rgba(42,120,214,0.12)",
};
const DARK = {
  series: ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300"],
  pos: "#3987e5",
  neg: "#e66767",
  neutral: "#383835",
  grid: "#2c2c2a",
  axis: "#383835",
  muted: "#898781",
  surface: "#1a1a19",
  band: "rgba(57,135,229,0.18)",
};
export type Palette = typeof LIGHT;
export type ThemeChoice = "system" | "light" | "dark";

function resolve(choice: ThemeChoice): "light" | "dark" {
  if (choice !== "system") return choice;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function useTheme() {
  const [choice, setChoice] = useState<ThemeChoice>(() => {
    try {
      return (localStorage.getItem("theme") as ThemeChoice) || "system";
    } catch {
      return "system";
    }
  });
  const [mode, setMode] = useState<"light" | "dark">(() => resolve(choice));

  useEffect(() => {
    const root = document.documentElement;
    if (choice === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", choice);
    try {
      localStorage.setItem("theme", choice);
    } catch {
      /* storage unavailable */
    }
    setMode(resolve(choice));
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => setMode(resolve(choice));
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [choice]);

  const palette: Palette = mode === "dark" ? DARK : LIGHT;
  return { choice, setChoice, mode, palette };
}
