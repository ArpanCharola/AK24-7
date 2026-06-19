import { useState } from "react";
import Sidebar from "./Sidebar";
import AvatarMenu from "./AvatarMenu";
import AmbientBackground from "../AmbientBackground";
import { Wordmark } from "../brand/Logo";

export default function AppLayout({ children }) {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="relative h-screen overflow-hidden bg-background">
      <AmbientBackground />
      <div className="relative z-10 flex h-full gap-3 p-2 sm:p-3">
        <Sidebar mobileOpen={mobileOpen} onClose={() => setMobileOpen(false)} />
        <main className="flex-1 min-w-0 flex flex-col overflow-hidden">
          {/* Top bar — hamburger+brand (mobile) on the left, account avatar on the right (all sizes). */}
          <div className="flex items-center gap-3 mb-2">
            <button
              onClick={() => setMobileOpen(true)}
              aria-label="Open menu"
              className="lg:hidden flex-shrink-0 p-2 rounded-xl glass text-foreground active:scale-95 transition-transform"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
            <div className="lg:hidden"><Wordmark variant="ak-emblem" size={30} tagline={null} /></div>
            <div className="ml-auto"><AvatarMenu /></div>
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
