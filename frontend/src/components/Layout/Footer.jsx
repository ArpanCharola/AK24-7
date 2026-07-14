import { Wordmark } from "../brand/Logo";

export default function Footer({ publicView = false }) {
  return (
    <footer className={`editorial-footer ${publicView ? "public-footer" : ""}`}>
      <div className="footer-inner">
        <div><Wordmark variant="ak-emblem" size={26} tagline={null} /><p>India's focused career discovery workspace.</p></div>
        <span className="footer-copy">© {new Date().getFullYear()} AK24/7 Jobs</span>
      </div>
    </footer>
  );
}
