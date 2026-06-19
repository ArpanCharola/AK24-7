import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import AppLayout from "./components/Layout/AppLayout";
import { authApi } from "./services/api";
import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";
import Profile from "./pages/Profile";
import Settings from "./pages/Settings";
import DiscoveredJobs from "./pages/DiscoveredJobs";
import TailoredResumes from "./pages/TailoredResumes";
import EmailAuto from "./pages/EmailAuto";
import Tracker from "./pages/Tracker";
import Inbox from "./pages/Inbox";
import PublicJobs from "./pages/PublicJobs";
import Admin from "./pages/Admin";

const queryClient = new QueryClient();

function PrivateRoute({ children }) {
  return localStorage.getItem("token") ? (
    <AppLayout>{children}</AppLayout>
  ) : (
    <Navigate to="/login" replace />
  );
}

// "/" is the job-seeker Dashboard for normal users; the admin is a management-only
// account, sent straight to /admin so they never see the job-seeker UI.
function HomeRoute() {
  const { data: me, isLoading } = useQuery({
    queryKey: ["me"],
    queryFn: () => authApi.me().then((r) => r.data),
    enabled: !!localStorage.getItem("token"),
    staleTime: 5 * 60 * 1000,
  });
  if (isLoading) return null;
  if (me?.is_admin) return <Navigate to="/admin" replace />;
  return <Dashboard />;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          {/* Public — accessible without login. */}
          <Route path="/jobs" element={<PublicJobs />} />
          <Route path="/" element={<PrivateRoute><HomeRoute /></PrivateRoute>} />
          <Route path="/profile" element={<PrivateRoute><Profile /></PrivateRoute>} />
          <Route path="/settings" element={<PrivateRoute><Settings /></PrivateRoute>} />
          <Route path="/discovered-jobs" element={<PrivateRoute><DiscoveredJobs /></PrivateRoute>} />
          <Route path="/tailored-resumes" element={<PrivateRoute><TailoredResumes /></PrivateRoute>} />
          <Route path="/admin" element={<PrivateRoute><Admin /></PrivateRoute>} />
          <Route path="/email-auto" element={<PrivateRoute><EmailAuto /></PrivateRoute>} />
          <Route path="/tracker" element={<PrivateRoute><Tracker /></PrivateRoute>} />
          {/* Inbox kept routable (not in nav) until the unified Emails page lands. */}
          <Route path="/inbox" element={<PrivateRoute><Inbox /></PrivateRoute>} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}