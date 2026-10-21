import { useEffect } from "react";
import { useTranslation } from "react-i18next";

import { Icon } from "./Icon";

/** Click-to-enlarge for screenshots; plain CSS, closes on Esc or click. */
export function Lightbox({ src, alt, onClose }: { src: string; alt: string; onClose: () => void }) {
  const { t } = useTranslation();
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="backdrop lightbox" role="dialog" aria-modal="true" onClick={onClose}>
      <button className="btn btn-ghost lightbox-close" onClick={onClose} aria-label={t("app.close")}>
        <Icon name="close" />
      </button>
      <img src={src} alt={alt} />
    </div>
  );
}
