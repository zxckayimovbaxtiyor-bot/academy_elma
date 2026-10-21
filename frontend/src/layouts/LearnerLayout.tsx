import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";

import type { Lang } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { Brand } from "../components/Brand";
import { initials } from "../lib/format";
import { name, useLang } from "../lib/lang";
import { canEditContent } from "../lib/roles";

export function LangSwitch() {
  const { setLanguage } = useAuth();
  const lang = useLang();
  const { t } = useTranslation();
  return (
    <div className="lang-switch" role="group" aria-label={t("nav.language")}>
      {(["uz", "ru"] as Lang[]).map((l) => (
        <button key={l} className={l === lang ? "on" : ""} aria-pressed={l === lang} onClick={() => setLanguage(l)}>
          {l.toUpperCase()}
        </button>
      ))}
    </div>
  );
}

function UserMenu() {
  const { me, logout } = useAuth();
  const { t } = useTranslation();
  const lang = useLang();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);
  if (!me) return null;
  const where = [name(me.branch, lang), name(me.job_role, lang)].filter(Boolean).join(" · ");
  return (
    <div className="user-menu" ref={box}>
      <button className="user-chip" aria-expanded={open} aria-label={me.full_name} onClick={() => setOpen(!open)}>
        <span className="avatar">{initials(me.full_name)}</span>
        <span className="user-text">
          <strong>{me.full_name}</strong>
          <span>{where || me.employee_id}</span>
        </span>
      </button>
      {open && (
        <div className="menu" role="menu">
          <div className="menu-head">
            <strong>{me.full_name}</strong>
            <span>{[me.employee_id, where].filter(Boolean).join(" · ")}</span>
          </div>
          <Link role="menuitem" to="/change-password" onClick={() => setOpen(false)}>
            {t("nav.change_password")}
          </Link>
          <button
            role="menuitem"
            onClick={async () => {
              await logout();
              navigate("/login", { replace: true });
            }}
          >
            {t("nav.logout")}
          </button>
        </div>
      )}
    </div>
  );
}

export function LearnerLayout() {
  const { t } = useTranslation();
  const { me } = useAuth();
  const items = [
    { to: "/", label: t("nav.home"), end: true },
    { to: "/courses", label: t("nav.courses") },
    { to: "/certificates", label: t("nav.certificates") },
    { to: "/faq", label: t("nav.faq") },
  ];
  if (me?.access_role === "branch_head") items.push({ to: "/reports", label: t("nav.reports") });
  if (canEditContent(me)) items.push({ to: "/admin", label: t("nav.admin") });
  return (
    <>
      <header className="topbar">
        <div className="container topbar-inner">
          <Brand />
          <nav className="nav" aria-label={t("nav.main")}>
            {items.map((item) => (
              <NavLink key={item.to} to={item.to} end={item.end}>
                {item.label}
              </NavLink>
            ))}
          </nav>
          <div className="row">
            <LangSwitch />
            <UserMenu />
          </div>
        </div>
      </header>
      <main className="container page">
        <Outlet />
      </main>
    </>
  );
}

/** Login, password change and the public verification page. */
export function PublicLayout() {
  return (
    <>
      <header className="topbar">
        <div className="container topbar-inner">
          <Brand />
          <LangSwitch />
        </div>
      </header>
      <main className="container page">
        <Outlet />
      </main>
    </>
  );
}
