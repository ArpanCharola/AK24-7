import { Link } from "react-router-dom";
import { Wordmark } from "../brand/Logo";

export default function Footer({ publicView = false }) {
  return (
    <footer className={`editorial-footer ${publicView ? "public-footer" : ""}`}>
      <div className="footer-inner">
        <div><Wordmark variant="ak" size={26} tagline={null} /><p>India's focused career discovery workspace.</p></div>
        {!publicView && <div className="footer-links"><Link to="/dashboard">Dashboard</Link><Link to="/jobs">Jobs</Link><Link to="/profile">Profile</Link></div>}
        <span className="footer-copy">© {new Date().getFullYear()} AK24/7 Jobs</span>
      </div>
    </footer>
  );
}
