import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

export interface Crumb {
  label: string;
  to?: string;
}

export function Breadcrumbs({ items }: { items: Crumb[] }) {
  const { t } = useTranslation();
  return (
    <nav className="crumbs" aria-label={t("nav.breadcrumbs")}>
      {items.map((item, i) => (
        <span key={i}>
          {i > 0 && <span className="crumbs-sep">/</span>}
          {item.to ? <Link to={item.to}>{item.label}</Link> : <span aria-current="page">{item.label}</span>}
        </span>
      ))}
    </nav>
  );
}
