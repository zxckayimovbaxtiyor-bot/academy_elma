import { useTranslation } from "react-i18next";
import { content } from "../api/admin";
import {
  inputTypes,
  type Definition,
  type Mode,
  type PComponent,
  type Policy,
  type PScreen,
  type Scenario,
} from "../api/practice";
import { pick, useLang } from "../lib/lang";
import { useApi } from "../lib/useApi";
import { Bilingual } from "./Renderer";
import {
  ConditionEditor,
  EventEditor,
  Toggle,
  ValueEditor,
} from "./StudioControls";
import { lt, settings, uid } from "./studioModel";
export function StudioLesson({
  def,
  update,
  selected,
  moduleId,
  lessonId,
  setModuleId,
  setLessonId,
  uploadCover,
}: {
  def: Definition;
  update: (v: Definition) => void;
  selected: Scenario | null;
  moduleId: number;
  lessonId: number | null;
  setModuleId: (v: number) => void;
  setLessonId: (v: number | null) => void;
  uploadCover: (file: File) => void;
}) {
  const { t } = useTranslation();
  const lang = useLang();
  const modules = useApi(() => content.modules(), []);
  const lessons = useApi(
    () => (moduleId ? content.lessons(moduleId) : Promise.resolve([])),
    [moduleId],
  );
  return (
    <div className="studio-panel studio-panel-content stack">
      <h2>
        <span className="studio-number">1</span>
        {t("studio.main_info")}
      </h2>
      <p className="studio-tip">{t("studio.info_help")}</p>
      <Bilingual
        label={t("practice.title_field")}
        value={def.title}
        onChange={(v) => update({ ...def, title: v })}
      />
      <Bilingual
        label={t("practice.description")}
        value={def.description}
        onChange={(v) => update({ ...def, description: v })}
      />
      <div className="studio-two">
        <label>
          {t("practice.module")}
          <select
            value={moduleId}
            disabled={!!selected}
            onChange={(e) => {
              setModuleId(Number(e.target.value));
              setLessonId(null);
            }}
          >
            <option value={0}>{t("studio.choose_module")}</option>
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
            onChange={(e) =>
              setLessonId(e.target.value ? Number(e.target.value) : null)
            }
          >
            <option value="">{t("studio.whole_module")}</option>
            {lessons.data?.map((l) => (
              <option key={l.id} value={l.id}>
                {pick(l, "title", lang)}
              </option>
            ))}
          </select>
        </label>
      </div>
      <h2>
        <span className="studio-number">2</span>
        {t("practice.roles")}
      </h2>
      <div className="studio-roles">
        {["learner", "branch_head", "methodologist", "admin"].map((role) => (
          <Toggle
            key={role}
            label={t(`roles.${role}`)}
            value={def.roles.includes(role)}
            change={(v) =>
              update({
                ...def,
                roles: v
                  ? [...def.roles, role]
                  : def.roles.filter((r) => r !== role),
              })
            }
          />
        ))}
      </div>
      <h2>{t("studio.settings")}</h2>
      <label>
        {t("studio.time_limit")}
        <input
          type="number"
          min={10}
          max={28800}
          value={def.metadata?.time_limit_s ?? ""}
          onChange={(e) =>
            update({
              ...def,
              metadata: {
                ...settings,
                ...def.metadata,
                time_limit_s: e.target.value ? Number(e.target.value) : null,
              },
            })
          }
        />
      </label>
      <label>
        {t("studio.cover")}
        <input
          type="file"
          accept="image/png,image/jpeg"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) uploadCover(file);
            e.target.value = "";
          }}
        />
      </label>
      {def.metadata?.cover_asset_id && (
        <div className="row">
          <img
            className="studio-cover"
            alt={def.title[lang]}
            src={`/api/v1/practice-assets/${def.metadata.cover_asset_id}`}
          />
          <button
            className="btn"
            onClick={() =>
              update({
                ...def,
                metadata: {
                  ...settings,
                  ...def.metadata,
                  cover_asset_id: null,
                },
              })
            }
          >
            {t("practice.remove")}
          </button>
        </div>
      )}
      <div className="studio-two">
        <label>
          {t("studio.difficulty")}
          <select
            value={def.metadata?.difficulty ?? "beginner"}
            onChange={(e) =>
              update({
                ...def,
                metadata: {
                  ...settings,
                  ...def.metadata,
                  difficulty: e.target.value as
                    "beginner" | "intermediate" | "advanced",
                },
              })
            }
          >
            {["beginner", "intermediate", "advanced"].map((v) => (
              <option key={v} value={v}>
                {t(`studio.difficulty_${v}`)}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t("studio.minutes")}
          <input
            type="number"
            min={1}
            max={480}
            value={def.metadata?.estimated_minutes ?? 10}
            onChange={(e) =>
              update({
                ...def,
                metadata: {
                  ...settings,
                  ...def.metadata,
                  estimated_minutes: Number(e.target.value),
                },
              })
            }
          />
        </label>
        <label>
          {t("studio.default_mode")}
          <select
            value={def.metadata?.default_mode ?? "guided"}
            onChange={(e) =>
              update({
                ...def,
                metadata: {
                  ...settings,
                  ...def.metadata,
                  default_mode: e.target.value as Mode,
                },
              })
            }
          >
            {["guided", "sandbox", "exam"].map((m) => (
              <option key={m} value={m}>
                {t(`practice.mode.${m}`)}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t("studio.scoring")}
          <select
            value={def.metadata?.scoring ?? "penalty"}
            onChange={(e) =>
              update({
                ...def,
                metadata: {
                  ...settings,
                  ...def.metadata,
                  scoring: e.target.value as "penalty" | "points",
                },
              })
            }
          >
            <option value="penalty">{t("studio.penalty")}</option>
            <option value="points">{t("studio.points")}</option>
          </select>
        </label>
        <label>
          {t("studio.max_points")}
          <input
            type="number"
            min={1}
            max={5000}
            value={def.metadata?.max_points ?? 100}
            onChange={(e) =>
              update({
                ...def,
                metadata: {
                  ...settings,
                  ...def.metadata,
                  max_points: Number(e.target.value),
                },
              })
            }
          />
        </label>
      </div>
      <details>
        <summary>{t("studio.variables")}</summary>
        <div className="stack">
          {def.variables?.map((v, i) => (
            <div className="studio-rule stack" key={v.id}>
              <Bilingual
                label={t("practice.label")}
                value={v.label}
                onChange={(label) =>
                  update({
                    ...def,
                    variables: def.variables!.map((old, n) =>
                      n === i ? { ...v, label } : old,
                    ),
                  })
                }
              />
              <ValueEditor
                label={t("studio.default_value")}
                value={v.value}
                allowType
                change={(value) =>
                  update({
                    ...def,
                    variables: def.variables!.map((old, n) =>
                      n === i ? { ...v, value } : old,
                    ),
                  })
                }
              />
              <code>{v.id}</code>
              <button
                className="studio-text-danger"
                onClick={() =>
                  update({
                    ...def,
                    variables: def.variables!.filter((_, n) => n !== i),
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
                variables: [
                  ...(def.variables ?? []),
                  {
                    id: uid("variable"),
                    label: lt("Переменная", "Oʻzgaruvchi"),
                    value: null,
                  },
                ],
              })
            }
          >
            {t("studio.add_variable")}
          </button>
        </div>
      </details>
    </div>
  );
}
export function StudioLogic({
  screen,
  def,
  fields,
  change,
}: {
  screen: PScreen;
  def: Definition;
  fields: PComponent[];
  change: (s: PScreen) => void;
}) {
  const { t } = useTranslation();
  const lang = useLang();
  const transitions = screen.transitions;
  const transition = (i: number, tr: (typeof transitions)[number]) =>
    change({
      ...screen,
      transitions: transitions.map((old, n) => (n === i ? tr : old)),
    });
  return (
    <>
      <h3>{t("studio.transitions")}</h3>
      {transitions.map((tr, i) => (
        <div className="studio-rule stack" key={i}>
          <label>
            {t("studio.source")}
            <select
              value={tr.action}
              onChange={(e) => transition(i, { ...tr, action: e.target.value })}
            >
              <option value="">—</option>
              {screen.components
                .filter((c) => ["button", "transition"].includes(c.type))
                .map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.label[lang]}
                  </option>
                ))}
            </select>
          </label>
          <label>
            {t("studio.target")}
            <select
              value={tr.target}
              onChange={(e) => transition(i, { ...tr, target: e.target.value })}
            >
              {def.screens.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.title[lang]}
                </option>
              ))}
            </select>
          </label>
          {tr.conditions.map((c, j) => (
            <ConditionEditor
              key={j}
              value={c}
              fields={fields}
              change={(v) =>
                transition(i, {
                  ...tr,
                  conditions: tr.conditions.map((old, k) =>
                    k === j ? v : old,
                  ),
                })
              }
              remove={() =>
                transition(i, {
                  ...tr,
                  conditions: tr.conditions.filter((_, k) => k !== j),
                })
              }
            />
          ))}
          <button
            className="btn"
            onClick={() =>
              transition(i, {
                ...tr,
                conditions: [
                  ...tr.conditions,
                  { field: fields[0]?.id || "", op: "present", value: null },
                ],
              })
            }
          >
            {t("studio.add_condition")}
          </button>
          <button
            className="studio-text-danger"
            onClick={() =>
              change({
                ...screen,
                transitions: transitions.filter((_, n) => n !== i),
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
          change({
            ...screen,
            transitions: [
              ...transitions,
              {
                action:
                  screen.components.find((c) => c.type === "button")?.id ?? "",
                target: def.completion[0],
                conditions: [],
              },
            ],
          })
        }
      >
        {t("studio.add_transition")}
      </button>
      <h3>{t("studio.checks")}</h3>
      {screen.rules.map((r, i) => (
        <div className="studio-rule stack" key={r.id}>
          <ConditionEditor
            value={r.condition}
            fields={fields}
            change={(v) =>
              change({
                ...screen,
                rules: screen.rules.map((old, n) =>
                  n === i ? { ...r, condition: v } : old,
                ),
              })
            }
            remove={() =>
              change({
                ...screen,
                rules: screen.rules.filter((_, n) => n !== i),
              })
            }
          />
          <Bilingual
            label={t("studio.error_message")}
            value={r.message}
            onChange={(v) =>
              change({
                ...screen,
                rules: screen.rules.map((old, n) =>
                  n === i ? { ...r, message: v } : old,
                ),
              })
            }
          />
          <label>
            {t("practice.points")}
            <input
              type="number"
              min={1}
              max={100}
              value={r.points}
              onChange={(e) =>
                change({
                  ...screen,
                  rules: screen.rules.map((old, n) =>
                    n === i ? { ...r, points: Number(e.target.value) } : old,
                  ),
                })
              }
            />
          </label>
        </div>
      ))}
      <button
        className="btn"
        onClick={() =>
          change({
            ...screen,
            rules: [
              ...screen.rules,
              {
                id: uid("rule"),
                condition: {
                  field: fields[0]?.id || "",
                  op: "present",
                  value: null,
                },
                message: lt("Проверьте данные", "Maʼlumotlarni tekshiring"),
                points: 10,
              },
            ],
          })
        }
      >
        {t("studio.add_check")}
      </button>
      <h3>{t("studio.events")}</h3>
      <EventEditor screen={screen} def={def} fields={fields} change={change} />
    </>
  );
}
export function StudioTasks({
  def,
  fields,
  update,
}: {
  def: Definition;
  fields: PComponent[];
  update: (d: Definition) => void;
}) {
  const { t } = useTranslation();
  const lang = useLang();
  return (
    <div className="studio-panel studio-panel-content stack">
      <h2>
        <span className="studio-number">3</span>
        {t("practice.tasks")}
      </h2>
      <p className="studio-tip">{t("studio.tasks_help")}</p>
      {def.tasks.map((task, i) => {
        const patch = (v: typeof task) =>
          update({
            ...def,
            tasks: def.tasks.map((old, n) => (n === i ? v : old)),
          });
        return (
          <details className="studio-rule" key={task.id} open>
            <summary>{t("studio.variant", { number: i + 1 })}</summary>
            <div className="stack">
              <Bilingual
                label={t("practice.description")}
                value={task.description}
                onChange={(v) => patch({ ...task, description: v })}
              />
              <h3>{t("studio.public_data")}</h3>
              <p className="small muted">{t("studio.public_help")}</p>
              {Object.entries(task.data ?? {}).map(([key, value]) => (
                <div className="studio-data-row" key={key}>
                  <code>{key}</code>
                  <ValueEditor
                    label={t("studio.default_value")}
                    value={value}
                    allowType
                    kind={typeof value === "number" ? "number" : "text"}
                    change={(v) =>
                      patch({ ...task, data: { ...task.data, [key]: v } })
                    }
                  />
                  <button
                    className="studio-text-danger"
                    onClick={() => {
                      const data = { ...task.data };
                      delete data[key];
                      patch({ ...task, data });
                    }}
                  >
                    {t("practice.remove")}
                  </button>
                </div>
              ))}
              <button
                className="btn"
                onClick={() =>
                  patch({ ...task, data: { ...task.data, [uid("data")]: "" } })
                }
              >
                {t("studio.add_data")}
              </button>
              <h3>{t("studio.private_answers")}</h3>
              <p className="small muted">{t("studio.private_help")}</p>
              {fields
                .filter(
                  (f) =>
                    inputTypes.includes(f.type) &&
                    def.screens.some((s) =>
                      s.components.some((c) => c.id === f.id),
                    ),
                )
                .map((f) => (
                  <div className="studio-two" key={f.id}>
                    <Toggle
                      label={f.label[lang]}
                      value={f.id in task.expected}
                      change={(v) => {
                        const expected = { ...task.expected };
                        if (v)
                          expected[f.id] =
                            f.type === "number"
                              ? 0
                              : ["checkbox", "switch"].includes(f.type)
                                ? false
                                : "";
                        else delete expected[f.id];
                        patch({ ...task, expected });
                      }}
                    />
                    {f.id in task.expected && (
                      <ValueEditor
                        label={t("practice.expected")}
                        kind={f.type}
                        value={task.expected[f.id]}
                        change={(v) =>
                          patch({
                            ...task,
                            expected: { ...task.expected, [f.id]: v },
                          })
                        }
                      />
                    )}
                  </div>
                ))}
              <button
                className="btn btn-danger"
                onClick={() =>
                  update({ ...def, tasks: def.tasks.filter((_, n) => n !== i) })
                }
              >
                {t("practice.remove")}
              </button>
            </div>
          </details>
        );
      })}
      <button
        className="btn"
        onClick={() =>
          update({
            ...def,
            tasks: [
              ...def.tasks,
              {
                id: uid("task"),
                description: lt(
                  "Выполните операцию по учебным данным",
                  "Oʻquv maʼlumotlari boʻyicha amaliyotni bajaring",
                ),
                expected: {},
                data: {},
              },
            ],
          })
        }
      >
        {t("studio.add_variant")}
      </button>
    </div>
  );
}
export function StudioPolicy({
  policy,
  change,
  save,
  busy,
}: {
  policy: Policy | null;
  change: (v: Policy) => void;
  save: () => void;
  busy: boolean;
}) {
  const { t } = useTranslation();
  return (
    <div className="studio-panel studio-panel-content stack">
      <h2>{t("studio.tab_policy")}</h2>
      {policy ? (
        <>
          <div className="studio-two">
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
              <Toggle
                key={k}
                label={t(`practice.policy.${k}`)}
                value={policy[k]}
                change={(v) => change({ ...policy, [k]: v })}
              />
            ))}
            {(["max_attempts", "pass_pct"] as const).map((k) => (
              <label key={k}>
                {t(`practice.policy.${k}`)}
                <input
                  type="number"
                  min={1}
                  max={k === "max_attempts" ? 20 : 100}
                  value={policy[k]}
                  onChange={(e) =>
                    change({ ...policy, [k]: Number(e.target.value) })
                  }
                />
              </label>
            ))}
            <label>
              {t("practice.policy.gate")}
              <select
                value={policy.gate}
                onChange={(e) =>
                  change({ ...policy, gate: e.target.value as Policy["gate"] })
                }
              >
                <option value="before_test">{t("practice.before_test")}</option>
                <option value="before_certificate">
                  {t("practice.before_certificate")}
                </option>
              </select>
            </label>
          </div>
          <button className="btn btn-primary" disabled={busy} onClick={save}>
            {t("practice.save_policy")}
          </button>
        </>
      ) : (
        <p>{t("studio.save_first")}</p>
      )}
    </div>
  );
}
