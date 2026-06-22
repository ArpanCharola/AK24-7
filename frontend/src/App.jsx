import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import AppLayout from "./components/Layout/AppLayout";
import { authApi } from "./services/api";
import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";
import Profile from "./pages/Profile";
import Settings from "./pages/Settings";
import Jobs from "./pages/Jobs";
import EmailAuto from "./pages/EmailAuto";
import Tracker from "./pages/Tracker";
import Admin from "./pages/Admin";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 2 * 60 * 1000 } },
});

function PrivateRoute({ children }) {
  return localStorage.getItem("token") ? (
    <AppLayout>{children}</AppLayout>
  ) : (
    <Navigate to="/login" replace />
  );
}

// "/" routes by role: the admin is a management-only account sent straight to
// /admin; every other user lands on the job-seeker dashboard.
function HomeRoute() {
  const { data: me, isLoading } = useQuery({
    queryKey: ["me"],
    queryFn: () => authApi.me().then((r) => r.data),
    enabled: !!localStorage.getItem("token"),
    staleTime: 5 * 60 * 1000,
  });
  if (isLoading) return null;
  if (me?.is_admin) return <Navigate to="/admin" replace />;
  return <Navigate to="/dashboard" replace />;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          {/* Root redirects by role. */}
          <Route path="/" element={<PrivateRoute><HomeRoute /></PrivateRoute>} />
          {/* Private app routes. */}
          <Route path="/dashboard" element={<PrivateRoute><Dashboard /></PrivateRoute>} />
          <Route path="/jobs" element={<PrivateRoute><Jobs /></PrivateRoute>} />
          <Route path="/email-auto" element={<PrivateRoute><EmailAuto /></PrivateRoute>} />
          <Route path="/tracker" element={<PrivateRoute><Tracker /></PrivateRoute>} />
          <Route path="/profile" element={<PrivateRoute><Profile /></PrivateRoute>} />
          <Route path="/settings" element={<PrivateRoute><Settings /></PrivateRoute>} />
          <Route path="/admin" element={<PrivateRoute><Admin /></PrivateRoute>} />
          {/* Back-compat redirects for old URLs. */}
          <Route path="/discovered-jobs" element={<Navigate to="/jobs" replace />} />
          {/* Resume-tailoring was removed; old links fall back to Jobs. */}
          <Route path="/tailor-resume" element={<Navigate to="/jobs" replace />} />
          <Route path="/tailored-resumes" element={<Navigate to="/jobs" replace />} />
          <Route path="/inbox" element={<Navigate to="/email-auto" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
