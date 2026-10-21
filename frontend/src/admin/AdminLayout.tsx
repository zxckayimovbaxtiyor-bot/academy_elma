import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";

import { content, questions } from "../api/admin";
import { useAuth } from "../auth/AuthContext";
import { Brand } from "../components/Brand";
import { ErrorWording } from "../components/Feedback";
import { Icon } from "../components/Icon";
import { LangSwitch } from "../layouts/LearnerLayout";
import { initials } from "../lib/format";
import { isAdmin } from "../lib/roles";
import { ToastProvider } from "./ui";

/** Draft questions waiting for review (the badge in the menu, mockups 6–11). */
const DraftsCtx = createContext<() => void>(() => undefined);
export const useRefreshDrafts = () => useContext(DraftsCtx);

export function AdminLayout() {
  const { t } = useTranslation();
  const { me, logout } = useAuth();
  const navigate = useNavigate();
  const [drafts, setDrafts] = useState<number | null>(null);
  const admin = isAdmin(me);

  const refreshDrafts = useCallback(() => {
    content
      .modules()
      .then((modules) => Promise.all(modules.filter((m) => m.type !== "faq").map((m) => questions.pool(m.id))))
      .then((pools) => setDrafts(pools.reduce((sum, p) => sum + p.drafts, 0)))
      .catch(() => setDrafts(null));
  }, []);
  useEffect(refreshDrafts, [refreshDrafts]);

  const items = [
    { to: "/admin/reports", icon: "chart", label: t("admin.nav.reports"), show: admin },
    { to: "/admin/content", icon: "content", label: t("admin.nav.content"), show: true },
    { to: "/admin/questions", icon: "question", label: t("admin.nav.questions"), show: true, badge: drafts },
    { to: "/admin/waves", icon: "wave", label: t("admin.nav.waves"), show: admin },
    { to: "/admin/users", icon: "users", label: t("admin.nav.users"), show: admin },
    { to: "/admin/releases", icon: "box", label: t("admin.nav.releases"), show: admin },
  ];
  if (!me) return null;
  return (
    <ErrorWording.Provider value="admin.errors">
      <ToastProvider>
        <DraftsCtx.Provider value={refreshDrafts}>
          <div className="a-shell">
            <aside className="a-side">
              <div className="a-brand">
                <Brand to={admin ? "/admin/reports" : "/admin/questions"} />
                <div className="a-brand-text">
                  <strong>{t("app.name")}</strong>
                  <span>{t(admin ? "admin.panel" : "admin.panel_methodologist")}</span>
                </div>
              </div>
              <nav className="a-nav" aria-label={t("nav.main")}>
                {items
                  .filter((i) => i.show)
                  .map((i) => (
                    <NavLink key={i.to} to={i.to}>
                      <Icon name={i.icon} />
                      <span className="grow">{i.label}</span>
                      {i.badge ? <span className="a-badge">{i.badge}</span> : null}
                    </NavLink>
                  ))}
              </nav>
              <div className="a-user">
                <div className="row">
                  <span className="avatar">{initials(me.full_name)}</span>
                  <div className="grow a-user-text">
                    <strong>{me.full_name}</strong>
                    <span>{t(`roles.${me.access_role}`)}</span>
                  </div>
                </div>
                <LangSwitch />
                <div className="a-user-links">
                  <Link to="/">
                    <Icon name="home" size={16} />
                    {t("admin.learner_view")}
                  </Link>
                  <Link to="/change-password">
                    <Icon name="key" size={16} />
                    {t("nav.change_password")}
                  </Link>
                  <button
                    onClick={async () => {
                      await logout();
                      navigate("/login", { replace: true });
                    }}
                  >
                    <Icon name="logout" size={16} />
                    {t("nav.logout")}
                  </button>
                </div>
              </div>
            </aside>
            <main className="a-main">
              <Outlet />
            </main>
          </div>
        </DraftsCtx.Provider>
      </ToastProvider>
    </ErrorWording.Provider>
  );
}
