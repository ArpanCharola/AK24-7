import { Link, useNavigate } from "react-router-dom";

export default function Navbar() {
  const navigate = useNavigate();

  function logout() {
    localStorage.removeItem("token");
    navigate("/login");
  }

  return (
    <nav className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-white">
      <Link to="/" className="text-xl font-semibold text-indigo-600">
        AK24/7Jobs
      </Link>
      <div className="flex gap-4 items-center">
        <Link to="/" className="text-sm text-gray-600 hover:text-gray-900">
          Dashboard
        </Link>
        <Link to="/discovered-jobs" className="text-sm text-gray-600 hover:text-gray-900">
          Discovered Jobs
        </Link>
        <Link to="/job-preferences" className="text-sm text-gray-600 hover:text-gray-900">
          Job Preferences
        </Link>
        <Link to="/profile" className="text-sm text-gray-600 hover:text-gray-900">
          Profile
        </Link>
        <button
          onClick={logout}
          className="text-sm text-red-500 hover:text-red-700"
        >
          Logout
        </button>
      </div>
    </nav>
  );
}
