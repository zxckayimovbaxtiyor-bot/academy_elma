import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { Icon } from "../components/Icon";

/** Small building blocks shared by the admin pages. */

export function PageHead({ title, subtitle, actions }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="a-head">
      <div className="grow">
        <h1>{title}</h1>
        {subtitle && <p className="muted">{subtitle}</p>}
      </div>
      {actions && <div className="row wrap">{actions}</div>}
    </header>
  );
}

export function Modal({
  title,
  children,
  footer,
  onClose,
  wide,
}: {
  title: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  const { t } = useTranslation();
  const box = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  // Focus the dialog once on open; a new onClose on every parent render must not steal focus from inputs.
  useEffect(() => {
    box.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close.current();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  return (
    <div className="backdrop" role="dialog" aria-modal="true" aria-label={typeof title === "string" ? title : undefined}>
      <div className={`dialog stack ${wide ? "dialog-wide" : ""}`} ref={box} tabIndex={-1}>
        <div className="spread">
          <h3>{title}</h3>
          <button className="btn btn-ghost btn-small" onClick={onClose} aria-label={t("app.close")}>
            <Icon name="close" size={18} />
          </button>
        </div>
        {children}
        {footer && <div className="row dialog-foot">{footer}</div>}
      </div>
    </div>
  );
}

// --- toasts -----------------------------------------------------------------------------------

type Tone = "success" | "danger";
const ToastCtx = createContext<(message: string, tone?: Tone) => void>(() => undefined);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<{ id: number; message: string; tone: Tone }[]>([]);
  const next = useRef(1);
  const notify = useCallback((message: string, tone: Tone = "success") => {
    const id = next.current++;
    setItems((list) => [...list, { id, message, tone }]);
    window.setTimeout(() => setItems((list) => list.filter((x) => x.id !== id)), 3500);
  }, []);
  return (
    <ToastCtx.Provider value={notify}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {items.map((x) => (
          <div key={x.id} className={`toast toast-${x.tone}`}>
            <Icon name={x.tone === "success" ? "check" : "alert"} size={18} />
            {x.message}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export const useToast = () => useContext(ToastCtx);

// --- small inputs ------------------------------------------------------------------------------

/** A labelled field; `hint` under the input. */
export function Field({ label, hint, children, htmlFor }: { label: ReactNode; hint?: ReactNode; children: ReactNode; htmlFor?: string }) {
  return (
    <div className="field">
      <label htmlFor={htmlFor}>{label}</label>
      {children}
      {hint && <span className="muted tiny">{hint}</span>}
    </div>
  );
}

/** A button that opens the file chooser and hands over the chosen file. */
export function FilePick({
  accept,
  onFile,
  children,
  className = "btn",
  disabled,
}: {
  accept: string;
  onFile: (file: File) => void;
  children: ReactNode;
  className?: string;
  disabled?: boolean;
}) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <>
      <button type="button" className={className} disabled={disabled} onClick={() => input.current?.click()}>
        {children}
      </button>
      <input
        ref={input}
        type="file"
        accept={accept}
        hidden
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = ""; // the same file can be chosen again
          if (file) onFile(file);
        }}
      />
    </>
  );
}

/** "m:ss" ↔ seconds for video timestamps typed by methodologists. */
export function parseClock(text: string): number | null {
  const m = text.trim().match(/^(?:(\d+):)?(\d{1,2}):(\d{2})$|^(\d+)$/);
  if (!m) return null;
  if (m[4] !== undefined) return Number(m[4]);
  return Number(m[1] ?? 0) * 3600 + Number(m[2]) * 60 + Number(m[3]);
}
