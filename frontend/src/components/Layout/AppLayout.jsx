import { useState } from "react";
import Sidebar from "./Sidebar";

export default function AppLayout({ children }) {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="h-screen overflow-hidden bg-background">
      <div className="flex h-full gap-3 p-2 sm:p-3">
        <Sidebar mobileOpen={mobileOpen} onClose={() => setMobileOpen(false)} />
        <main className="flex-1 min-w-0 flex flex-col overflow-hidden">
          {/* Mobile top bar — hamburger + brand. Hidden on lg where the sidebar is static. */}
          <div className="lg:hidden flex items-center gap-3 mb-2">
            <button
              onClick={() => setMobileOpen(true)}
              aria-label="Open menu"
              className="flex-shrink-0 p-2 rounded-xl glass text-foreground active:scale-95 transition-transform"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg flex items-center justify-center bg-primary">
                <svg className="w-4 h-4 text-primary-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </div>
              <span className="text-[15px] font-semibold text-foreground tracking-tight">AK24/7Jobs</span>
            </div>
          </div>
          {/* Pages use h-full; this flex region gives them the space below the
              mobile top bar (and all of main on lg where the bar is hidden). */}
          <div className="flex-1 min-h-0 flex flex-col">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
