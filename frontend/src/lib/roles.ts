import type { AccessRole, Me } from "../api/types";

export const isAdmin = (me: Me | null) => me?.access_role === "admin";
export const canEditContent = (me: Me | null) => me?.access_role === "admin" || me?.access_role === "methodologist";
export const canSeeReports = (me: Me | null) => me?.access_role === "admin" || me?.access_role === "branch_head";

/** Where a role lands after signing in (an explicit ?next= wins). */
export function landing(role: AccessRole): string {
  if (role === "admin") return "/admin/reports";
  if (role === "methodologist") return "/admin/questions";
  return "/";
}
