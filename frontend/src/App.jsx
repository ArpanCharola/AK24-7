import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import AppLayout from "./components/Layout/AppLayout";
import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";
import Profile from "./pages/Profile";
import JobPreferences from "./pages/JobPreferences";
import DiscoveredJobs from "./pages/DiscoveredJobs";
import TailoredResumes from "./pages/TailoredResumes";
import EmailAuto from "./pages/EmailAuto";
import Applications from "./pages/Applications";
import Tracker from "./pages/Tracker";
import EmailHome from "./pages/EmailHome";
import Inbox from "./pages/Inbox";
import Labels from "./pages/Labels";
import TrackerList from "./pages/TrackerList";
import PublicJobs from "./pages/PublicJobs";
import Copilot from "./pages/Copilot";
import ConsentGate from "./components/ConsentGate";

const queryClient = new QueryClient();

function PrivateRoute({ children }) {
  return localStorage.getItem("token") ? (
    <AppLayout>{children}</AppLayout>
  ) : (
    <Navigate to="/login" replace />
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ConsentGate>
        <Routes>
          <Route path="/login" element={<Login />} />
          {/* Public — accessible without login. ConsentGate ignores tokenless users. */}
          <Route path="/jobs" element={<PublicJobs />} />
          <Route path="/" element={<PrivateRoute><Dashboard /></PrivateRoute>} />
          <Route path="/profile" element={<PrivateRoute><Profile /></PrivateRoute>} />
          <Route path="/job-preferences" element={<PrivateRoute><JobPreferences /></PrivateRoute>} />
          <Route path="/discovered-jobs" element={<PrivateRoute><DiscoveredJobs /></PrivateRoute>} />
          <Route path="/tailored-resumes" element={<PrivateRoute><TailoredResumes /></PrivateRoute>} />
          <Route path="/copilot" element={<PrivateRoute><Copilot /></PrivateRoute>} />
          <Route path="/email-auto" element={<PrivateRoute><EmailAuto /></PrivateRoute>} />
          <Route path="/applications" element={<PrivateRoute><Applications /></PrivateRoute>} />
          <Route path="/tracker" element={<PrivateRoute><Tracker /></PrivateRoute>} />
          <Route path="/email-home" element={<PrivateRoute><EmailHome /></PrivateRoute>} />
          <Route path="/inbox" element={<PrivateRoute><Inbox /></PrivateRoute>} />
          <Route path="/labels" element={<PrivateRoute><Labels /></PrivateRoute>} />
          <Route path="/tracker-list" element={<PrivateRoute><TrackerList /></PrivateRoute>} />
        </Routes>
        </ConsentGate>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
