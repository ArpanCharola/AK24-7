import TopNav from "./TopNav";
import Footer from "./Footer";
import ApplyPrompt from "../ApplyPrompt";

export default function AppLayout({ children }) {
  return (
    <div className="app-shell">
      <TopNav />
      <main className="app-main">{children}</main>
      <Footer />
      <ApplyPrompt />
    </div>
  );
}
