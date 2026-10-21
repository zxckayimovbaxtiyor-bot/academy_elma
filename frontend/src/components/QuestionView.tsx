import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { AttemptQuestion } from "../api/types";
import { pick, useLang } from "../lib/lang";
import { Icon } from "./Icon";
import { Lightbox } from "./Lightbox";

const LETTERS = "ABCDEFGH";

/**
 * One test question (mockup 3). Answers are display indices; screenshot options keep
 * their authored order, so their letters match the ones drawn on the image.
 */
export function QuestionView({
  q,
  number,
  onAnswer,
}: {
  q: AttemptQuestion;
  number: number;
  onAnswer: (answer: number[] | null) => void;
}) {
  const { t } = useTranslation();
  const lang = useLang();
  const [zoom, setZoom] = useState(false);
  const kind = {
    single: [t("q.single")],
    multiple: [t("q.multiple")],
    ordering: [t("q.ordering")],
    screenshot: [t("q.screenshot"), t("q.single")],
  }[q.type];
  return (
    <div className="question stack">
      <div className="row wrap">
        <span className="q-number">{t("q.number", { n: number })}</span>
        {kind.map((k) => (
          <span key={k} className="chip">
            {k}
          </span>
        ))}
      </div>
      <h2 className="q-text">{pick(q, "text", lang)}</h2>
      {q.image_url && (
        <figure className="q-figure">
          <button type="button" className="q-image" onClick={() => setZoom(true)} aria-label={t("q.zoom")}>
            <img src={q.image_url} alt={t("q.image")} />
          </button>
          <figcaption>{q.type === "screenshot" ? t("q.screenshot_hint") : t("q.zoom_hint")}</figcaption>
        </figure>
      )}
      {q.type === "ordering" ? <Ordering q={q} onAnswer={onAnswer} /> : <Choices q={q} onAnswer={onAnswer} />}
      {zoom && q.image_url && <Lightbox src={q.image_url} alt={t("q.image")} onClose={() => setZoom(false)} />}
    </div>
  );
}

function Choices({ q, onAnswer }: { q: AttemptQuestion; onAnswer: (answer: number[] | null) => void }) {
  const { t } = useTranslation();
  const lang = useLang();
  const multiple = q.type === "multiple";
  const chosen = new Set(q.answer ?? []);
  const toggle = (index: number) => {
    if (!multiple) return onAnswer([index]);
    const next = new Set(chosen);
    if (next.has(index)) next.delete(index);
    else next.add(index);
    onAnswer(next.size ? [...next].sort((a, b) => a - b) : null);
  };
  return (
    <div className="options" role="group" aria-label={t("q.options")}>
      {q.options.map((o) => {
        const on = chosen.has(o.index);
        return (
          <label key={o.index} className={`option ${on ? "on" : ""}`}>
            <input
              type={multiple ? "checkbox" : "radio"}
              name={`q-${q.position}`}
              checked={on}
              onChange={() => toggle(o.index)}
            />
            <span>
              {q.type === "screenshot" && <strong>{LETTERS[o.index]} — </strong>}
              {pick(o, "text", lang)}
            </span>
          </label>
        );
      })}
    </div>
  );
}

/** Step ordering with ▲▼ buttons (no drag and drop). The answer is the full order. */
function Ordering({ q, onAnswer }: { q: AttemptQuestion; onAnswer: (answer: number[] | null) => void }) {
  const { t } = useTranslation();
  const lang = useLang();
  const order = q.answer && q.answer.length === q.options.length ? q.answer : q.options.map((o) => o.index);
  const byIndex = new Map(q.options.map((o) => [o.index, o]));
  const move = (from: number, to: number) => {
    const next = [...order];
    const [item] = next.splice(from, 1);
    next.splice(to, 0, item);
    onAnswer(next);
  };
  return (
    <div className="stack-sm">
      <p className="muted">{t("q.ordering_hint")}</p>
      <ol className="ordering">
        {order.map((index, i) => (
          <li key={index} className="order-item">
            <span className="order-num">{i + 1}</span>
            <span className="grow">{pick(byIndex.get(index)!, "text", lang)}</span>
            <button
              type="button"
              className="btn btn-small"
              disabled={i === 0}
              onClick={() => move(i, i - 1)}
              aria-label={t("q.move_up")}
            >
              <Icon name="up" size={18} />
            </button>
            <button
              type="button"
              className="btn btn-small"
              disabled={i === order.length - 1}
              onClick={() => move(i, i + 1)}
              aria-label={t("q.move_down")}
            >
              <Icon name="down" size={18} />
            </button>
          </li>
        ))}
      </ol>
      {q.answer === null && (
        <div>
          <button type="button" className="btn" onClick={() => onAnswer(order)}>
            <Icon name="check" size={18} />
            {t("q.ordering_confirm")}
          </button>
        </div>
      )}
    </div>
  );
}
