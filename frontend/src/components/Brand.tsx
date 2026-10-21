import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

/** Logo placeholder: the platform name (the bank's own logo is added on site). */
export function Brand({ to = "/", link = true }: { to?: string; link?: boolean }) {
  const { t } = useTranslation();
  const content = (
    <>
      <span className="brand-mark" aria-hidden="true">
        <svg viewBox="0 0 32 32" width="34" height="34">
          <rect width="32" height="32" rx="9" fill="currentColor" />
          <path d="M9 9l7 8 7-8M16 17v7" fill="none" stroke="#fff" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
      <span className="brand-name">{t("app.name")}</span>
    </>
  );
  if (!link) return <span className="brand">{content}</span>;
  return (
    <Link to={to} className="brand" aria-label={t("app.name")}>
      {content}
    </Link>
  );
}
