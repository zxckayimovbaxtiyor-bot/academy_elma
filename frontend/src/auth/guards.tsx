import type { ReactNode } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";

import type { AccessRole } from "../api/types";

import { PageLoader } from "../components/Feedback";
import { useAuth } from "./AuthContext";

/** Signed in, and the one-time password already replaced. */
export function RequireAuth() {
  const { me, ready } = useAuth();
  const location = useLocation();
  if (!ready) return <PageLoader />;
  if (!me) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  if (me.must_change_password && location.pathname !== "/change-password") {
    return <Navigate to="/change-password" replace />;
  }
  return <Outlet />;
}

/** Pages for some roles only; anyone else is sent to their own start page. */
export function RequireRole({ roles, children, fallback = "/" }: { roles: AccessRole[]; children: ReactNode; fallback?: string }) {
  const { me } = useAuth();
  if (!me || !roles.includes(me.access_role)) return <Navigate to={fallback} replace />;
  return <>{children}</>;
}
