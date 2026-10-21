import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { verify } from "../../api/learner";
import type { Verification } from "../../api/types";
import { ErrorLine, PageLoader } from "../../components/Feedback";
import { Icon } from "../../components/Icon";
import { date } from "../../lib/format";
import { pick, useLang } from "../../lib/lang";
import { useApi } from "../../lib/useApi";

/** Public check of a certificate: the QR code opens /verify/<number>?c=<printed code>. */
export function Verify() {
  const { t } = useTranslation();
  const number = useParams().number ?? "";
  const [search] = useSearchParams();
  const code = search.get("c") ?? "";
  const ready = number !== "" && code !== "";
  const { data, error, loading } = useApi<Verification | null>(
    () => (ready ? verify(number, code) : Promise.resolve(null)),
    [number, code],
  );

  if (!ready) {
    return (
      <div className="auth-box card card-pad">
        <h1>{t("verify.title")}</h1>
        <p className="muted">{t("verify.intro")}</p>
        <VerifyForm number={number} code={code} />
      </div>
    );
  }
  if (loading && !data) return <PageLoader />;
  if (error || !data) {
    return (
      <div className="auth-box card card-pad">
        <h1>{t("verify.title")}</h1>
        {error?.code === "certificate.not_found" ? (
          <div className="notice notice-danger" role="alert">
            {t("verify.not_found")}
          </div>
        ) : (
          <ErrorLine error={error} />
        )}
        <VerifyForm number={number} code={code} />
      </div>
    );
  }
  return <Verified v={data} />;
}

function VerifyForm({ number, code }: { number: string; code: string }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [n, setN] = useState(number);
  const [c, setC] = useState(code);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const target = n.trim().toUpperCase();
    if (target) navigate(`/verify/${encodeURIComponent(target)}?c=${encodeURIComponent(c.trim().toUpperCase())}`);
  };
  return (
    <form className="stack" onSubmit={submit}>
      <div className="field">
        <label htmlFor="cert-number">{t("certs.number")}</label>
        <input id="cert-number" className="input" required value={n} placeholder="YO-2026-000001"
          onChange={(e) => setN(e.target.value)} />
      </div>
      <div className="field">
        <label htmlFor="cert-code">{t("verify.code")}</label>
        <input id="cert-code" className="input" required value={c} autoComplete="off"
          onChange={(e) => setC(e.target.value)} />
        <span className="muted tiny">{t("verify.code_hint")}</span>
      </div>
      <button className="btn btn-primary btn-block">{t("verify.submit")}</button>
    </form>
  );
}

function Verified({ v }: { v: Verification }) {
  const { t } = useTranslation();
  const lang = useLang();
  const ok = v.status === "valid" && !v.recert_due_at;
  return (
    <article className="card card-pad-lg stack verify">
      <p className="caps">{t("verify.title")}</p>
      <div className={`verify-status verify-${v.status}`}>
        <Icon name={v.status === "valid" ? "check" : "alert"} size={28} />
        <div>
          <strong>{t(`verify.status_${v.status}`)}</strong>
          <span>
            {v.status === "valid" && v.recert_due_at
              ? t("verify.renew_by", { date: date(v.recert_due_at) })
              : t(`verify.hint_${v.status}`)}
          </span>
        </div>
      </div>
      <dl className="cert-facts">
        <div>
          <dt>{t("verify.holder")}</dt>
          <dd>{v.holder}</dd>
        </div>
        <div>
          <dt>{t("verify.kind")}</dt>
          <dd>{t(v.kind === "operator" ? "certs.kind_operator" : "certs.kind_module")}</dd>
        </div>
        <div>
          <dt>{t("certs.number")}</dt>
          <dd className="num">{v.number}</dd>
        </div>
        <div>
          <dt>{t("certs.issued")}</dt>
          <dd>{date(v.issued_at)}</dd>
        </div>
        {v.branch && (
          <div>
            <dt>{t("verify.branch")}</dt>
            <dd>{pick(v.branch, "name", lang)}</dd>
          </div>
        )}
        {v.region && (
          <div>
            <dt>{t("verify.region")}</dt>
            <dd>{pick(v.region, "name", lang)}</dd>
          </div>
        )}
        {v.superseded_at && (
          <div>
            <dt>{t("certs.superseded")}</dt>
            <dd>{date(v.superseded_at)}</dd>
          </div>
        )}
      </dl>
      <div className="stack-sm">
        <p className="caps">{t("verify.modules")}</p>
        <ul className="cert-modules">
          {v.modules.map((m) => (
            <li key={m.code}>
              <Icon name={ok ? "check" : "info"} size={16} />
              <span>
                {pick(m, "title", lang)}
                {m.release && <span className="muted"> · {t("certs.release")} {m.release}</span>}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </article>
  );
}
