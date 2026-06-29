import { Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "./api/auth";
import { ToastProvider } from "./components/Toast";
import ProtectedRoute from "./components/ProtectedRoute";
import LoginPage from "./pages/LoginPage";
import TeacherDashboard from "./pages/TeacherDashboard";
import AdminDashboard from "./pages/AdminDashboard";
import LeaderDashboard from "./pages/LeaderDashboard";
import MemberDashboard from "./pages/MemberDashboard";
import StudentProjectPortal from "./pages/StudentProjectPortal";
import EvaluationResultPage from "./pages/EvaluationResultPage";
import NotFoundPage from "./pages/NotFoundPage";

export default function App() {
  return (
    <AuthProvider>
      <ToastProvider>
        <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/teacher/*"
          element={
            <ProtectedRoute roles={["teacher", "admin"]}>
              <TeacherDashboard />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/*"
          element={
            <ProtectedRoute roles={["admin"]}>
              <AdminDashboard />
            </ProtectedRoute>
          }
        />
        <Route
          path="/leader"
          element={
            <ProtectedRoute roles={["group_leader"]}>
              <StudentProjectPortal role="group_leader" />
            </ProtectedRoute>
          }
        />
        <Route
          path="/leader/project/:projectId"
          element={
            <ProtectedRoute roles={["group_leader"]}>
              <LeaderDashboard />
            </ProtectedRoute>
          }
        />
        <Route
          path="/member"
          element={
            <ProtectedRoute roles={["group_member"]}>
              <StudentProjectPortal role="group_member" />
            </ProtectedRoute>
          }
        />
        <Route
          path="/member/project/:projectId"
          element={
            <ProtectedRoute roles={["group_member"]}>
              <MemberDashboard />
            </ProtectedRoute>
          }
        />
        <Route
          path="/evaluation/:submissionId"
          element={
            <ProtectedRoute>
              <EvaluationResultPage />
            </ProtectedRoute>
          }
        />
        <Route path="/" element={<RootRedirect />} />
        <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </ToastProvider>
    </AuthProvider>
  );
}

/** 根据角色自动跳转 */
function RootRedirect() {
  const stored = localStorage.getItem("user");
  if (stored) {
    const user = JSON.parse(stored);
    const map: Record<string, string> = {
      teacher: "/teacher",
      admin: "/admin",
      group_leader: "/leader",
      group_member: "/member",
    };
    return <Navigate to={map[user.role] || "/login"} replace />;
  }
  return <Navigate to="/login" replace />;
}
