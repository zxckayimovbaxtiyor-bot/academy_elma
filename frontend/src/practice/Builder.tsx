import { useEffect, useRef, useState } from "react";
import { I18nextProvider, useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { content } from "../api/admin";
import {
  practice,
  componentTypes,
  inputTypes,
  type Command,
  type ComponentType,
  type Definition,
  type Mode,
  type PComponent,
  type PScreen,
  type Policy,
  type Preview,
  type Scenario,
  type Value,
} from "../api/practice";
import { ErrorLine, ErrorState, PageLoader } from "../components/Feedback";
import { Icon } from "../components/Icon";
import { useApi } from "../lib/useApi";
import { useLang } from "../lib/lang";
import { Bilingual, ScenarioScreen, PracticeComponentView } from "./Renderer";
import { ComponentInspector } from "./StudioControls";
import {
  StudioLesson,
  StudioLogic,
  StudioTasks,
  StudioPolicy,
} from "./StudioSections";
import {
  blank,
  component,
  copyScreen,
  editableValues,
  lt,
  reorder,
  removeScreen,
  settings,
  uid,
} from "./studioModel";
import { PracticeAnalytics } from "./Analytics";
import "../styles/studio.css";
type Recovery = {
  definition: Definition;
  scenario: number | null;
  revision: number;
  moduleId: number;
  lessonId: number | null;
};
export function PracticeBuilder() {
  const { t, i18n } = useTranslation();
  const lang = useLang();
  const { me } = useAuth();
  const list = useApi(() => practice.scenarios(), []);
  const modules = useApi(() => content.modules(), []);
  const [selected, setSelected] = useState<Scenario | null>(null);
  const [def, setDef] = useState<Definition | null>(null);
  const [screenId, setScreenId] = useState("start");
  const [componentId, setComponentId] = useState<string | null>(null);
  const [moduleId, setModuleId] = useState(0);
  const [lessonId, setLessonId] = useState<number | null>(null);
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState("");
  const [section, setSection] = useState("screens");
  const [library, setLibrary] = useState(false);
  const [search, setSearch] = useState("");
  const [templateKind, setTemplateKind] = useState("credit");
  const [flow, setFlow] = useState(false);
  const [inspector, setInspector] = useState("properties");
  const [undo, setUndo] = useState<Definition[]>([]);
  const [redo, setRedo] = useState<Definition[]>([]);
  const [recovery, setRecovery] = useState<Recovery | null>(null);
  const [issues, setIssues] = useState<
    { path: (string | number)[]; message: string; code?: string }[]
  >([]);
  const [checked, setChecked] = useState(false);
  const [previewClock, setPreviewClock] = useState(0);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [previewValues, setPreviewValues] = useState<Record<string, Value>>({});
  const [previewMode, setPreviewMode] = useState<Mode>("guided");
  const [previewTask, setPreviewTask] = useState("");
  const [previewLang, setPreviewLang] = useState(lang);
  const [reviewed, setReviewed] = useState(false);
  const [previewI18n] = useState(() => i18n.cloneInstance({ lng: lang }));
  const dialog = useRef<HTMLDialogElement>(null);
  const selectedComponent = useRef<HTMLDivElement>(null);
  const pendingAddedComponent = useRef<string | null>(null);
  useEffect(() => {
    if (
      pendingAddedComponent.current !== componentId ||
      !selectedComponent.current
    )
      return;
    selectedComponent.current.scrollIntoView({
      block: "nearest",
      behavior: "auto",
    });
    selectedComponent.current.focus({ preventScroll: true });
    pendingAddedComponent.current = null;
  }, [componentId]);
  const savingRef = useRef<Promise<Scenario | null> | null>(null);
  const current = useRef({ def, selected, moduleId, lessonId, policy, dirty });
  current.current = { def, selected, moduleId, lessonId, policy, dirty };
  const storageKey = `practice-studio:${me?.id}`;
  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(storageKey);
      if (raw) setRecovery(JSON.parse(raw));
    } catch {}
  }, [storageKey]);
  useEffect(() => {
    if (!dirty || !def) return;
    try {
      sessionStorage.setItem(
        storageKey,
        JSON.stringify({
          definition: def,
          scenario: selected?.id ?? null,
          revision: selected?.revision ?? 0,
          moduleId,
          lessonId,
        }),
      );
    } catch {}
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty, def, moduleId, lessonId, selected, storageKey]);
  useEffect(() => {
    void previewI18n.changeLanguage(previewLang);
  }, [previewLang, previewI18n]);
  const update = (d: Definition) => {
    if (def) setUndo((old) => [...old, def].slice(-50));
    setRedo([]);
    setDef(d);
    setDirty(true);
    setReviewed(false);
    setChecked(false);
    setNotice("");
  };
  const load = (s: Scenario) => {
    setSelected(s);
    setDef(structuredClone(s.definition));
    setScreenId(s.definition.start);
    setComponentId(
      s.definition.screens.find((screen) => screen.id === s.definition.start)
        ?.components[0]?.id ?? null,
    );
    setModuleId(s.module_id);
    setLessonId(s.lesson_id);
    setPolicy(s.policy);
    setDirty(false);
    setReviewed(false);
    setChecked(false);
    setUndo([]);
    setRedo([]);
    setIssues([]);
    setError(null);
    setNotice("");
  };
  const save = async (): Promise<Scenario | null> => {
    if (savingRef.current) return savingRef.current;
    const snapshot = current.current;
    if (!snapshot.def || !snapshot.moduleId) return null;
    const snapshotJSON = JSON.stringify(snapshot.def);
    setSaving(true);
    const promise = (async () => {
      const s = snapshot.selected
        ? await practice.save(
            snapshot.selected.id,
            snapshot.selected.revision,
            snapshot.def!,
          )
        : await practice.create(
            snapshot.moduleId,
            snapshot.lessonId,
            snapshot.def!,
          );
      current.current.selected = s;
      setSelected(s);
      setPolicy((p) => p ?? s.policy);
      if (JSON.stringify(current.current.def) === snapshotJSON) {
        current.current.dirty = false;
        setDirty(false);
        try {
          sessionStorage.removeItem(storageKey);
        } catch {}
      }
      list.reload();
      return s;
    })();
    savingRef.current = promise;
    try {
      return await promise;
    } finally {
      savingRef.current = null;
      setSaving(false);
    }
  };
  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => {
    if (!dirty || !def || !moduleId || saving || busy || error) return;
    const timer = window.setTimeout(() => {
      void save().catch(setError);
    }, 1600);
    return () => clearTimeout(timer);
  }, [dirty, def, moduleId, saving, busy, error]);
  const switchTo = (s: Scenario) =>
    run(async () => {
      if (s.id === current.current.selected?.id) return;
      if (current.current.dirty) {
        const result = await save();
        if (!result) throw Error(t("studio.choose_module"));
      }
      load(s);
    });
  const fresh = (template: boolean) =>
    run(async () => {
      if (current.current.dirty) {
        const result = await save();
        if (!result) throw Error(t("studio.choose_module"));
      }
      const d = template ? await practice.template(templateKind) : blank();
      setSelected(null);
      setDef(d);
      setScreenId(d.start);
      setComponentId(null);
      setPolicy(null);
      setLessonId(null);
      setUndo([]);
      setRedo([]);
      setDirty(true);
      setReviewed(false);
      setSection("lesson");
    });
  const check = async () => {
    if (!def) return false;
    const result = await practice.check(def);
    setIssues(result.issues);
    setChecked(true);
    setNotice(result.valid ? t("studio.valid") : t("studio.fix_issues"));
    return result.valid;
  };
  useEffect(() => {
    if (!preview || preview.finished) return;
    const timer = window.setInterval(() => {
      if (dialog.current?.open) setPreviewClock((c) => Math.min(28800, c + 1));
    }, 1000);
    return () => clearInterval(timer);
  }, [preview?.finished, !!preview]);
  const beginPreview = async (mode = previewMode, task = previewTask) => {
    if (!def) return;
    const p = await practice.preview(
      def,
      {
        screen: def.start,
        values: {},
        history: [],
        visited: [def.start],
        mistakes: [],
        task_id: task || def.tasks[0]?.id || null,
      },
      { request_id: crypto.randomUUID(), expected_revision: 0, kind: "save" },
      mode,
      true,
      policy?.pass_pct ?? 80,
    );
    setPreviewClock(0);
    setPreview(p);
    setPreviewValues(p.values);
  };
  const openPreview = () =>
    run(async () => {
      if (!(await check())) return;
      const s = dirty || !selected ? await save() : selected;
      if (!s) throw Error(t("studio.choose_module"));
      await practice.review(s.id, s.revision);
      setPreviewLang(lang);
      await beginPreview();
      setReviewed(true);
      dialog.current?.showModal();
    });
  const previewStep = (
    kind: Command["kind"],
    action?: string,
    event?: Command["event"],
    nextValues?: Record<string, Value>,
  ) =>
    run(async () => {
      if (!def || !preview) return;
      const p = await practice.preview(
        def,
        { ...preview.state, elapsed_s: previewClock },
        {
          request_id: crypto.randomUUID(),
          expected_revision: 0,
          kind,
          action,
          event,
          values: ["action", "event", "save", "finish", "hint"].includes(kind)
            ? editableValues(preview.screen, nextValues ?? previewValues)
            : {},
        },
        previewMode,
        false,
        policy?.pass_pct ?? 80,
      );
      setPreview(p);
      setPreviewValues(p.values);
    });
  useEffect(() => {
    if (
      dialog.current?.open &&
      preview &&
      !preview.finished &&
      def?.metadata?.time_limit_s &&
      previewClock >= def.metadata.time_limit_s &&
      !busy
    )
      void previewStep("finish");
  }, [previewClock, preview, busy]);
  const screen = def?.screens.find((s) => s.id === screenId) ?? def?.screens[0];
  const chosen = screen?.components.find((c) => c.id === componentId);
  const patchScreen = (s: PScreen) => {
    if (def)
      update({
        ...def,
        screens: def.screens.map((old) => (old.id === s.id ? s : old)),
      });
  };
  const fields = def
    ? [
        ...new Map(
          [
            ...def.screens.flatMap((s) =>
              s.components.filter((c) => inputTypes.includes(c.type)),
            ),
            ...(def.variables ?? []).map((v) => ({
              ...component(
                typeof v.value === "number"
                  ? "number"
                  : typeof v.value === "boolean"
                    ? "checkbox"
                    : "text",
                v.label,
              ),
              id: v.id,
            })),
          ].map((c) => [c.id, c]),
        ).values(),
      ]
    : [];
  const add = (type: ComponentType, index?: number) => {
    if (!screen) return;
    if (screen.components.length >= 50) {
      setNotice(t("studio.component_limit"));
      return;
    }
    const c = component(
      type,
      lt(
        i18n.getFixedT("ru")(`practice.component.${type}`),
        i18n.getFixedT("uz")(`practice.component.${type}`),
      ),
    );
    const items = [...screen.components];
    items.splice(index ?? items.length, 0, c);
    patchScreen({ ...screen, components: items });
    pendingAddedComponent.current = c.id;
    setComponentId(c.id);
    setInspector("properties");
    setNotice(t("studio.component_added", { name: c.label[lang] }));
  };
  const duplicateScreen = () => {
    if (!def || !screen) return;
    const c = copyScreen(screen);
    update({
      ...def,
      screens: [...def.screens, c],
      completion: def.completion.includes(screen.id)
        ? [...def.completion, c.id]
        : def.completion,
    });
    setScreenId(c.id);
    setComponentId(null);
  };
  const changeComponent = (c: PComponent) => {
    if (screen)
      patchScreen({
        ...screen,
        components: screen.components.map((old) => (old.id === c.id ? c : old)),
      });
  };
  const uploadCover = (file: File) =>
    run(async () => {
      const s = dirty || !selected ? await save() : selected;
      if (!s) throw Error(t("studio.choose_module"));
      const asset = await practice.upload(s.id, file);
      const d = current.current.def;
      if (d)
        update({
          ...d,
          metadata: { ...settings, ...d.metadata, cover_asset_id: asset.id },
        });
    });
  const upload = (file: File) =>
    run(async () => {
      if (!chosen) return;
      const s = dirty || !selected ? await save() : selected;
      if (!s) throw Error(t("studio.choose_module"));
      const asset =
        chosen.type === "video"
          ? await practice.uploadVideo(s.id, file)
          : await practice.upload(s.id, file);
      changeComponent({ ...chosen, asset_id: asset.id });
    });
  if ((list.loading && !list.data) || (modules.loading && !modules.data))
    return <PageLoader />;
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
  return (
    <div className="studio stack">
      <header className="studio-header">
        <div>
          <div className="studio-breadcrumb">
            <Link to="/admin/practice">{t("practice.title")}</Link>
            <span> / {t("studio.title")}</span>
          </div>
          <h1>{def?.title[lang] || t("studio.title")}</h1>
          <span className="muted small">
            {selected
              ? `${t(selected.archived ? "studio.archived" : selected.published ? "practice.published" : "practice.draft")} · ${t("practice.version", { number: selected.number })}`
              : t("studio.intro")}
          </span>
        </div>
        <div className="studio-actions">
          <button
            className="btn"
            disabled={!undo.length || busy}
            title={t("studio.undo")}
            onClick={() => {
              if (!def || !undo.length) return;
              setRedo((r) => [def, ...r]);
              setDef(undo.at(-1)!);
              setUndo(undo.slice(0, -1));
              setDirty(true);
              setReviewed(false);
            }}
          >
            ↶ <span>{t("studio.undo")}</span>
          </button>
          <button
            className="btn"
            disabled={!redo.length || busy}
            title={t("studio.redo")}
            onClick={() => {
              if (!def || !redo.length) return;
              setUndo((u) => [...u, def]);
              setDef(redo[0]);
              setRedo(redo.slice(1));
              setDirty(true);
              setReviewed(false);
            }}
          >
            ↷
          </button>
          <button
            className="btn"
            disabled={!def || busy}
            onClick={() =>
              run(async () => {
                await check();
              })
            }
          >
            <Icon name="check" size={16} />
            {t("studio.check")}
          </button>
          <button
            className="btn"
            disabled={!def || busy || !moduleId}
            onClick={openPreview}
          >
            <Icon name="play" size={16} />
            {t("practice.preview")}
          </button>
          <button
            className="btn"
            disabled={!def || busy || saving || !moduleId}
            onClick={() =>
              run(async () => {
                await save();
                setNotice(t("practice.saved"));
              })
            }
          >
            {saving ? t("practice.saving") : t("studio.save_draft")}
          </button>
          <button
            className="btn btn-primary"
            disabled={
              !selected ||
              busy ||
              dirty ||
              saving ||
              !reviewed ||
              selected.archived ||
              selected.published
            }
            onClick={() =>
              run(async () => {
                if (!selected) return;
                const s = await practice.publish(
                  selected.id,
                  selected.revision,
                );
                load(s);
                setNotice(t("practice.published"));
                list.reload();
              })
            }
          >
            <Icon name="certificate" size={16} />
            {t("practice.publish")}
          </button>
        </div>
      </header>
      <ErrorLine error={error} />
      {notice && (
        <div
          className={`notice ${checked && issues.length ? "notice-danger" : ""}`}
          role="status"
        >
          {notice}
        </div>
      )}
      {checked && issues.length > 0 && (
        <div className="notice notice-danger">
          <strong>{t("studio.fix_issues")}</strong>
          <ul>
            {issues.map((e, i) => (
              <li key={i}>
                {e.path.join(" → ")}:{" "}
                {t(`studio.issue.${e.code}`, {
                  defaultValue: t("studio.issue_invalid"),
                })}
              </li>
            ))}
          </ul>
        </div>
      )}
      {recovery && (
        <div className="notice spread">
          <span>{t("studio.recovery")}</span>
          <div className="row">
            <button
              className="btn"
              onClick={() => {
                const s = list.data?.find((s) => s.id === recovery.scenario);
                if (s && s.revision !== recovery.revision) {
                  setError(Error(t("studio.recovery_conflict")));
                  return;
                }
                if (s) load(s);
                setDef(recovery.definition);
                setModuleId(recovery.moduleId);
                setLessonId(recovery.lessonId);
                setScreenId(recovery.definition.start);
                setDirty(true);
                setRecovery(null);
              }}
            >
              {t("studio.restore")}
            </button>
            <button
              className="btn"
              onClick={() => {
                sessionStorage.removeItem(storageKey);
                setRecovery(null);
              }}
            >
              {t("studio.dismiss")}
            </button>
          </div>
        </div>
      )}
      <fieldset className="studio-body" disabled={busy}>
        <aside className="studio-library studio-panel">
          <div className="studio-panel-head">
            <strong>
              {t(library ? "studio.library" : "practice.scenarios")}
            </strong>
            <button
              className="studio-icon"
              title={t(library ? "practice.scenarios" : "studio.library")}
              onClick={() => setLibrary(!library)}
            >
              <Icon name={library ? "content" : "plus"} size={18} />
            </button>
          </div>
          <div className="studio-panel-content stack">
            <label>
              {t("studio.template_type")}
              <select
                value={templateKind}
                onChange={(e) => setTemplateKind(e.target.value)}
              >
                {["credit", "client", "transfer", "deposit"].map((kind) => (
                  <option value={kind} key={kind}>
                    {t(`studio.template_${kind}`)}
                  </option>
                ))}
              </select>
            </label>
            <div className="studio-two">
              <button
                className="btn btn-sm"
                disabled={busy}
                onClick={() => fresh(false)}
              >
                {t("practice.new")}
              </button>
              <button
                className="btn btn-sm"
                disabled={busy}
                onClick={() => fresh(true)}
              >
                {t("studio.template")}
              </button>
            </div>
            {library ? (
              <>
                <label className="studio-search">
                  <Icon name="search" size={16} />
                  <input
                    aria-label={t("studio.search")}
                    placeholder={t("studio.search")}
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                  />
                </label>
                <p className="muted small">{t("studio.drag_help")}</p>
                <div className="studio-library-grid">
                  {componentTypes
                    .filter((type) =>
                      t(`practice.component.${type}`)
                        .toLowerCase()
                        .includes(search.toLowerCase()),
                    )
                    .map((type) => (
                      <button
                        key={type}
                        className="studio-tool"
                        draggable
                        disabled={!screen}
                        onDragStart={(e) =>
                          e.dataTransfer.setData(
                            "application/practice-component",
                            type,
                          )
                        }
                        onClick={() => add(type)}
                      >
                        <span className="studio-tool-icon">
                          {inputTypes.includes(type)
                            ? "T"
                            : type === "button"
                              ? "➜"
                              : type === "image"
                                ? "▧"
                                : "▤"}
                        </span>
                        <span>{t(`practice.component.${type}`)}</span>
                      </button>
                    ))}
                </div>
              </>
            ) : (
              <>
                <div className="studio-lesson-list">
                  {list.data?.map((s) => (
                    <button
                      key={s.id}
                      disabled={busy}
                      className={`studio-lesson ${selected?.id === s.id ? "active" : ""}`}
                      onClick={() => switchTo(s)}
                    >
                      <span className="studio-lesson-mark">
                        <Icon name="content" size={17} />
                      </span>
                      <span>
                        <strong>
                          {s.definition.title[lang] || t("studio.untitled")}
                        </strong>
                        <small>
                          {t(
                            s.archived
                              ? "studio.archived"
                              : s.published
                                ? "practice.published"
                                : "practice.draft",
                          )}{" "}
                          · v{s.number}
                        </small>
                      </span>
                    </button>
                  ))}
                </div>
                {selected && (
                  <div className="stack">
                    <button
                      className="btn btn-sm"
                      disabled={busy || dirty}
                      onClick={() =>
                        run(async () => {
                          const s = await practice.copy(selected.id);
                          load(s);
                          list.reload();
                        })
                      }
                    >
                      {t("studio.copy_lesson")}
                    </button>
                    <button
                      className="btn btn-sm"
                      disabled={busy || dirty}
                      onClick={() =>
                        run(async () => {
                          const s = await practice.archive(
                            selected.id,
                            !selected.archived,
                          );
                          load(s);
                          list.reload();
                        })
                      }
                    >
                      {t(
                        selected.archived
                          ? "studio.unarchive"
                          : "studio.archive",
                      )}
                    </button>
                  </div>
                )}
              </>
            )}
            <div className="studio-help">
              <strong>{t("studio.safe_title")}</strong>
              <p>{t("studio.safe_help")}</p>
            </div>
          </div>
        </aside>
        {!def ? (
          <div className="studio-empty studio-panel">
            <Icon name="content" size={42} />
            <h2>{t("studio.welcome")}</h2>
            <p>{t("studio.welcome_help")}</p>
            <button className="btn btn-primary" onClick={() => fresh(true)}>
              {t("studio.from_template")}
            </button>
          </div>
        ) : (
          <div className="studio-editor">
            <nav className="studio-tabs" aria-label={t("studio.sections")}>
              {["lesson", "screens", "tasks", "policy", "analytics"].map(
                (name) => (
                  <button
                    className={section === name ? "active" : ""}
                    key={name}
                    onClick={() => setSection(name)}
                  >
                    {t(`studio.tab_${name}`)}
                  </button>
                ),
              )}
              <span role="status" className="studio-save-status">
                {t(
                  saving
                    ? "practice.saving"
                    : dirty
                      ? "practice.unsaved"
                      : "practice.saved",
                )}
              </span>
            </nav>
            {section === "lesson" && (
              <StudioLesson
                def={def}
                update={update}
                selected={selected}
                moduleId={moduleId}
                lessonId={lessonId}
                setModuleId={setModuleId}
                setLessonId={setLessonId}
                uploadCover={uploadCover}
              />
            )}
            {section === "screens" && screen && (
              <>
                <section className="studio-panel">
                  <div className="studio-panel-head">
                    <h2>
                      <span className="studio-number">3</span>
                      {t("practice.screens")}
                    </h2>
                    <div className="row">
                      <button
                        className="btn btn-sm"
                        aria-pressed={flow}
                        onClick={() => setFlow(!flow)}
                      >
                        {t("studio.flow")}
                      </button>
                      <button
                        className="btn btn-sm"
                        onClick={() => {
                          const s: PScreen = {
                            id: uid("screen"),
                            title: lt("Новый экран", "Yangi ekran"),
                            description: lt(
                              "Выполните шаг",
                              "Bosqichni bajaring",
                            ),
                            components: [],
                            transitions: [],
                            rules: [],
                            events: [],
                          };
                          update({ ...def, screens: [...def.screens, s] });
                          setScreenId(s.id);
                          setComponentId(null);
                        }}
                      >
                        <Icon name="plus" size={16} />
                        {t("practice.add_screen")}
                      </button>
                    </div>
                  </div>
                  <div className="studio-filmstrip">
                    {def.screens.map((s, i) => (
                      <div
                        key={s.id}
                        className={`studio-screen-thumb ${s.id === screen.id ? "active" : ""}`}
                        draggable
                        onDragStart={(e) =>
                          e.dataTransfer.setData(
                            "application/practice-screen",
                            s.id,
                          )
                        }
                        onDragOver={(e) => e.preventDefault()}
                        onDrop={(e) => {
                          e.preventDefault();
                          const from = def.screens.findIndex(
                            (s) =>
                              s.id ===
                              e.dataTransfer.getData(
                                "application/practice-screen",
                              ),
                          );
                          update({
                            ...def,
                            screens: reorder(def.screens, from, i),
                          });
                        }}
                      >
                        <button
                          onClick={() => {
                            setScreenId(s.id);
                            setComponentId(null);
                          }}
                        >
                          <span className="studio-mini-screen">
                            <span />
                            <i />
                            <i />
                            <i />
                          </span>
                          <strong>
                            {i + 1}. {s.title[lang]}
                          </strong>
                          <small>
                            {s.id === def.start
                              ? t("studio.start")
                              : def.completion.includes(s.id)
                                ? t("studio.terminal")
                                : t("studio.step")}
                          </small>
                        </button>
                        <div className="studio-thumb-actions">
                          <button
                            title={t("studio.move_left")}
                            disabled={i === 0}
                            onClick={() =>
                              update({
                                ...def,
                                screens: reorder(def.screens, i, i - 1),
                              })
                            }
                          >
                            ←
                          </button>
                          <button
                            title={t("studio.move_right")}
                            disabled={i === def.screens.length - 1}
                            onClick={() =>
                              update({
                                ...def,
                                screens: reorder(def.screens, i, i + 1),
                              })
                            }
                          >
                            →
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                  {flow && (
                    <div className="studio-flow" aria-label={t("studio.flow")}>
                      {def.screens.map((s) => (
                        <div key={s.id}>
                          <button
                            className="btn"
                            onClick={() => setScreenId(s.id)}
                          >
                            {s.title[lang]}
                          </button>
                          {[
                            ...new Set([
                              ...s.transitions.map((tr) => tr.target),
                              ...(s.events ?? []).flatMap((e) =>
                                [...e.actions, ...e.otherwise]
                                  .filter((a) => a.type === "goto")
                                  .map((a) => a.target!),
                              ),
                            ]),
                          ].map((target) => (
                            <span key={target}>
                              {" "}
                              →{" "}
                              {def.screens.find((s) => s.id === target)?.title[
                                lang
                              ] ?? "?"}
                            </span>
                          ))}
                        </div>
                      ))}
                    </div>
                  )}
                </section>
                <div className="studio-workbench">
                  <section className="studio-panel studio-canvas-panel">
                    <div className="studio-panel-head">
                      <h2>
                        <span className="studio-number">4</span>
                        {screen.title[lang]}
                      </h2>
                      <button
                        className="btn btn-sm"
                        onClick={() => setLibrary(true)}
                      >
                        <Icon name="plus" size={16} />
                        {t("studio.add_component")}
                      </button>
                    </div>
                    <div
                      className="studio-canvas"
                      onDragOver={(e) => e.preventDefault()}
                      onDrop={(e) => {
                        e.preventDefault();
                        const type = e.dataTransfer.getData(
                          "application/practice-component",
                        ) as ComponentType;
                        if (componentTypes.includes(type)) add(type);
                      }}
                    >
                      <p className="muted small">{t("studio.canvas_help")}</p>
                      {screen.components.length === 0 && (
                        <div
                          className="studio-dropzone"
                          onClick={() => setLibrary(true)}
                        >
                          {t("studio.drop_here")}
                        </div>
                      )}
                      {screen.components.map((c, i) => (
                        <div
                          key={c.id}
                          ref={
                            c.id === componentId ? selectedComponent : undefined
                          }
                          className={`studio-component ${chosen?.id === c.id ? "selected" : ""}`}
                          style={{
                            gridColumn:
                              c.width === "half" ? "span 1" : "1 / -1",
                          }}
                          draggable
                          onDragStart={(e) => {
                            e.stopPropagation();
                            e.dataTransfer.setData(
                              "application/practice-order",
                              String(i),
                            );
                          }}
                          onDragOver={(e) => e.preventDefault()}
                          onDrop={(e) => {
                            const raw = e.dataTransfer.getData(
                              "application/practice-order",
                            );
                            if (raw !== "") {
                              e.preventDefault();
                              e.stopPropagation();
                              patchScreen({
                                ...screen,
                                components: reorder(
                                  screen.components,
                                  Number(raw),
                                  i,
                                ),
                              });
                            }
                          }}
                          onClick={() => setComponentId(c.id)}
                          onKeyDown={(e) => {
                            if (
                              e.target === e.currentTarget &&
                              ["Enter", " "].includes(e.key)
                            ) {
                              e.preventDefault();
                              setComponentId(c.id);
                            }
                          }}
                          role="button"
                          tabIndex={0}
                          aria-label={`${t("studio.select_component")}: ${c.label[lang]}`}
                        >
                          <div className="studio-component-label">
                            <span>⠿ {t(`practice.component.${c.type}`)}</span>
                            {c.visible === false && (
                              <span>{t("studio.hidden")}</span>
                            )}
                          </div>
                          <div
                            className="studio-component-preview"
                            aria-hidden="true"
                          >
                            <PracticeComponentView
                              component={c}
                              value={c.default_value ?? null}
                              values={{}}
                              change={() => setComponentId(c.id)}
                              action={() => setComponentId(c.id)}
                              disabled
                              guided
                              invalid={false}
                            />
                          </div>
                          <div className="studio-component-actions">
                            <button
                              aria-label={t("studio.move_up")}
                              disabled={i === 0}
                              onClick={(e) => {
                                e.stopPropagation();
                                patchScreen({
                                  ...screen,
                                  components: reorder(
                                    screen.components,
                                    i,
                                    i - 1,
                                  ),
                                });
                              }}
                            >
                              ↑
                            </button>
                            <button
                              aria-label={t("studio.move_down")}
                              disabled={i === screen.components.length - 1}
                              onClick={(e) => {
                                e.stopPropagation();
                                patchScreen({
                                  ...screen,
                                  components: reorder(
                                    screen.components,
                                    i,
                                    i + 1,
                                  ),
                                });
                              }}
                            >
                              ↓
                            </button>
                            <button
                              aria-label={t("studio.copy_component")}
                              onClick={(e) => {
                                e.stopPropagation();
                                const copy = {
                                  ...structuredClone(c),
                                  id: uid("field"),
                                };
                                patchScreen({
                                  ...screen,
                                  components: [
                                    ...screen.components.slice(0, i + 1),
                                    copy,
                                    ...screen.components.slice(i + 1),
                                  ],
                                });
                                setComponentId(copy.id);
                              }}
                            >
                              ⧉
                            </button>
                            <button
                              aria-label={t("practice.remove")}
                              onClick={(e) => {
                                e.stopPropagation();
                                patchScreen({
                                  ...screen,
                                  components: screen.components.filter(
                                    (x) => x.id !== c.id,
                                  ),
                                  transitions: screen.transitions.filter(
                                    (tr) => tr.action !== c.id,
                                  ),
                                  events: screen.events?.filter(
                                    (event) => event.component_id !== c.id,
                                  ),
                                });
                                setComponentId(null);
                              }}
                            >
                              <Icon name="trash" size={14} />
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                    <div className="studio-canvas-foot">
                      <span className="chip">{t("practice.synthetic")}</span>
                      <button className="back-link" onClick={openPreview}>
                        <Icon name="play" size={16} />
                        {t("studio.try_lesson")}
                      </button>
                    </div>
                  </section>
                  <aside className="studio-panel studio-inspector">
                    <div className="studio-panel-head">
                      <h2>
                        <span className="studio-number">5</span>
                        {t("studio.inspector")}
                      </h2>
                    </div>
                    <nav className="studio-tabs">
                      {["properties", "screen", "logic"].map((v) => (
                        <button
                          key={v}
                          className={inspector === v ? "active" : ""}
                          onClick={() => setInspector(v)}
                        >
                          {t(`studio.inspector_${v}`)}
                        </button>
                      ))}
                    </nav>
                    <div className="studio-panel-content stack">
                      {inspector === "properties" &&
                        (chosen ? (
                          <ComponentInspector
                            key={chosen.id}
                            value={chosen}
                            def={def}
                            fields={fields}
                            change={changeComponent}
                            upload={upload}
                          />
                        ) : (
                          <div className="studio-empty">
                            <Icon name="content" size={32} />
                            <p>{t("studio.select_help")}</p>
                          </div>
                        ))}
                      {inspector === "screen" && (
                        <>
                          <Bilingual
                            label={t("studio.screen_name")}
                            value={screen.title}
                            onChange={(v) =>
                              patchScreen({ ...screen, title: v })
                            }
                          />
                          <Bilingual
                            label={t("practice.description")}
                            value={screen.description}
                            onChange={(v) =>
                              patchScreen({ ...screen, description: v })
                            }
                          />
                          <label className="studio-toggle">
                            <input
                              type="checkbox"
                              checked={def.start === screen.id}
                              onChange={(e) => {
                                if (e.target.checked)
                                  update({
                                    ...def,
                                    start: screen.id,
                                    completion: def.completion.filter(
                                      (id) => id !== screen.id,
                                    ),
                                  });
                              }}
                            />
                            {t("studio.start")}
                          </label>
                          <label className="studio-toggle">
                            <input
                              type="checkbox"
                              checked={def.completion.includes(screen.id)}
                              onChange={(e) =>
                                update({
                                  ...def,
                                  completion: e.target.checked
                                    ? [...def.completion, screen.id]
                                    : def.completion.filter(
                                        (id) => id !== screen.id,
                                      ),
                                })
                              }
                            />
                            {t("studio.terminal")}
                          </label>
                          <button className="btn" onClick={duplicateScreen}>
                            {t("studio.copy_screen")}
                          </button>
                          <button
                            className="btn btn-danger"
                            disabled={def.screens.length <= 2}
                            onClick={() => {
                              const d = removeScreen(def, screen.id);
                              update(d);
                              setScreenId(d.start);
                              setComponentId(null);
                            }}
                          >
                            {t("practice.delete_screen")}
                          </button>
                          <small className="muted">ID: {screen.id}</small>
                        </>
                      )}
                      {inspector === "logic" && (
                        <StudioLogic
                          screen={screen}
                          def={def}
                          fields={fields}
                          change={patchScreen}
                        />
                      )}
                    </div>
                  </aside>
                </div>
              </>
            )}
            {section === "tasks" && (
              <StudioTasks def={def} fields={fields} update={update} />
            )}
            {section === "policy" && (
              <StudioPolicy
                policy={policy}
                change={setPolicy}
                save={() =>
                  run(async () => {
                    if (policy && selected) {
                      await practice.assign(selected.id, policy);
                      setNotice(t("practice.saved"));
                    }
                  })
                }
                busy={busy}
              />
            )}
            {section === "analytics" && <PracticeAnalytics />}
          </div>
        )}
      </fieldset>
      <dialog
        ref={dialog}
        className="practice-dialog studio-preview"
        aria-label={t("practice.preview")}
      >
        <div className="studio-panel-head">
          <div>
            <h2>{t("studio.student_preview")}</h2>
            <small>{t("practice.preview_notice")}</small>
          </div>
          <button className="btn" onClick={() => dialog.current?.close()}>
            {t("practice.close")}
          </button>
        </div>
        <div className="studio-preview-tools">
          <label>
            {t("studio.language")}
            <select
              value={previewLang}
              onChange={(e) => setPreviewLang(e.target.value as "ru" | "uz")}
            >
              <option value="ru">RU</option>
              <option value="uz">UZ</option>
            </select>
          </label>
          <label>
            {t("studio.default_mode")}
            <select
              value={previewMode}
              disabled={busy}
              onChange={(e) => {
                const mode = e.target.value as Mode;
                setPreviewMode(mode);
                void run(() => beginPreview(mode));
              }}
            >
              {["guided", "sandbox", "exam"].map((m) => (
                <option key={m} value={m}>
                  {t(`practice.mode.${m}`)}
                </option>
              ))}
            </select>
          </label>
          <label>
            {t("practice.tasks")}
            <select
              disabled={busy}
              value={previewTask}
              onChange={(e) => {
                setPreviewTask(e.target.value);
                void run(() => beginPreview(previewMode, e.target.value));
              }}
            >
              <option value="">{t("studio.first_variant")}</option>
              {def?.tasks.map((task, i) => (
                <option key={task.id} value={task.id}>
                  {t("studio.variant", { number: i + 1 })}
                </option>
              ))}
            </select>
          </label>
          <button
            className="btn"
            disabled={busy}
            onClick={() => run(() => beginPreview())}
          >
            {t("practice.reset")}
          </button>
        </div>
        <ErrorLine error={error} />
        {preview && (
          <I18nextProvider i18n={previewI18n}>
            <div className="studio-panel-content stack">
              {preview.task && (
                <div className="notice">{preview.task[previewLang]}</div>
              )}
              {preview.messages?.map((m, i) => (
                <div className="notice" key={i}>
                  {m.message[previewLang]}
                </div>
              ))}
              <ScenarioScreen
                summary={preview.summary}
                elapsed={previewClock}
                screen={preview.screen}
                values={previewValues}
                setValues={setPreviewValues}
                onAction={(id) => previewStep("action", id)}
                onEvent={(id, event, v) => previewStep("event", id, event, v)}
                onHint={(id) => previewStep("hint", id)}
                guided={previewMode === "guided"}
                disabled={busy || preview.finished}
                feedback={preview.feedback}
              />
              <div className="row">
                <button
                  className="back-link"
                  disabled={
                    busy || previewMode === "exam" || !preview.history.length
                  }
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
              {preview.result && (
                <p className="notice">
                  {preview.result.score_pct}% · {preview.result.duration_s}{" "}
                  {t("studio.seconds")}
                </p>
              )}
              {preview.finished && (
                <div className="notice" role="status">
                  {t("practice.preview_finished")}
                </div>
              )}
            </div>
          </I18nextProvider>
        )}
      </dialog>
    </div>
  );
}
