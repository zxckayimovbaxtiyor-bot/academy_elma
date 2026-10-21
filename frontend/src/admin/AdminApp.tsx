import "../styles/admin.css";

import { Navigate, Route, Routes } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import { RequireRole } from "../auth/guards";
import { NotFound } from "../pages/learner/NotFound";
import { AdminLayout } from "./AdminLayout";
import { Content } from "./pages/Content";
import { LessonAdminPage } from "./pages/LessonAdmin";
import { Questions } from "./pages/Questions";
import { Releases } from "./pages/Releases";
import { Users } from "./pages/Users";
import { Waves } from "./pages/Waves";
import { ReportUser } from "./reports/ReportUser";
import { Reports } from "./reports/Reports";

/** Everything under /admin (loaded on demand: learners never download it). */
export default function AdminApp() {
  const { me } = useAuth();
  // A methodologist who opens an admin-only address lands on their own start page.
  const admin = (el: JSX.Element) => (
    <RequireRole roles={["admin"]} fallback="/admin">
      {el}
    </RequireRole>
  );
  return (
    <Routes>
      <Route element={<AdminLayout />}>
        <Route index element={<Navigate to={me?.access_role === "admin" ? "reports" : "questions"} replace />} />
        <Route path="reports" element={admin(<Reports />)} />
        <Route path="reports/users/:userId" element={admin(<ReportUser />)} />
        <Route path="content" element={<Content />} />
        <Route path="content/modules/:moduleId" element={<Content />} />
        <Route path="content/lessons/:lessonId" element={<LessonAdminPage />} />
        <Route path="questions" element={<Questions />} />
        <Route path="questions/:moduleId" element={<Questions />} />
        <Route path="waves" element={admin(<Waves />)} />
        <Route path="waves/:waveId" element={admin(<Waves />)} />
        <Route path="users" element={admin(<Users />)} />
        <Route path="users/:userId" element={admin(<Users />)} />
        <Route path="releases" element={admin(<Releases />)} />
        <Route path="releases/:releaseId" element={admin(<Releases />)} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
