import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { content } from "../api/admin";
import {
  practice,
  componentTypes,
  type Command,
  type Condition,
  type Definition,
  type LText,
  type PComponent,
  type Policy,
  type Preview,
  type PScreen,
  type Rule,
  type Scenario,
  type Value,
} from "../api/practice";
import { ErrorLine, ErrorState, PageLoader } from "../components/Feedback";
import { Icon } from "../components/Icon";
import { useApi } from "../lib/useApi";
import { pick, useLang } from "../lib/lang";
import { Bilingual, ScenarioScreen } from "./Renderer";

const text = (): LText => ({ ru: "", uz: "" });
const key = (prefix: string) =>
  `${prefix}_${crypto.randomUUID().replaceAll("-", "").slice(0, 8)}`;
const button = (): PComponent => ({
  id: key("action"),
  type: "button",
  label: { ru: "Продолжить", uz: "Davom etish" },
  required: false,
  options: [],
  rows: [],
  hotspots: [],
});
function blank(): Definition {
  const next = button();
  return {
    schema_version: 1,
    tasks: [],
    title: text(),
    description: text(),
    roles: ["learner", "branch_head"],
    start: "start",
    completion: ["result"],
    screens: [
      {
        id: "start",
        title: { ru: "Начало", uz: "Boshlanish" },
        description: { ru: "Учебная операция", uz: "Oʻquv amaliyoti" },
        components: [next],
        transitions: [{ action: next.id, target: "result", conditions: [] }],
        rules: [],
      },
      {
        id: "result",
        title: { ru: "Результат", uz: "Natija" },
        description: { ru: "Завершите практику", uz: "Amaliyotni yakunlang" },
        components: [],
        transitions: [],
        rules: [],
      },
    ],
  };
}

export function PracticeBuilder() {
  const { t } = useTranslation();
  const lang = useLang();
  const list = useApi(() => practice.scenarios(), []);
  const modules = useApi(() => content.modules(), []);
  const [selected, setSelected] = useState<Scenario | null>(null);
  const [def, setDef] = useState<Definition | null>(null);
  const [screenId, setScreenId] = useState("start");
  const [moduleId, setModuleId] = useState(0);
  const [lessonId, setLessonId] = useState<number | null>(null);
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState("");
  const [dirty, setDirty] = useState(false);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [previewValues, setPreviewValues] = useState<Record<string, Value>>({});
  const [reviewed, setReviewed] = useState(false);
  const previewDialog = useRef<HTMLDialogElement>(null);
  const lessons = useApi(
    () => (moduleId ? content.lessons(moduleId) : Promise.resolve([])),
    [moduleId],
  );
  useEffect(() => {
    if (!dirty) return;
    const f = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener("beforeunload", f);
    return () => window.removeEventListener("beforeunload", f);
  }, [dirty]);
  const update = (d: Definition) => {
    setDef(d);
    setDirty(true);
    setReviewed(false);
    setNotice("");
  };
  const load = (s: Scenario) => {
    setSelected(s);
    setDef(structuredClone(s.definition));
    setScreenId(s.definition.start);
    setModuleId(s.module_id);
    setLessonId(s.lesson_id);
    setPolicy(s.policy);
    setDirty(false);
    setReviewed(false);
    setNotice("");
    setError(null);
  };
  const fresh = async (demo: boolean) => {
    setBusy(true);
    try {
      setSelected(null);
      const d = demo ? await practice.template() : blank();
      setDef(d);
      setScreenId(d.start);
      setPolicy(null);
      setLessonId(null);
      setReviewed(false);
      setDirty(true);
      setError(null);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  const save = async (): Promise<Scenario | null> => {
    if (!def || !moduleId) return null;
    setError(null);
    const s = selected
      ? await practice.save(selected.id, selected.revision, def)
      : await practice.create(moduleId, lessonId, def);
    setSelected(s);
    setPolicy(policy ?? s.policy);
    setDirty(false);
    list.reload();
    return s;
  };
  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    setNotice("");
    try {
      await fn();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  const openPreview = () =>
    run(async () => {
      if (!def) return;
      const s = dirty || !selected ? await save() : selected;
      if (!s) return;
      await practice.review(s.id, s.revision);
      const state = {
        screen: def.start,
        values: {},
        history: [],
        visited: [def.start],
        mistakes: [],
        task_id: def.tasks[0]?.id ?? null,
      };
      const p = await practice.preview(def, state, {
        request_id: crypto.randomUUID(),
        expected_revision: 0,
        kind: "save",
      });
      setPreview(p);
      setPreviewValues(p.values);
      setReviewed(true);
      previewDialog.current?.showModal();
    });
  const previewStep = async (kind: Command["kind"], action?: string) => {
    if (!def || !preview) return;
    setBusy(true);
    setError(null);
    try {
      const editable = Object.fromEntries(
        Object.entries(previewValues).filter(([id]) =>
          preview.screen.components.some(
            (c) =>
              c.id === id &&
              [
                "text",
                "number",
                "select",
                "checkbox",
                "document",
                "tabs",
              ].includes(c.type),
          ),
        ),
      );
      const p = await practice.preview(def, preview.state, {
        request_id: crypto.randomUUID(),
        expected_revision: 0,
        kind,
        action,
        values: kind === "action" || kind === "save" ? editable : {},
      });
      setPreview(p);
      setPreviewValues(p.values);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  if (list.loading || modules.loading) return <PageLoader />;
  if (list.error || modules.error)
    return (
      <ErrorState
        error={list.error || modules.error}
        onRetry={() => {
          list.reload();
          modules.reload();
        }}
      />
    );
  const screen = def?.screens.find((s) => s.id === screenId);
  const patchScreen = (s: PScreen) => {
    if (def)
      update({
        ...def,
        screens: def.screens.map((old) => (old.id === s.id ? s : old)),
      });
  };
  const move = (index: number, delta: number) => {
    if (!screen) return;
    const components = [...screen.components];
    const target = index + delta;
    if (target < 0 || target >= components.length) return;
    [components[index], components[target]] = [
      components[target],
      components[index],
    ];
    patchScreen({ ...screen, components });
  };
  const fields =
    def?.screens.flatMap((s) =>
      s.components.filter((c) =>
        ["text", "number", "select", "checkbox", "document", "tabs"].includes(
          c.type,
        ),
      ),
    ) ?? [];
  const uniqueFields = [...new Map(fields.map((c) => [c.id, c])).values()];
  return (
    <div className="stack-lg">
      <header className="spread practice-wrap">
        <div>
          <h1>{t("practice.builder")}</h1>
          <p className="muted">{t("practice.builder_intro")}</p>
        </div>
        <div className="row practice-wrap">
          <button
            className="btn"
            disabled={busy || dirty}
            onClick={() => fresh(false)}
          >
            {t("practice.new")}
          </button>
          <button
            className="btn"
            disabled={busy || dirty}
            onClick={() => fresh(true)}
          >
            {t("practice.demo")}
          </button>
        </div>
      </header>
      <ErrorLine error={error} />
      {notice && (
        <div role="status" className="notice">
          {notice}
        </div>
      )}
      <div className="practice-builder">
        <nav
          className="practice-builder-nav"
          aria-label={t("practice.scenarios")}
        >
          {list.data?.map((s) => (
            <button
              className={`btn ${s.id === selected?.id ? "btn-primary" : ""}`}
              key={s.id}
              disabled={busy || dirty}
              onClick={() => load(s)}
            >
              {s.definition.title[lang]}
              <br />
              {t(s.published ? "practice.published" : "practice.draft")} ·{" "}
              {s.number}
            </button>
          ))}
          {dirty && <p className="small muted">{t("practice.unsaved")}</p>}
        </nav>
        {def ? (
          <div className="stack">
            <div className="card card-pad stack">
              <div className="spread practice-wrap">
                <h2>
                  {selected
                    ? t("practice.version", { number: selected.number })
                    : t("practice.new")}
                </h2>
                <div className="row practice-wrap">
                  <button
                    className="btn"
                    disabled={busy || !moduleId}
                    onClick={() =>
                      run(async () => {
                        await save();
                        setNotice(t("practice.saved"));
                      })
                    }
                  >
                    {t("practice.save_draft")}
                  </button>
                  <button
                    className="btn"
                    disabled={busy || !moduleId}
                    onClick={openPreview}
                  >
                    {t("practice.preview")}
                  </button>
                  <button
                    className="btn btn-primary"
                    disabled={
                      busy ||
                      !selected ||
                      dirty ||
                      selected.published ||
                      !reviewed
                    }
                    onClick={() =>
                      run(async () => {
                        if (selected) {
                          const s = await practice.publish(
                            selected.id,
                            selected.revision,
                          );
                          load(s);
                          list.reload();
                          setNotice(t("practice.published"));
                        }
                      })
                    }
                  >
                    {t("practice.publish")}
                  </button>
                </div>
              </div>
              <Bilingual
                label={t("practice.name")}
                value={def.title}
                onChange={(title) => update({ ...def, title })}
              />
              <Bilingual
                label={t("practice.description")}
                value={def.description}
                onChange={(description) => update({ ...def, description })}
              />
              <div className="practice-editor-grid">
                <label>
                  {t("practice.module")}
                  <select
                    value={moduleId}
                    disabled={!!selected}
                    onChange={(e) => {
                      setModuleId(Number(e.target.value));
                      setLessonId(null);
                      setDirty(true);
                    }}
                  >
                    <option value="0">{t("practice.choose")}</option>
                    {modules.data?.map((m) => (
                      <option key={m.id} value={m.id}>
                        {pick(m, "title", lang)}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  {t("practice.lesson")}
                  <select
                    value={lessonId ?? ""}
                    disabled={!!selected}
                    onChange={(e) => {
                      setLessonId(Number(e.target.value) || null);
                      setDirty(true);
                    }}
                  >
                    <option value="">{t("practice.module_level")}</option>
                    {lessons.data?.map((l) => (
                      <option key={l.id} value={l.id}>
                        {pick(l, "title", lang)}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <fieldset className="row practice-wrap">
                <legend>{t("practice.allowed_roles")}</legend>
                {["learner", "branch_head", "methodologist", "admin"].map(
                  (role) => (
                    <label key={role}>
                      <input
                        type="checkbox"
                        checked={def.roles.includes(role)}
                        onChange={(e) =>
                          update({
                            ...def,
                            roles: e.target.checked
                              ? [...def.roles, role]
                              : def.roles.filter((r) => r !== role),
                          })
                        }
                      />
                      {t(`roles.${role}`)}
                    </label>
                  ),
                )}
              </fieldset>
            </div>
            <details className="card card-pad stack">
              <summary>{t("practice.individual_tasks")}</summary>
              <p className="muted">{t("practice.tasks_intro")}</p>
              {def.tasks.map((task, i) => (
                <div key={task.id} className="practice-editor-item">
                  <Bilingual
                    label={t("practice.task_description")}
                    value={task.description}
                    onChange={(description) =>
                      update({
                        ...def,
                        tasks: def.tasks.map((x, j) =>
                          j === i ? { ...x, description } : x,
                        ),
                      })
                    }
                  />
                  {Object.entries(task.expected).map(([field, value]) => (
                    <div key={field} className="row practice-wrap">
                      <label>
                        {uniqueFields.find((f) => f.id === field)?.label[
                          lang
                        ] || field}
                        <input
                          type={
                            uniqueFields.find((f) => f.id === field)?.type ===
                            "number"
                              ? "number"
                              : "text"
                          }
                          value={String(value ?? "")}
                          onChange={(e) =>
                            update({
                              ...def,
                              tasks: def.tasks.map((x, j) =>
                                j === i
                                  ? {
                                      ...x,
                                      expected: {
                                        ...x.expected,
                                        [field]:
                                          uniqueFields.find(
                                            (f) => f.id === field,
                                          )?.type === "number"
                                            ? Number(e.target.value)
                                            : uniqueFields.find(
                                                  (f) => f.id === field,
                                                )?.type === "checkbox"
                                              ? e.target.value === "true"
                                              : e.target.value,
                                      },
                                    }
                                  : x,
                              ),
                            })
                          }
                        />
                      </label>
                      <button
                        className="btn"
                        onClick={() => {
                          const expected = { ...task.expected };
                          delete expected[field];
                          update({
                            ...def,
                            tasks: def.tasks.map((x, j) =>
                              j === i ? { ...x, expected } : x,
                            ),
                          });
                        }}
                      >
                        {t("practice.remove")}
                      </button>
                    </div>
                  ))}
                  <label>
                    {t("practice.add_task_field")}
                    <select
                      value=""
                      onChange={(e) => {
                        if (e.target.value)
                          update({
                            ...def,
                            tasks: def.tasks.map((x, j) =>
                              j === i
                                ? {
                                    ...x,
                                    expected: {
                                      ...x.expected,
                                      [e.target.value]: null,
                                    },
                                  }
                                : x,
                            ),
                          });
                      }}
                    >
                      <option value="">{t("practice.choose")}</option>
                      {uniqueFields
                        .filter((f) => !Object.hasOwn(task.expected, f.id))
                        .map((f) => (
                          <option key={f.id} value={f.id}>
                            {f.label[lang] || f.id}
                          </option>
                        ))}
                    </select>
                  </label>
                  <button
                    className="btn"
                    onClick={() =>
                      update({
                        ...def,
                        tasks: def.tasks.filter((_, j) => j !== i),
                      })
                    }
                  >
                    {t("practice.remove")}
                  </button>
                </div>
              ))}
              <button
                className="btn"
                onClick={() =>
                  update({
                    ...def,
                    tasks: [
                      ...def.tasks,
                      { id: key("task"), description: text(), expected: {} },
                    ],
                  })
                }
              >
                {t("practice.add_task")}
              </button>
            </details>
            <section className="card card-pad stack">
              <div className="spread practice-wrap">
                <h2>{t("practice.screens")}</h2>
                <button
                  className="btn"
                  disabled={busy}
                  onClick={() => {
                    const id = key("screen");
                    const b = button();
                    const added: PScreen = {
                      id,
                      title: text(),
                      description: text(),
                      components: [b],
                      transitions: [
                        {
                          action: b.id,
                          target: def.completion[0],
                          conditions: [],
                        },
                      ],
                      rules: [],
                    };
                    update({
                      ...def,
                      screens: [
                        ...def.screens.slice(0, -1),
                        added,
                        def.screens.at(-1)!,
                      ],
                    });
                    setScreenId(id);
                  }}
                >
                  {t("practice.add_screen")}
                </button>
              </div>
              <div className="practice-flow" aria-label={t("practice.flow")}>
                {def.screens.map((s) => (
                  <div key={s.id}>
                    <a
                      href={`#screen-${s.id}`}
                      onClick={() => setScreenId(s.id)}
                    >
                      {s.title[lang] || s.id}
                    </a>
                    {s.transitions.map((tr, i) => (
                      <span key={i}>
                        {" "}
                        →{" "}
                        <a
                          href={`#screen-${tr.target}`}
                          onClick={() => setScreenId(tr.target)}
                        >
                          {def.screens.find((x) => x.id === tr.target)?.title[
                            lang
                          ] || tr.target}
                        </a>
                      </span>
                    ))}
                  </div>
                ))}
              </div>
              <div className="row practice-wrap">
                {def.screens.map((s) => (
                  <button
                    className={`btn ${screenId === s.id ? "btn-primary" : ""}`}
                    key={s.id}
                    onClick={() => setScreenId(s.id)}
                  >
                    {s.title[lang] || s.id}
                  </button>
                ))}
              </div>
            </section>
            {screen && (
              <section className="stack" id={`screen-${screen.id}`}>
                <div className="card card-pad stack">
                  <Bilingual
                    label={t("practice.screen_title")}
                    value={screen.title}
                    onChange={(title) => patchScreen({ ...screen, title })}
                  />
                  <Bilingual
                    label={t("practice.description")}
                    value={screen.description}
                    onChange={(description) =>
                      patchScreen({ ...screen, description })
                    }
                  />
                  <div className="row practice-wrap">
                    <label>
                      <input
                        type="radio"
                        name="start-screen"
                        checked={def.start === screen.id}
                        onChange={() => update({ ...def, start: screen.id })}
                      />
                      {t("practice.start_screen")}
                    </label>
                    <label>
                      <input
                        type="checkbox"
                        checked={def.completion.includes(screen.id)}
                        onChange={(e) => {
                          update({
                            ...def,
                            completion: e.target.checked
                              ? [...def.completion, screen.id]
                              : def.completion.filter((id) => id !== screen.id),
                            screens: def.screens.map((s) =>
                              s.id === screen.id && e.target.checked
                                ? { ...s, transitions: [] }
                                : s,
                            ),
                          });
                        }}
                      />
                      {t("practice.terminal")}
                    </label>
                    <button
                      className="btn"
                      disabled={
                        def.start === screen.id || def.screens.length <= 2
                      }
                      onClick={() => {
                        const screens = def.screens
                          .filter((s) => s.id !== screen.id)
                          .map((s) => ({
                            ...s,
                            transitions: s.transitions.filter(
                              (tr) => tr.target !== screen.id,
                            ),
                          }));
                        update({
                          ...def,
                          screens,
                          completion: def.completion.filter(
                            (id) => id !== screen.id,
                          ),
                        });
                        setScreenId(def.start);
                      }}
                    >
                      {t("practice.delete_screen")}
                    </button>
                  </div>
                  <label>
                    {t("practice.add_component")}
                    <select
                      value=""
                      onChange={(e) => {
                        if (!e.target.value) return;
                        const c: PComponent = {
                          id: key("field"),
                          type: e.target.value as PComponent["type"],
                          label: text(),
                          hint: null,
                          required: false,
                          rows: [],
                          hotspots: [],
                          options: ["select", "document", "tabs"].includes(
                            e.target.value,
                          )
                            ? [{ value: "option_1", label: text() }]
                            : [],
                        };
                        patchScreen({
                          ...screen,
                          components: [...screen.components, c],
                        });
                      }}
                    >
                      <option value="">{t("practice.choose")}</option>
                      {componentTypes.map((type) => (
                        <option key={type} value={type}>
                          {t(`practice.component.${type}`)}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                {screen.components.map((c, index) => {
                  const patch = (v: PComponent) =>
                    patchScreen({
                      ...screen,
                      components: screen.components.map((old) =>
                        old.id === c.id ? v : old,
                      ),
                    });
                  return (
                    <div key={c.id} className="practice-editor-item">
                      <div className="spread practice-wrap">
                        <strong>
                          {t(`practice.component.${c.type}`)} · {index + 1}
                        </strong>
                        <div className="row">
                          <button
                            className="btn"
                            aria-label={t("practice.move_up")}
                            disabled={index === 0}
                            onClick={() => move(index, -1)}
                          >
                            ↑
                          </button>
                          <button
                            className="btn"
                            aria-label={t("practice.move_down")}
                            disabled={index === screen.components.length - 1}
                            onClick={() => move(index, 1)}
                          >
                            ↓
                          </button>
                          <button
                            className="btn"
                            onClick={() =>
                              patchScreen({
                                ...screen,
                                components: screen.components.filter(
                                  (x) => x.id !== c.id,
                                ),
                                transitions: screen.transitions.filter(
                                  (tr) => tr.action !== c.id,
                                ),
                              })
                            }
                          >
                            {t("practice.remove")}
                          </button>
                        </div>
                      </div>
                      <Bilingual
                        label={t("practice.label")}
                        value={c.label}
                        onChange={(label) => patch({ ...c, label })}
                      />
                      <Bilingual
                        label={t("practice.hint")}
                        value={c.hint ?? text()}
                        onChange={(hint) =>
                          patch({
                            ...c,
                            hint: hint.ru || hint.uz ? hint : null,
                          })
                        }
                      />
                      {[
                        "text",
                        "number",
                        "checkbox",
                        "select",
                        "document",
                        "tabs",
                      ].includes(c.type) && (
                        <label>
                          <input
                            type="checkbox"
                            checked={c.required}
                            onChange={(e) =>
                              patch({ ...c, required: e.target.checked })
                            }
                          />
                          {t("practice.required")}
                        </label>
                      )}
                      {["select", "document", "tabs"].includes(c.type) && (
                        <div className="stack">
                          {c.options.map((o, i) => (
                            <div className="practice-editor-item" key={i}>
                              <label>
                                {t("practice.option_value")}
                                <input
                                  value={o.value}
                                  maxLength={100}
                                  onChange={(e) =>
                                    patch({
                                      ...c,
                                      options: c.options.map((x, j) =>
                                        j === i
                                          ? { ...x, value: e.target.value }
                                          : x,
                                      ),
                                    })
                                  }
                                />
                              </label>
                              <Bilingual
                                label={t("practice.label")}
                                value={o.label}
                                onChange={(label) =>
                                  patch({
                                    ...c,
                                    options: c.options.map((x, j) =>
                                      j === i ? { ...x, label } : x,
                                    ),
                                  })
                                }
                              />
                              <button
                                className="btn"
                                onClick={() =>
                                  patch({
                                    ...c,
                                    options: c.options.filter(
                                      (_, j) => j !== i,
                                    ),
                                  })
                                }
                              >
                                {t("practice.remove")}
                              </button>
                            </div>
                          ))}
                          <button
                            className="btn"
                            onClick={() =>
                              patch({
                                ...c,
                                options: [
                                  ...c.options,
                                  { value: key("option"), label: text() },
                                ],
                              })
                            }
                          >
                            {t("practice.add_option")}
                          </button>
                        </div>
                      )}
                      {["table", "client"].includes(c.type) && (
                        <div className="stack">
                          {c.rows.map((r, i) => (
                            <div className="row practice-wrap" key={i}>
                              {Object.entries(r).map(([col, val]) => (
                                <label key={col}>
                                  {col}
                                  <input
                                    maxLength={2000}
                                    value={val}
                                    onChange={(e) =>
                                      patch({
                                        ...c,
                                        rows: c.rows.map((x, j) =>
                                          j === i
                                            ? { ...x, [col]: e.target.value }
                                            : x,
                                        ),
                                      })
                                    }
                                  />
                                </label>
                              ))}
                              <button
                                className="btn"
                                onClick={() =>
                                  patch({
                                    ...c,
                                    rows: c.rows.filter((_, j) => j !== i),
                                  })
                                }
                              >
                                {t("practice.remove")}
                              </button>
                            </div>
                          ))}
                          <button
                            className="btn"
                            onClick={() =>
                              patch({
                                ...c,
                                rows: [
                                  ...c.rows,
                                  {
                                    id: "TEST-001",
                                    client: "",
                                    status: "draft",
                                  },
                                ],
                              })
                            }
                          >
                            {t("practice.add_row")}
                          </button>
                        </div>
                      )}
                      {c.type === "image" && (
                        <div className="stack">
                          <p className="muted">
                            {t("practice.screenshot_notice")}
                          </p>
                          <label>
                            {t("practice.upload_screenshot")}
                            <input
                              type="file"
                              accept="image/png,image/jpeg"
                              disabled={!selected || busy}
                              onChange={(e) => {
                                const f = e.target.files?.[0];
                                if (f && selected)
                                  void run(async () => {
                                    const a = await practice.upload(
                                      selected.id,
                                      f,
                                    );
                                    patch({ ...c, asset_id: a.id });
                                  });
                              }}
                            />
                          </label>
                          {c.asset_id && (
                            <img
                              alt={c.label[lang]}
                              src={`/api/v1/practice-assets/${c.asset_id}`}
                              style={{ maxWidth: "100%" }}
                            />
                          )}
                          {c.hotspots.map((h, i) => (
                            <div key={i} className="practice-editor-item">
                              <Bilingual
                                label={t("practice.hotspot")}
                                value={h.label}
                                onChange={(label) =>
                                  patch({
                                    ...c,
                                    hotspots: c.hotspots.map((x, j) =>
                                      j === i ? { ...x, label } : x,
                                    ),
                                  })
                                }
                              />
                              <select
                                aria-label={t("practice.action")}
                                value={h.action}
                                onChange={(e) =>
                                  patch({
                                    ...c,
                                    hotspots: c.hotspots.map((x, j) =>
                                      j === i
                                        ? { ...x, action: e.target.value }
                                        : x,
                                    ),
                                  })
                                }
                              >
                                <option value="">{t("practice.choose")}</option>
                                {screen.components
                                  .filter((x) =>
                                    ["button", "transition"].includes(x.type),
                                  )
                                  .map((x) => (
                                    <option key={x.id} value={x.id}>
                                      {x.label[lang] || x.id}
                                    </option>
                                  ))}
                              </select>
                              <div className="practice-editor-grid">
                                {(["x", "y", "width", "height"] as const).map(
                                  (axis) => (
                                    <label key={axis}>
                                      {t(`practice.area.${axis}`)}
                                      <input
                                        type="number"
                                        min={0}
                                        max={100}
                                        value={h[axis]}
                                        onChange={(e) =>
                                          patch({
                                            ...c,
                                            hotspots: c.hotspots.map((x, j) =>
                                              j === i
                                                ? {
                                                    ...x,
                                                    [axis]: Number(
                                                      e.target.value,
                                                    ),
                                                  }
                                                : x,
                                            ),
                                          })
                                        }
                                      />
                                    </label>
                                  ),
                                )}
                              </div>
                              <button
                                className="btn"
                                onClick={() =>
                                  patch({
                                    ...c,
                                    hotspots: c.hotspots.filter(
                                      (_, j) => j !== i,
                                    ),
                                  })
                                }
                              >
                                {t("practice.remove")}
                              </button>
                            </div>
                          ))}
                          <button
                            className="btn"
                            onClick={() =>
                              patch({
                                ...c,
                                hotspots: [
                                  ...c.hotspots,
                                  {
                                    label: text(),
                                    action:
                                      screen.components.find(
                                        (x) => x.type === "button",
                                      )?.id ?? "",
                                    x: 0,
                                    y: 0,
                                    width: 20,
                                    height: 10,
                                  },
                                ],
                              })
                            }
                          >
                            {t("practice.add_hotspot")}
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })}
                <div className="card card-pad stack">
                  <h3>{t("practice.transitions")}</h3>
                  {screen.transitions.map((tr, i) => (
                    <div key={i} className="practice-editor-item">
                      <div className="practice-editor-grid">
                        <label>
                          {t("practice.action")}
                          <select
                            value={tr.action}
                            onChange={(e) =>
                              patchScreen({
                                ...screen,
                                transitions: screen.transitions.map((x, j) =>
                                  j === i
                                    ? { ...x, action: e.target.value }
                                    : x,
                                ),
                              })
                            }
                          >
                            {screen.components
                              .filter((c) =>
                                ["button", "transition"].includes(c.type),
                              )
                              .map((c) => (
                                <option key={c.id} value={c.id}>
                                  {c.label[lang] || c.id}
                                </option>
                              ))}
                          </select>
                        </label>
                        <label>
                          {t("practice.target")}
                          <select
                            value={tr.target}
                            onChange={(e) =>
                              patchScreen({
                                ...screen,
                                transitions: screen.transitions.map((x, j) =>
                                  j === i
                                    ? { ...x, target: e.target.value }
                                    : x,
                                ),
                              })
                            }
                          >
                            {def.screens.map((s) => (
                              <option key={s.id} value={s.id}>
                                {s.title[lang] || s.id}
                              </option>
                            ))}
                          </select>
                        </label>
                      </div>
                      {tr.conditions.map((cond, k) => (
                        <ConditionEditor
                          key={k}
                          value={cond}
                          fields={uniqueFields}
                          onChange={(value) =>
                            patchScreen({
                              ...screen,
                              transitions: screen.transitions.map((x, j) =>
                                j === i
                                  ? {
                                      ...x,
                                      conditions: x.conditions.map((c, n) =>
                                        n === k ? value : c,
                                      ),
                                    }
                                  : x,
                              ),
                            })
                          }
                          onRemove={() =>
                            patchScreen({
                              ...screen,
                              transitions: screen.transitions.map((x, j) =>
                                j === i
                                  ? {
                                      ...x,
                                      conditions: x.conditions.filter(
                                        (_, n) => n !== k,
                                      ),
                                    }
                                  : x,
                              ),
                            })
                          }
                        />
                      ))}
                      <div className="row">
                        <button
                          className="btn"
                          disabled={!fields.length}
                          onClick={() =>
                            patchScreen({
                              ...screen,
                              transitions: screen.transitions.map((x, j) =>
                                j === i
                                  ? {
                                      ...x,
                                      conditions: [
                                        ...x.conditions,
                                        {
                                          field: fields[0].id,
                                          op: "present",
                                          value: null,
                                        },
                                      ],
                                    }
                                  : x,
                              ),
                            })
                          }
                        >
                          {t("practice.add_condition")}
                        </button>
                        <button
                          className="btn"
                          onClick={() =>
                            patchScreen({
                              ...screen,
                              transitions: screen.transitions.filter(
                                (_, j) => j !== i,
                              ),
                            })
                          }
                        >
                          {t("practice.remove")}
                        </button>
                      </div>
                    </div>
                  ))}
                  <button
                    className="btn"
                    disabled={
                      def.completion.includes(screen.id) ||
                      !screen.components.some((c) =>
                        ["button", "transition"].includes(c.type),
                      )
                    }
                    onClick={() =>
                      patchScreen({
                        ...screen,
                        transitions: [
                          ...screen.transitions,
                          {
                            action: screen.components.find((c) =>
                              ["button", "transition"].includes(c.type),
                            )!.id,
                            target: def.completion[0],
                            conditions: [],
                          },
                        ],
                      })
                    }
                  >
                    {t("practice.add_transition")}
                  </button>
                  <h3>{t("practice.rules")}</h3>
                  {screen.rules.map((r, i) => {
                    const change = (v: Rule) =>
                      patchScreen({
                        ...screen,
                        rules: screen.rules.map((x, j) => (j === i ? v : x)),
                      });
                    return (
                      <div className="practice-editor-item" key={r.id}>
                        <ConditionEditor
                          value={r.condition}
                          fields={uniqueFields}
                          onChange={(condition) => change({ ...r, condition })}
                          onRemove={() =>
                            patchScreen({
                              ...screen,
                              rules: screen.rules.filter((_, j) => j !== i),
                            })
                          }
                        />
                        <Bilingual
                          label={t("practice.error_explanation")}
                          value={r.message}
                          onChange={(message) => change({ ...r, message })}
                        />
                        <label>
                          {t("practice.penalty")}
                          <input
                            type="number"
                            min={1}
                            max={100}
                            value={r.points}
                            onChange={(e) =>
                              change({ ...r, points: Number(e.target.value) })
                            }
                          />
                        </label>
                      </div>
                    );
                  })}
                  <button
                    className="btn"
                    disabled={!fields.length}
                    onClick={() =>
                      patchScreen({
                        ...screen,
                        rules: [
                          ...screen.rules,
                          {
                            id: key("rule"),
                            condition: {
                              field: fields[0].id,
                              op: "present",
                              value: null,
                            },
                            message: text(),
                            points: 10,
                          },
                        ],
                      })
                    }
                  >
                    {t("practice.add_rule")}
                  </button>
                </div>
              </section>
            )}
            {selected && policy && (
              <section className="card card-pad stack">
                <h2>{t("practice.learning_policy")}</h2>
                <div className="practice-editor-grid">
                  {(
                    [
                      "required",
                      "require_pass",
                      "allow_repeat",
                      "repeat_on_update",
                      "repeat_on_material",
                      "theory_first",
                    ] as const
                  ).map((k) => (
                    <label key={k}>
                      <span>
                        <input
                          type="checkbox"
                          checked={policy[k]}
                          onChange={(e) =>
                            setPolicy({ ...policy, [k]: e.target.checked })
                          }
                        />
                        {t(`practice.policy.${k}`)}
                      </span>
                    </label>
                  ))}
                  <label>
                    {t("practice.policy.max_attempts")}
                    <input
                      type="number"
                      min={1}
                      max={20}
                      value={policy.max_attempts}
                      onChange={(e) =>
                        setPolicy({
                          ...policy,
                          max_attempts: Number(e.target.value),
                        })
                      }
                    />
                  </label>
                  <label>
                    {t("practice.policy.pass_pct")}
                    <input
                      type="number"
                      min={1}
                      max={100}
                      value={policy.pass_pct}
                      onChange={(e) =>
                        setPolicy({
                          ...policy,
                          pass_pct: Number(e.target.value),
                        })
                      }
                    />
                  </label>
                  <label>
                    {t("practice.policy.gate")}
                    <select
                      value={policy.gate}
                      onChange={(e) =>
                        setPolicy({
                          ...policy,
                          gate: e.target.value as Policy["gate"],
                        })
                      }
                    >
                      <option value="before_test">
                        {t("practice.before_test")}
                      </option>
                      <option value="before_certificate">
                        {t("practice.before_certificate")}
                      </option>
                    </select>
                  </label>
                </div>
                <button
                  className="btn"
                  disabled={busy}
                  onClick={() =>
                    run(async () => {
                      await practice.assign(selected.id, policy);
                      setNotice(t("practice.saved"));
                    })
                  }
                >
                  {t("practice.save_policy")}
                </button>
              </section>
            )}
          </div>
        ) : (
          <div className="card card-pad muted">
            {t("practice.select_scenario")}
          </div>
        )}
      </div>
      <dialog
        ref={previewDialog}
        className="practice-dialog practice-preview"
        aria-label={t("practice.preview")}
      >
        <div className="stack">
          <div className="spread">
            <h2>{t("practice.preview")}</h2>
            <button
              className="btn"
              onClick={() => previewDialog.current?.close()}
            >
              {t("practice.close")}
            </button>
          </div>
          <p className="muted">{t("practice.preview_notice")}</p>
          {preview?.task && <div className="notice">{preview.task[lang]}</div>}
          <ErrorLine error={error} />
          {preview && (
            <>
              <ScenarioScreen
                summary={preview.summary}
                screen={preview.screen}
                values={previewValues}
                setValues={setPreviewValues}
                onAction={(action) => previewStep("action", action)}
                disabled={busy}
                feedback={preview.feedback}
              />
              <div className="row">
                <button
                  className="back-link"
                  disabled={busy || !preview.history.length}
                  onClick={() => previewStep("back")}
                >
                  <Icon name="arrowLeft" size={18} />
                  {t("practice.back")}
                </button>
                {preview.can_finish && (
                  <button
                    className="btn btn-primary"
                    disabled={busy || preview.finished}
                    onClick={() => previewStep("finish")}
                  >
                    {t("practice.finish")}
                  </button>
                )}
              </div>
              {preview.finished && (
                <p role="status">{t("practice.preview_finished")}</p>
              )}
            </>
          )}
        </div>
      </dialog>
    </div>
  );
}

function ConditionEditor({
  value,
  fields,
  onChange,
  onRemove,
}: {
  value: Condition;
  fields: PComponent[];
  onChange: (c: Condition) => void;
  onRemove: () => void;
}) {
  const { t } = useTranslation();
  const lang = useLang();
  const field = fields.find((f) => f.id === value.field);
  return (
    <div className="practice-editor-grid">
      <label>
        {t("practice.field_label")}
        <select
          value={value.field}
          onChange={(e) =>
            onChange({ ...value, field: e.target.value, value: null })
          }
        >
          {fields.map((f) => (
            <option key={f.id} value={f.id}>
              {f.label[lang] || f.id}
            </option>
          ))}
        </select>
      </label>
      <label>
        {t("practice.operator")}
        <select
          value={value.op}
          onChange={(e) =>
            onChange({
              ...value,
              op: e.target.value as Condition["op"],
              value: null,
            })
          }
        >
          {["present", "eq", "ne", "gte", "lte", "in"].map((op) => (
            <option key={op} value={op}>
              {t(`practice.operator_label.${op}`)}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span>
          <input
            type="checkbox"
            checked={value.task_value ?? false}
            onChange={(e) =>
              onChange({ ...value, task_value: e.target.checked })
            }
          />
          {t("practice.task_value")}
        </span>
      </label>
      {value.op !== "present" && !value.task_value && (
        <label>
          {t("practice.expected")}
          {field?.type === "checkbox" ? (
            <select
              value={String(value.value)}
              onChange={(e) =>
                onChange({ ...value, value: e.target.value === "true" })
              }
            >
              <option value="null">{t("practice.choose")}</option>
              <option value="true">{t("practice.yes")}</option>
              <option value="false">{t("practice.no")}</option>
            </select>
          ) : (
            <input
              type={
                field?.type === "number" && value.op !== "in"
                  ? "number"
                  : "text"
              }
              value={
                Array.isArray(value.value)
                  ? value.value.join(",")
                  : String(value.value ?? "")
              }
              onChange={(e) =>
                onChange({
                  ...value,
                  value:
                    value.op === "in"
                      ? e.target.value.split(",").map((s) => s.trim())
                      : field?.type === "number"
                        ? Number(e.target.value)
                        : e.target.value,
                })
              }
            />
          )}
        </label>
      )}
      <button className="btn" onClick={onRemove}>
        {t("practice.remove")}
      </button>
    </div>
  );
}
