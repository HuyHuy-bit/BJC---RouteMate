export type Theme = "light" | "dark";

// Must match the key read by the boot script in index.html, which
// applies the theme before first paint to avoid a flash of light.
const STORAGE_KEY = "xeghep_theme";

export function getTheme(): Theme {
  const attr = document.documentElement.getAttribute("data-theme");
  return attr === "dark" ? "dark" : "light";
}

export function setTheme(theme: Theme) {
  document.documentElement.setAttribute("data-theme", theme);
  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // Private browsing or a full quota — the theme still applies for
    // this session, it just won't be remembered. Not worth surfacing.
  }
}
