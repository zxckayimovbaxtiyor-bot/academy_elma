import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { auth } from "../../api/learner";
import { useAuth } from "../../auth/AuthContext";
import { ErrorLine } from "../../components/Feedback";
import { landing } from "../../lib/roles";

export function ChangePassword() {
  const { t } = useTranslation();
  const { me, refresh } = useAuth();
  const navigate = useNavigate();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [mismatch, setMismatch] = useState(false);
  const [busy, setBusy] = useState(false);
  const forced = Boolean(me?.must_change_password);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setMismatch(next !== again);
    if (next !== again) return;
    setBusy(true);
    setError(null);
    try {
      await auth.changePassword(current, next);
      await refresh();
      navigate(me ? landing(me.access_role) : "/", { replace: true });
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-box card card-pad">
      <h1>{t("password.title")}</h1>
      {forced && <div className="notice">{t("password.first_login")}</div>}
      <form className="stack" onSubmit={submit}>
        <div className="field">
          <label htmlFor="current">{forced ? t("password.temporary") : t("password.current")}</label>
          <input id="current" className="input" type="password" autoComplete="current-password" required
            value={current} onChange={(e) => setCurrent(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="new">{t("password.new")}</label>
          <input id="new" className="input" type="password" autoComplete="new-password" required minLength={8}
            value={next} onChange={(e) => setNext(e.target.value)} />
          <span className="muted tiny">{t("password.rule")}</span>
        </div>
        <div className="field">
          <label htmlFor="again">{t("password.confirm")}</label>
          <input id="again" className="input" type="password" autoComplete="new-password" required
            value={again} onChange={(e) => setAgain(e.target.value)} />
        </div>
        {mismatch && <div className="notice notice-danger">{t("password.mismatch")}</div>}
        <ErrorLine error={error} />
        <button className="btn btn-primary btn-block" disabled={busy}>
          {t("password.submit")}
        </button>
        {!forced && (
          <button type="button" className="btn btn-ghost" onClick={() => navigate(-1)}>
            {t("app.back")}
          </button>
        )}
      </form>
    </div>
  );
}
