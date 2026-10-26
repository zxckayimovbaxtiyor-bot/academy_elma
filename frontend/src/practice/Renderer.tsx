import { useEffect, useRef, useState, useId, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type {
  ComponentType,
  LText,
  Mistake,
  PComponent,
  PScreen,
  Value,
  SummaryItem,
} from "../api/practice";
import { useLang } from "../lib/lang";
import { practice } from "../api/practice";
import { ErrorLine } from "../components/Feedback";
import { NumberInput } from "./NumberInput";
import { numberText } from "../lib/numberInput";
import "../styles/practice.css";

export type ComponentProps = {
  summary?: SummaryItem[];
  component: PComponent;
  value: Value;
  values: Record<string, Value>;
  change: (value: Value) => void;
  action: (id: string) => void;
  sessionId?: number;
  disabled: boolean;
  guided: boolean;
  invalid: boolean;
  onHint?: (id: string) => void;
  elapsed?: number;
};
type Props = ComponentProps;
type Renderer = (p: Props) => ReactNode;
// Extend this registry together with the validated server schema, preserving existing types.
const registry: Partial<Record<ComponentType, Renderer>> = {};
export function registerPracticeComponent(
  type: ComponentType,
  renderer: Renderer,
) {
  registry[type] = renderer;
}

function Modal({ label }: { label: string }) {
  const ref = useRef<HTMLDialogElement>(null);
  const { t } = useTranslation();
  return (
    <>
      <button
        type="button"
        className="btn"
        onClick={() => ref.current?.showModal()}
      >
        {label}
      </button>
      <dialog ref={ref} className="dialog practice-dialog" aria-label={label}>
        <p>{label}</p>
        <form method="dialog">
          <button className="btn">{t("practice.close")}</button>
        </form>
      </dialog>
    </>
  );
}

function Standard(p: Props) {
  const { component: c, value, change, action, disabled, guided, invalid } = p;
  const lang = useLang();
  const { t } = useTranslation();
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<unknown>(null);
  const label = c.label[lang];
  const instanceId = useId();
  const id = `practice-${c.id}-${instanceId}`;
  const input = {
    id,
    disabled: disabled || c.editable === false,
    placeholder: c.placeholder?.[lang],
    "aria-invalid": invalid,
    "aria-describedby": c.hint && guided ? `${id}-hint` : undefined,
  };
  let node: ReactNode;
  switch (c.type) {
    case "date":
    case "text":
      node = (
        <input
          {...input}
          type={c.type === "date" ? "date" : "text"}
          value={value === null ? "" : String(value)}
          maxLength={2000}
          onChange={(e) => change(e.target.value)}
        />
      );
      break;
    case "number":
      node = <NumberInput {...input} value={value} change={change} />;
      break;
    case "switch":
    case "checkbox":
      node = (
        <input
          {...input}
          type="checkbox"
          checked={value === true}
          onChange={(e) => change(e.target.checked)}
        />
      );
      break;
    case "dialog":
    case "select":
    case "document":
      node = (
        <>
          <select
            {...input}
            value={typeof value === "string" ? value : ""}
            onChange={(e) => change(e.target.value || null)}
          >
            <option value="">{t("practice.choose")}</option>
            {c.options.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label[lang]}
              </option>
            ))}
          </select>
          {c.type === "document" && value && (
            <div className="practice-document">
              <span className="chip">{t("practice.synthetic")}</span>
              <strong>
                {c.options.find((o) => o.value === value)?.label[lang]}
              </strong>
              <p>{t("practice.document_notice")}</p>
            </div>
          )}
        </>
      );
      break;
    case "tabs":
      node = (
        <div className="row" role="group" aria-label={label}>
          {c.options.map((o) => (
            <button
              type="button"
              className={`btn ${value === o.value ? "btn-primary" : ""}`}
              key={o.value}
              disabled={disabled || c.editable === false}
              aria-pressed={value === o.value}
              onClick={() => change(o.value)}
            >
              {o.label[lang]}
            </button>
          ))}
        </div>
      );
      break;
    case "button":
    case "transition":
      return (
        <button
          type="button"
          className={`btn btn-primary ${guided ? "practice-highlight" : ""}`}
          disabled={disabled || c.editable === false}
          title={guided ? c.hint?.[lang] : undefined}
          onClick={() => action(c.id)}
        >
          {label}
        </button>
      );
    case "products":
    case "operations":
    case "table":
    case "client": {
      const columns = [
        ...new Set([
          ...(c.columns ?? []).map((col) => col.value),
          ...c.rows.flatMap((row) => Object.keys(row)),
        ]),
      ];
      node = (
        <div className="practice-table">
          <table>
            <thead>
              <tr>
                {columns.map((col) => (
                  <th key={col}>
                    {c.columns?.find((x) => x.value === col)?.label[lang] ??
                      t(`practice.column.${col}`, { defaultValue: col })}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {c.rows.map((r, i) => (
                <tr key={i}>
                  {columns.map((col) => (
                    <td key={col}>
                      {r[col] === "draft" ? t("practice.draft") : r[col]}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      break;
    }
    case "result":
    case "check_status":
    case "status":
      node = (
        <dl className="practice-summary">
          {(
            p.summary ??
            Object.entries(p.values).map(([field, value]) => ({
              field,
              label: { ru: field, uz: field },
              value,
            }))
          ).map(({ field, label, value: v }) => (
            <div key={field}>
              <dt>{label[lang]}</dt>
              <dd>
                {typeof v === "boolean"
                  ? t(v ? "practice.yes" : "practice.no")
                  : typeof v === "number"
                    ? numberText(v)
                    : typeof v === "object" && v !== null
                      ? v[lang]
                      : String(v ?? "—")}
              </dd>
            </div>
          ))}
        </dl>
      );
      break;
    case "heading":
      return <h3>{label}</h3>;
    case "paragraph":
      return <p style={{ whiteSpace: "pre-wrap" }}>{label}</p>;
    case "timer":
      return (
        <div className="notice">
          <strong>{label}</strong> · {Math.floor((p.elapsed ?? 0) / 60)}:
          {String((p.elapsed ?? 0) % 60).padStart(2, "0")}
        </div>
      );
    case "file":
      node = (
        <>
          <input
            {...input}
            disabled={input.disabled || uploading}
            type="file"
            accept=".pdf,.png,.jpg,.jpeg"
            onChange={async (e) => {
              const f = e.target.files?.[0];
              if (!f) {
                change(null);
                return;
              }
              if (!p.sessionId) {
                change(f.name.slice(0, 200));
                return;
              }
              setUploading(true);
              setUploadError(null);
              try {
                const result = await practice.uploadFile(p.sessionId, c.id, f);
                change(result.value);
              } catch (error) {
                setUploadError(error);
              } finally {
                setUploading(false);
              }
            }}
          />
          {uploading && <small role="status">{t("practice.saving")}</small>}
          <ErrorLine error={uploadError} />
          {value &&
            (p.sessionId && String(value).startsWith("upload_") ? (
              <a
                href={`/api/v1/me/practice-sessions/${p.sessionId}/files/${String(value).slice(7)}`}
                download
              >
                {c.upload_name ?? t("practice.component.file")}
              </a>
            ) : (
              <span className="chip">{String(value)}</span>
            ))}
          <small className="muted">
            {t(
              p.sessionId ? "studio.file_notice" : "studio.file_preview_notice",
            )}
          </small>
        </>
      );
      break;
    case "card":
    case "passport":
    case "loan":
      return (
        <article className="practice-card">
          <h3>{label}</h3>
          <span className="chip">{t("practice.synthetic")}</span>
          <dl className="practice-summary">
            {c.rows.flatMap((r, i) =>
              Object.entries(r).map(([key, v]) => (
                <div key={`${i}-${key}`}>
                  <dt>
                    {c.columns?.find((col) => col.value === key)?.label[lang] ??
                      key}
                  </dt>
                  <dd>{v}</dd>
                </div>
              )),
            )}
          </dl>
        </article>
      );
    case "video":
      return c.asset_id ? (
        <figure>
          <video
            className="practice-video"
            controls
            preload="metadata"
            src={`/api/v1/practice-assets/${c.asset_id}${p.sessionId ? `?session_id=${p.sessionId}` : ""}`}
          />
          <figcaption>{label}</figcaption>
        </figure>
      ) : (
        <div className="notice">{label}</div>
      );
    case "modal":
      return <Modal label={label} />;
    case "image":
      return (
        <figure className="practice-image">
          <img
            alt={label}
            src={`/api/v1/practice-assets/${c.asset_id}${p.sessionId ? `?session_id=${p.sessionId}` : ""}`}
          />
          {c.hotspots.map((h, i) => (
            <button
              type="button"
              key={i}
              disabled={disabled || c.editable === false}
              aria-label={h.label[lang]}
              title={h.label[lang]}
              className="practice-hotspot"
              style={{
                left: `${h.x}%`,
                top: `${h.y}%`,
                width: `${h.width}%`,
                height: `${h.height}%`,
              }}
              onClick={() => action(h.action)}
            >
              {h.label[lang]}
            </button>
          ))}
          <figcaption>{label}</figcaption>
        </figure>
      );
    case "hint":
      return guided ? (
        <Hint label={label} show={() => p.onHint?.(c.id)} />
      ) : null;
    default:
      return (
        <div className="notice">
          <span>{label}</span>
        </div>
      );
  }
  return (
    <div className={`practice-field ${invalid ? "practice-invalid" : ""}`}>
      <label htmlFor={id}>
        {label}
        {c.required && <span aria-label={t("practice.required")}> *</span>}
      </label>
      {node}
      {guided && c.hint && (
        <Hint
          id={`${id}-hint`}
          label={c.hint[lang]}
          show={() => p.onHint?.(c.id)}
        />
      )}
    </div>
  );
}

export const PracticeComponentView = Standard;
function Hint({
  label,
  show,
  id,
}: {
  label: string;
  show: () => void;
  id?: string;
}) {
  const { t } = useTranslation();
  return (
    <details
      id={id}
      className="notice"
      onToggle={(e) => {
        if (e.currentTarget.open) show();
      }}
    >
      <summary>{t("studio.show_hint")}</summary>
      <p>{label}</p>
    </details>
  );
}
export function ScenarioScreen({
  summary,
  screen,
  values,
  setValues,
  onAction,
  disabled = false,
  guided = true,
  feedback = [],
  sessionId,
  onEvent,
  onHint,
  elapsed,
}: {
  summary?: SummaryItem[];
  screen: PScreen;
  values: Record<string, Value>;
  setValues: (v: Record<string, Value>) => void;
  onAction: (id: string) => void;
  disabled?: boolean;
  guided?: boolean;
  feedback?: Mistake[];
  sessionId?: number;
  onEvent?: (
    id: string,
    event: "change" | "submit" | "click",
    values: Record<string, Value>,
  ) => void;
  onHint?: (id: string) => void;
  elapsed?: number;
}) {
  const lang = useLang();
  const { t } = useTranslation();
  const heading = useRef<HTMLHeadingElement>(null);
  const previous = useRef(screen.id);
  useEffect(() => {
    if (previous.current !== screen.id) {
      const content = heading.current?.closest(".practice-content");
      if (content) content.scrollTop = 0;
      heading.current?.focus({ preventScroll: true });
      previous.current = screen.id;
    }
  }, [screen.id]);
  return (
    <section className="stack practice-workspace">
      <header>
        <h2 ref={heading} tabIndex={-1}>
          {screen.title[lang]}
        </h2>
        <p className="muted">{screen.description[lang]}</p>
      </header>
      {feedback.length > 0 && (
        <div className="notice notice-danger" role="alert">
          <ul>
            {feedback.map((e, i) => (
              <li key={i}>
                {e.message?.[lang] ??
                  t(
                    e.field ? "practice.required_field" : "practice.check_data",
                    {
                      field:
                        screen.components.find((c) => c.id === e.field)?.label[
                          lang
                        ] ?? "",
                    },
                  )}
              </li>
            ))}
          </ul>
        </div>
      )}
      <form
        className="practice-screen-grid"
        onSubmit={(e) => {
          e.preventDefault();
          const button = screen.components.find((c) => c.type === "button");
          if (button) onEvent?.(button.id, "submit", values);
        }}
      >
        {screen.components.map((c) => {
          const props: Props = {
            summary,
            component: c,
            value: values[c.id] ?? null,
            values,
            change: (v) => setValues({ ...values, [c.id]: v }),
            action: onAction,
            sessionId,
            onHint,
            elapsed,
            disabled,
            guided,
            invalid: feedback.some((e) => e.field === c.id),
          };
          return (
            <div
              key={c.id}
              style={{ gridColumn: c.width === "half" ? "span 1" : "1 / -1" }}
              onBlur={(e) => {
                if ((e.relatedTarget as HTMLElement | null)?.closest("button"))
                  return;
                if (
                  !e.currentTarget.contains(e.relatedTarget) &&
                  c.event_types?.includes("change")
                )
                  onEvent?.(c.id, "change", values);
              }}
            >
              {registry[c.type] ? (
                registry[c.type]!(props)
              ) : (
                <Standard {...props} />
              )}
            </div>
          );
        })}
      </form>
    </section>
  );
}

export function Bilingual({
  label,
  value,
  onChange,
}: {
  label: string;
  value: LText;
  onChange: (v: LText) => void;
}) {
  return (
    <fieldset className="practice-bilingual">
      <legend>{label}</legend>
      {(["ru", "uz"] as const).map((lang) => (
        <label key={lang}>
          {lang.toUpperCase()}
          <textarea
            maxLength={2000}
            value={value[lang]}
            onChange={(e) => onChange({ ...value, [lang]: e.target.value })}
          />
        </label>
      ))}
    </fieldset>
  );
}
