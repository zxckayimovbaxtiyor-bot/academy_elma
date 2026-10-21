import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

export function NotFound() {
  const { t } = useTranslation();
  return (
    <div className="center-box">
      <h1>{t("notfound.title")}</h1>
      <p className="muted">{t("notfound.text")}</p>
      <Link className="btn btn-primary" to="/">
        {t("nav.home")}
      </Link>
    </div>
  );
}
