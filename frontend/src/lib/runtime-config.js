const explicitApiUrl = import.meta.env.VITE_API_URL?.trim();
const explicitWsUrl = import.meta.env.VITE_WS_URL?.trim();

function trimTrailingSlash(value) {
  return value.replace(/\/+$/, "");
}

export function apiBaseUrl() {
  if (explicitApiUrl) return trimTrailingSlash(explicitApiUrl);
  if (import.meta.env.DEV) return "http://localhost:8000/api";
  return "/api";
}

export function wsBaseUrl() {
  if (explicitWsUrl) return trimTrailingSlash(explicitWsUrl);
  if (import.meta.env.DEV) return "ws://localhost:8000/ws";
  if (typeof window !== "undefined") {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${window.location.host}/ws`;
  }
  return "/ws";
}
