import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router-dom";

import { RequireAuth, RequireRole } from "./auth/guards";
import { PageLoader } from "./components/Feedback";
import { LearnerLayout, PublicLayout } from "./layouts/LearnerLayout";
import { Certificates } from "./pages/learner/Certificates";
import { ChangePassword } from "./pages/learner/ChangePassword";
import { Courses } from "./pages/learner/Courses";
import { Faq } from "./pages/learner/Faq";
import { Home } from "./pages/learner/Home";
import { Login } from "./pages/learner/Login";
import { ModulePage } from "./pages/learner/Module";
import { NotFound } from "./pages/learner/NotFound";
import { TestIntro } from "./pages/learner/TestIntro";
import { TestResult } from "./pages/learner/TestResult";
import { TestTake } from "./pages/learner/TestTake";
import { Verify } from "./pages/learner/Verify";

// The player pulls in hls.js; load it only when a lesson is opened (slow branch links).
const Lesson = lazy(() => import("./pages/learner/Lesson"));
// Staff screens are a separate download; learners never fetch them.
const AdminApp = lazy(() => import("./admin/AdminApp"));
const BranchReport = lazy(() => import("./admin/reports/BranchReport"));
const BranchReportUser = lazy(() => import("./admin/reports/BranchReportUser"));

export function App() {
  return (
    <Suspense fallback={<PageLoader />}>
      <Routes>
        <Route element={<PublicLayout />}>
          <Route path="/login" element={<Login />} />
          <Route path="/verify" element={<Verify />} />
          <Route path="/verify/:number" element={<Verify />} />
        </Route>
        <Route element={<RequireAuth />}>
          <Route element={<PublicLayout />}>
            <Route path="/change-password" element={<ChangePassword />} />
          </Route>
          <Route path="/attempts/:attemptId" element={<TestTake />} />
          <Route
            path="/admin/*"
            element={
              <RequireRole roles={["admin", "methodologist"]}>
                <AdminApp />
              </RequireRole>
            }
          />
          <Route element={<LearnerLayout />}>
            <Route index element={<Home />} />
            <Route path="/courses" element={<Courses />} />
            <Route path="/courses/:moduleId" element={<ModulePage />} />
            <Route path="/courses/:moduleId/lessons/:lessonId" element={<Lesson />} />
            <Route path="/courses/:moduleId/test" element={<TestIntro />} />
            <Route path="/attempts/:attemptId/result" element={<TestResult />} />
            <Route path="/certificates" element={<Certificates />} />
            <Route path="/faq" element={<Faq />} />
            <Route path="/faq/:lessonId" element={<Lesson faq />} />
            <Route
              path="/reports"
              element={
                <RequireRole roles={["branch_head"]}>
                  <BranchReport />
                </RequireRole>
              }
            />
            <Route
              path="/reports/users/:userId"
              element={
                <RequireRole roles={["branch_head"]}>
                  <BranchReportUser />
                </RequireRole>
              }
            />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Route>
      </Routes>
    </Suspense>
  );
}
