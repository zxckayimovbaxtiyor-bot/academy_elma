import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, useNavigate, useSearchParams } from "react-router-dom";

import { auth } from "../../api/learner";
import type { AccessRole } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { ErrorLine } from "../../components/Feedback";
import { landing } from "../../lib/roles";

/** Only same-site paths after login (never an absolute URL from the query string). */
function safeNext(next: string | null, role: AccessRole): string {
  if (next && next.startsWith("/") && !next.startsWith("//") && next !== "/") return next;
  return landing(role);
}

export function Login() {
  const { t } = useTranslation();
  const { me, signedIn } = useAuth();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  if (me) return <Navigate to={me.must_change_password ? "/change-password" : safeNext(params.get("next"), me.access_role)} replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const user = await auth.login(username.trim(), password);
      signedIn(user);
      navigate(user.must_change_password ? "/change-password" : safeNext(params.get("next"), user.access_role), { replace: true });
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-box card card-pad">
      <h1>{t("login.title")}</h1>
      <p className="muted">{t("login.subtitle")}</p>
      <form className="stack" onSubmit={submit}>
        <div className="field">
          <label htmlFor="username">{t("login.employee_id")}</label>
          <input
            id="username"
            className="input"
            autoComplete="username"
            autoFocus
            required
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="XB-100231"
          />
        </div>
        <div className="field">
          <label htmlFor="password">{t("login.password")}</label>
          <input
            id="password"
            className="input"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        <ErrorLine error={error} />
        <button className="btn btn-primary btn-block" disabled={busy}>
          {t("login.submit")}
        </button>
      </form>
      <p className="muted small">{t("login.hint")}</p>
    </div>
  );
}
