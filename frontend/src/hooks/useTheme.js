import { useEffect, useState } from "react";

export function useTheme() {
  const [dark, setDark] = useState(() => {
    const stored = localStorage.getItem("editorial-theme");
    if (stored) return stored === "dark";
    return false;
  });

  useEffect(() => {
    const root = document.documentElement;
    if (dark) {
      root.classList.add("dark");
    } else {
      root.classList.remove("dark");
    }
    localStorage.setItem("editorial-theme", dark ? "dark" : "light");
  }, [dark]);

  return { dark, toggle: () => setDark((d) => !d) };
}
