import { Component, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

function RetryPage() {
  const { t } = useTranslation();
  return (
    <div className="center-box" role="alert">
      <p>{t("app.load_failed")}</p>
      <button
        className="btn btn-primary"
        onClick={() => window.location.reload()}
      >
        {t("app.retry")}
      </button>
    </div>
  );
}

/** Keep a failed page import or render from leaving the entire app blank. */
export class AppBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    return this.state.failed ? <RetryPage /> : this.props.children;
  }
}
