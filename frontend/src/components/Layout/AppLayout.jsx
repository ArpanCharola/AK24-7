import { useState } from "react";
import { Menu } from "lucide-react";
import Sidebar from "./Sidebar";
import AvatarMenu from "./AvatarMenu";
import AmbientBackground from "../AmbientBackground";
import ApplyPrompt from "../ApplyPrompt";

export default function AppLayout({ children }) {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="relative flex h-screen overflow-hidden bg-background">
      <AmbientBackground />

      {/* Sidebar — flush, full-height column on the left (drawer on mobile). */}
      <Sidebar mobileOpen={mobileOpen} onClose={() => setMobileOpen(false)} />

      {/* Main column */}
      <div className="relative z-10 flex flex-col flex-1 min-w-0 overflow-hidden">
        {/* Topbar — flush to the top, same height as the sidebar brand band. */}
        <header className="h-14 px-4 flex items-center gap-3 border-b border-border bg-background/70 backdrop-blur-sm shrink-0">
          <button
            onClick={() => setMobileOpen(true)}
            aria-label="Open menu"
            className="lg:hidden p-2 -ml-2 rounded-xl text-muted-foreground hover:bg-muted active:scale-95 transition-all"
          >
            <Menu size={20} strokeWidth={1.75} />
          </button>
          <div className="ml-auto">
            <AvatarMenu />
          </div>
        </header>

        {/* Page content — pages own their padding (some are full-bleed). */}
        <div className="flex-1 min-h-0 flex flex-col overflow-y-auto">
          {children}
        </div>
      </div>

      {/* "Did you apply?" prompt after the Tailor & Apply flow. */}
      <ApplyPrompt />
    </div>
  );
}
