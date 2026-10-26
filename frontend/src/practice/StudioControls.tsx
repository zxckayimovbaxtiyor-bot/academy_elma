import { useTranslation } from "react-i18next";
import { useLang } from "../lib/lang";
import {
  componentTypes,
  type Condition,
  type Definition,
  type Effect,
  type EventBinding,
  type PComponent,
  type PScreen,
  type Value,
} from "../api/practice";
import { Bilingual } from "./Renderer";
import { lt, uid } from "./studioModel";
export function Toggle({
  label,
  value,
  change,
}: {
  label: string;
  value: boolean;
  change: (v: boolean) => void;
}) {
  return (
    <label className="studio-toggle">
      <input
        type="checkbox"
        checked={value}
        onChange={(e) => change(e.target.checked)}
      />
      <span>{label}</span>
    </label>
  );
}
export function ValueEditor({
  label,
  value,
  change,
  kind = "text",
  allowType = false,
}: {
  label: string;
  value: Value;
  change: (v: Value) => void;
  kind?: string;
  allowType?: boolean;
}) {
  const { t } = useTranslation();
  if (allowType)
    kind =
      typeof value === "number"
        ? "number"
        : typeof value === "boolean"
          ? "checkbox"
          : "text";
  return (
    <>
      {allowType && (
        <label>
          {t("studio.value_type")}
          <select
            value={kind}
            onChange={(e) =>
              change(
                e.target.value === "number"
                  ? 0
                  : e.target.value === "checkbox"
                    ? false
                    : "",
              )
            }
          >
            {["text", "number", "checkbox"].map((type) => (
              <option value={type} key={type}>
                {t(`practice.component.${type}`)}
              </option>
            ))}
          </select>
        </label>
      )}
      <label>
        {label}
        {["checkbox", "switch"].includes(kind) ? (
          <select
            value={String(value)}
            onChange={(e) =>
              change(
                e.target.value === "null" ? null : e.target.value === "true",
              )
            }
          >
            <option value="null">—</option>
            <option value="true">{t("practice.yes")}</option>
            <option value="false">{t("practice.no")}</option>
          </select>
        ) : (
          <input
            type={
              kind === "number" ? "number" : kind === "date" ? "date" : "text"
            }
            value={String(value ?? "")}
            onChange={(e) =>
              change(
                e.target.value === ""
                  ? null
                  : kind === "number"
                    ? Number(e.target.value)
                    : e.target.value,
              )
            }
          />
        )}
      </label>
    </>
  );
}
export function ConditionEditor({
  value,
  fields,
  change,
  remove,
  depth = 0,
}: {
  value: Condition;
  fields: PComponent[];
  change: (v: Condition) => void;
  remove: () => void;
  depth?: number;
}) {
  const { t } = useTranslation();
  const lang = useLang();
  const field = fields.find((f) => f.id === value.field);
  const group = ["all", "any"].includes(value.op);
  return (
    <div className="studio-condition stack">
      <div className="studio-two">
        <label>
          {t("practice.operator")}
          <select
            value={value.op}
            onChange={(e) =>
              change({
                field:
                  e.target.value === "all" || e.target.value === "any"
                    ? ""
                    : value.field || fields[0]?.id || "",
                op: e.target.value as Condition["op"],
                value: null,
                children: ["all", "any"].includes(e.target.value)
                  ? [{ field: fields[0]?.id || "", op: "present", value: null }]
                  : [],
              })
            }
          >
            {[
              "present",
              "empty",
              "eq",
              "ne",
              "gt",
              "lt",
              "gte",
              "lte",
              "contains",
              "in",
              ...(depth < 3 ? ["all", "any"] : []),
            ].map((op) => (
              <option key={op} value={op}>
                {t(`practice.operator_label.${op}`)}
              </option>
            ))}
          </select>
        </label>
        {!group && (
          <label>
            {t("practice.field_label")}
            <select
              value={value.field}
              onChange={(e) =>
                change({ ...value, field: e.target.value, value: null })
              }
            >
              <option value="">—</option>
              {fields.map((f) => (
                <option value={f.id} key={f.id}>
                  {f.label[lang] || f.id}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      {group ? (
        <>
          <div>
            {value.children?.map((c, i) => (
              <ConditionEditor
                key={i}
                value={c}
                fields={fields}
                depth={depth + 1}
                change={(v) =>
                  change({
                    ...value,
                    children: value.children!.map((old, n) =>
                      n === i ? v : old,
                    ),
                  })
                }
                remove={() =>
                  change({
                    ...value,
                    children: value.children!.filter((_, n) => n !== i),
                  })
                }
              />
            ))}
          </div>
          <button
            className="btn btn-sm"
            onClick={() =>
              change({
                ...value,
                children: [
                  ...(value.children ?? []),
                  { field: fields[0]?.id || "", op: "present", value: null },
                ],
              })
            }
          >
            {t("studio.add_condition")}
          </button>
        </>
      ) : (
        !["present", "empty"].includes(value.op) && (
          <>
            <Toggle
              label={t("practice.task_value")}
              value={value.task_value ?? false}
              change={(v) => change({ ...value, task_value: v })}
            />
            {!value.task_value &&
              (value.op === "in" ? (
                <label>
                  {t("practice.expected")}
                  <input
                    value={
                      Array.isArray(value.value) ? value.value.join(",") : ""
                    }
                    onChange={(e) =>
                      change({
                        ...value,
                        value: e.target.value.split(",").map((s) => s.trim()),
                      })
                    }
                  />
                </label>
              ) : (
                <ValueEditor
                  label={t("practice.expected")}
                  value={Array.isArray(value.value) ? null : value.value}
                  kind={field?.type}
                  change={(v) => change({ ...value, value: v })}
                />
              ))}
          </>
        )
      )}
      <button className="studio-text-danger" onClick={remove}>
        {t("practice.remove")}
      </button>
    </div>
  );
}
export function EffectEditor({
  value,
  def,
  change,
  remove,
}: {
  value: Effect;
  def: Definition;
  change: (v: Effect) => void;
  remove: () => void;
}) {
  const { t } = useTranslation();
  const lang = useLang();
  return (
    <div className="studio-condition stack">
      <label>
        {t("studio.effect")}
        <select
          value={value.type}
          onChange={(e) =>
            change({
              type: e.target.value as Effect["type"],
              points: 10,
              ...(["message", "hint", "error"].includes(e.target.value)
                ? { message: lt() }
                : {}),
            })
          }
        >
          {[
            "goto",
            "message",
            "hint",
            "show",
            "hide",
            "set",
            "check",
            "award",
            "error",
            "finish",
          ].map((a) => (
            <option value={a} key={a}>
              {t(`studio.effect_${a}`)}
            </option>
          ))}
        </select>
      </label>
      {["goto", "show", "hide"].includes(value.type) && (
        <label>
          {t("studio.target")}
          <select
            value={value.target ?? ""}
            onChange={(e) => change({ ...value, target: e.target.value })}
          >
            <option value="">—</option>
            {(value.type === "goto"
              ? def.screens.map((s) => ({ id: s.id, label: s.title }))
              : def.screens.flatMap((s) => s.components)
            ).map((c) => (
              <option value={c.id} key={c.id}>
                {c.label[lang]}
              </option>
            ))}
          </select>
        </label>
      )}
      {["message", "hint", "error"].includes(value.type) && (
        <Bilingual
          label={t("studio.message")}
          value={value.message ?? lt()}
          onChange={(v) => change({ ...value, message: v })}
        />
      )}
      {value.type === "set" && (
        <>
          <label>
            {t("studio.variable")}
            <select
              value={value.field ?? ""}
              onChange={(e) => change({ ...value, field: e.target.value })}
            >
              <option value="">—</option>
              {def.variables?.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.label[lang]}
                </option>
              ))}
            </select>
          </label>
          <ValueEditor
            label={t("practice.expected")}
            value={value.value ?? null}
            allowType
            change={(v) => change({ ...value, value: v })}
          />
          <label>
            {t("studio.copy_value")}
            <select
              value={value.value_field ?? ""}
              onChange={(e) =>
                change({ ...value, value_field: e.target.value || null })
              }
            >
              <option value="">—</option>
              {def.screens
                .flatMap((s) => s.components)
                .map((c) => (
                  <option key={`${c.id}-${c.label.ru}`} value={c.id}>
                    {c.label[lang]}
                  </option>
                ))}
            </select>
          </label>
        </>
      )}
      {["award", "error"].includes(value.type) && (
        <label>
          {t("practice.points")}
          <input
            type="number"
            min={0}
            max={100}
            value={value.points ?? 10}
            onChange={(e) =>
              change({ ...value, points: Number(e.target.value) })
            }
          />
        </label>
      )}
      <button className="studio-text-danger" onClick={remove}>
        {t("practice.remove")}
      </button>
    </div>
  );
}
export function EventEditor({
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
  const events = screen.events ?? [];
  const patch = (i: number, e: EventBinding) =>
    change({ ...screen, events: events.map((old, n) => (n === i ? e : old)) });
  return (
    <div className="stack">
      {events.map((event, i) => (
        <details className="studio-rule" key={event.id} open>
          <summary>
            {t(`studio.event_${event.on}`)} ·{" "}
            {screen.components.find((c) => c.id === event.component_id)?.label[
              lang
            ] || screen.title[lang]}
          </summary>
          <div className="stack">
            <label>
              {t("studio.event")}
              <select
                value={event.on}
                onChange={(e) =>
                  patch(i, {
                    ...event,
                    on: e.target.value as EventBinding["on"],
                  })
                }
              >
                {[
                  "click",
                  "change",
                  "submit",
                  "enter",
                  "success",
                  "failure",
                ].map((e) => (
                  <option key={e} value={e}>
                    {t(`studio.event_${e}`)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {t("studio.source")}
              <select
                value={event.component_id ?? ""}
                onChange={(e) =>
                  patch(i, { ...event, component_id: e.target.value || null })
                }
              >
                <option value="">{t("studio.whole_screen")}</option>
                {screen.components.map((c) => (
                  <option value={c.id} key={c.id}>
                    {c.label[lang]}
                  </option>
                ))}
              </select>
            </label>
            <strong>{t("studio.conditions")}</strong>
            {event.conditions.map((c, n) => (
              <ConditionEditor
                key={n}
                value={c}
                fields={fields}
                change={(v) =>
                  patch(i, {
                    ...event,
                    conditions: event.conditions.map((old, j) =>
                      n === j ? v : old,
                    ),
                  })
                }
                remove={() =>
                  patch(i, {
                    ...event,
                    conditions: event.conditions.filter((_, j) => n !== j),
                  })
                }
              />
            ))}
            <button
              className="btn"
              onClick={() =>
                patch(i, {
                  ...event,
                  conditions: [
                    ...event.conditions,
                    { field: fields[0]?.id || "", op: "present", value: null },
                  ],
                })
              }
            >
              {t("studio.add_condition")}
            </button>
            {(["actions", "otherwise"] as const).map((branch) => (
              <div className="stack" key={branch}>
                <strong>
                  {t(branch === "actions" ? "studio.then" : "studio.otherwise")}
                </strong>
                {event[branch].map((a, n) => (
                  <EffectEditor
                    key={n}
                    value={a}
                    def={def}
                    change={(v) =>
                      patch(i, {
                        ...event,
                        [branch]: event[branch].map((old, j) =>
                          n === j ? v : old,
                        ),
                      })
                    }
                    remove={() =>
                      patch(i, {
                        ...event,
                        [branch]: event[branch].filter((_, j) => n !== j),
                      })
                    }
                  />
                ))}
                <button
                  className="btn"
                  onClick={() =>
                    patch(i, {
                      ...event,
                      [branch]: [
                        ...event[branch],
                        { type: "message", message: lt() },
                      ],
                    })
                  }
                >
                  {t("studio.add_effect")}
                </button>
              </div>
            ))}
            <button
              className="studio-text-danger"
              onClick={() =>
                change({ ...screen, events: events.filter((_, n) => n !== i) })
              }
            >
              {t("studio.delete_event")}
            </button>
          </div>
        </details>
      ))}
      <button
        className="btn"
        onClick={() =>
          change({
            ...screen,
            events: [
              ...events,
              {
                id: uid("event"),
                on: "click",
                component_id:
                  screen.components.find((c) => c.type === "button")?.id ??
                  null,
                conditions: [],
                actions: [],
                otherwise: [],
              },
            ],
          })
        }
      >
        {t("studio.add_event")}
      </button>
    </div>
  );
}
export function TableRows({
  component: c,
  change,
}: {
  component: PComponent;
  change: (v: PComponent) => void;
}) {
  const { t } = useTranslation();
  const lang = useLang();
  const keys = [
    ...new Set([
      ...(c.columns ?? []).map((col) => col.value),
      ...c.rows.flatMap((row) => Object.keys(row)),
    ]),
  ];
  const label = (key: string) =>
    c.columns?.find((col) => col.value === key)?.label[lang] ??
    t(`practice.column.${key}`, { defaultValue: key });
  return (
    <section className="stack">
      <h3>{t("studio.table_data")}</h3>
      <div className="practice-table">
        <table>
          <thead>
            <tr>
              {keys.map((key) => (
                <th key={key}>
                  {label(key)}
                  <button
                    className="studio-text-danger"
                    aria-label={`${t("studio.delete_column")}: ${label(key)}`}
                    onClick={() =>
                      change({
                        ...c,
                        columns: c.columns?.filter((col) => col.value !== key),
                        rows: c.rows.map((row) =>
                          Object.fromEntries(
                            Object.entries(row).filter(
                              ([name]) => name !== key,
                            ),
                          ),
                        ),
                      })
                    }
                  >
                    {" "}
                    ×
                  </button>
                </th>
              ))}
              <th />
            </tr>
          </thead>
          <tbody>
            {c.rows.map((row, i) => (
              <tr key={i}>
                {keys.map((key) => (
                  <td key={key}>
                    <input
                      aria-label={`${label(key)} · ${i + 1}`}
                      value={row[key] ?? ""}
                      maxLength={2000}
                      onChange={(e) =>
                        change({
                          ...c,
                          rows: c.rows.map((old, n) =>
                            n === i ? { ...row, [key]: e.target.value } : old,
                          ),
                        })
                      }
                    />
                  </td>
                ))}
                <td>
                  <button
                    className="studio-text-danger"
                    aria-label={`${t("practice.remove")} · ${i + 1}`}
                    onClick={() =>
                      change({ ...c, rows: c.rows.filter((_, n) => n !== i) })
                    }
                  >
                    ×
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="row practice-wrap">
        <button
          className="btn"
          disabled={c.rows.length >= 50}
          onClick={() =>
            change({
              ...c,
              rows: [
                ...c.rows,
                Object.fromEntries(
                  (keys.length ? keys : ["value"]).map((key) => [key, ""]),
                ),
              ],
            })
          }
        >
          {t("studio.add_row")}
        </button>
        <button
          className="btn"
          disabled={keys.length >= 15}
          onClick={() => {
            let n = keys.length + 1;
            while (keys.includes(`column_${n}`)) n++;
            change({
              ...c,
              columns: [
                ...(c.columns ?? []),
                {
                  value: `column_${n}`,
                  label: lt(`Столбец ${n}`, `${n}-ustun`),
                },
              ],
            });
          }}
        >
          {t("studio.add_column")}
        </button>
      </div>
    </section>
  );
}
export function ComponentInspector({
  value: c,
  def,
  fields,
  change,
  upload,
}: {
  value: PComponent;
  def: Definition;
  fields: PComponent[];
  change: (c: PComponent) => void;
  upload: (f: File) => void;
}) {
  const { t } = useTranslation();
  const lang = useLang();
  return (
    <div className="stack">
      <label>
        {t("studio.component_type")}
        <select
          value={c.type}
          onChange={(e) =>
            change({ ...c, type: e.target.value as PComponent["type"] })
          }
        >
          {componentTypes.map((type) => (
            <option value={type} key={type}>
              {t(`practice.component.${type}`)}
            </option>
          ))}
        </select>
      </label>
      <Bilingual
        label={t("practice.label")}
        value={c.label}
        onChange={(v) => change({ ...c, label: v })}
      />
      <div className="studio-two">
        <Toggle
          label={t("practice.required")}
          value={c.required}
          change={(v) => change({ ...c, required: v })}
        />
        <Toggle
          label={t("studio.editable")}
          value={c.editable !== false}
          change={(v) => change({ ...c, editable: v })}
        />
        <Toggle
          label={t("studio.visible")}
          value={c.visible !== false}
          change={(v) => change({ ...c, visible: v })}
        />
        <label>
          {t("studio.width")}
          <select
            value={c.width ?? "full"}
            onChange={(e) =>
              change({ ...c, width: e.target.value as "full" | "half" })
            }
          >
            <option value="full">100%</option>
            <option value="half">50%</option>
          </select>
        </label>
      </div>
      <Bilingual
        label={t("studio.placeholder")}
        value={c.placeholder ?? lt()}
        onChange={(v) => change({ ...c, placeholder: v.ru || v.uz ? v : null })}
      />
      <Bilingual
        label={t("practice.hint")}
        value={c.hint ?? lt()}
        onChange={(v) => change({ ...c, hint: v.ru || v.uz ? v : null })}
      />
      <ValueEditor
        label={t("studio.default_value")}
        value={c.default_value ?? null}
        kind={c.type}
        change={(v) => change({ ...c, default_value: v })}
      />
      <label>
        {t("studio.binding")}
        <input
          value={c.binding ?? ""}
          pattern="[a-z][a-z0-9_]*"
          onChange={(e) => change({ ...c, binding: e.target.value || null })}
        />
      </label>
      {["select", "document", "tabs", "dialog"].includes(c.type) && (
        <section className="stack">
          <h3>{t("practice.options")}</h3>
          {c.options.map((o, i) => (
            <div className="studio-rule stack" key={i}>
              <label>
                {t("studio.code")}
                <input
                  value={o.value}
                  onChange={(e) =>
                    change({
                      ...c,
                      options: c.options.map((old, n) =>
                        n === i ? { ...o, value: e.target.value } : old,
                      ),
                    })
                  }
                />
              </label>
              <Bilingual
                label={t("practice.label")}
                value={o.label}
                onChange={(v) =>
                  change({
                    ...c,
                    options: c.options.map((old, n) =>
                      n === i ? { ...o, label: v } : old,
                    ),
                  })
                }
              />
              <button
                className="studio-text-danger"
                onClick={() =>
                  change({ ...c, options: c.options.filter((_, n) => n !== i) })
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
                ...c,
                options: [...c.options, { value: uid("option"), label: lt() }],
              })
            }
          >
            {t("practice.add_option")}
          </button>
        </section>
      )}
      {[
        "table",
        "client",
        "card",
        "passport",
        "loan",
        "products",
        "operations",
      ].includes(c.type) && (
        <>
          <TableRows component={c} change={change} />
          <h3>{t("studio.columns")}</h3>
          {c.columns?.map((col, i) => (
            <div key={i} className="studio-rule">
              <label>
                {t("studio.code")}
                <input
                  value={col.value}
                  onChange={(e) =>
                    change({
                      ...c,
                      columns: c.columns!.map((old, n) =>
                        n === i ? { ...col, value: e.target.value } : old,
                      ),
                    })
                  }
                />
              </label>
              <Bilingual
                label={t("practice.label")}
                value={col.label}
                onChange={(v) =>
                  change({
                    ...c,
                    columns: c.columns!.map((old, n) =>
                      n === i ? { ...col, label: v } : old,
                    ),
                  })
                }
              />
            </div>
          ))}
          <button
            className="btn"
            onClick={() =>
              change({
                ...c,
                columns: [
                  ...(c.columns ?? []),
                  { value: uid("column"), label: lt() },
                ],
              })
            }
          >
            {t("studio.add_column")}
          </button>
        </>
      )}
      {["image", "video"].includes(c.type) && (
        <label>
          {t("studio.synthetic_upload")}
          <input
            type="file"
            accept={c.type === "video" ? "video/mp4" : "image/png,image/jpeg"}
            onChange={(e) => {
              if (e.target.files?.[0]) upload(e.target.files[0]);
              e.target.value = "";
            }}
          />
        </label>
      )}
      {c.type === "image" && (
        <>
          <h3>{t("studio.hotspots")}</h3>
          {c.hotspots.map((h, i) => (
            <div className="studio-rule stack" key={i}>
              <Bilingual
                label={t("practice.label")}
                value={h.label}
                onChange={(v) =>
                  change({
                    ...c,
                    hotspots: c.hotspots.map((old, n) =>
                      n === i ? { ...h, label: v } : old,
                    ),
                  })
                }
              />
              <select
                aria-label={t("studio.effect")}
                value={h.action}
                onChange={(e) =>
                  change({
                    ...c,
                    hotspots: c.hotspots.map((old, n) =>
                      n === i ? { ...h, action: e.target.value } : old,
                    ),
                  })
                }
              >
                {def.screens
                  .flatMap((s) => s.components)
                  .filter((x) => x.type === "button")
                  .map((x) => (
                    <option key={x.id} value={x.id}>
                      {x.label[lang]}
                    </option>
                  ))}
              </select>
              <div className="studio-two">
                {(["x", "y", "width", "height"] as const).map((k) => (
                  <label key={k}>
                    {k}%
                    <input
                      type="number"
                      min={0}
                      max={100}
                      value={h[k]}
                      onChange={(e) =>
                        change({
                          ...c,
                          hotspots: c.hotspots.map((old, n) =>
                            n === i
                              ? { ...h, [k]: Number(e.target.value) }
                              : old,
                          ),
                        })
                      }
                    />
                  </label>
                ))}
              </div>
              <button
                className="studio-text-danger"
                onClick={() =>
                  change({
                    ...c,
                    hotspots: c.hotspots.filter((_, n) => n !== i),
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
                ...c,
                hotspots: [
                  ...c.hotspots,
                  {
                    label: lt(),
                    action: "",
                    x: 10,
                    y: 10,
                    width: 20,
                    height: 10,
                  },
                ],
              })
            }
          >
            {t("studio.add_hotspot")}
          </button>
        </>
      )}
      <details>
        <summary>{t("studio.visibility")}</summary>
        {c.visible_when ? (
          <ConditionEditor
            value={c.visible_when}
            fields={fields}
            change={(v) => change({ ...c, visible_when: v })}
            remove={() => change({ ...c, visible_when: null })}
          />
        ) : (
          <button
            className="btn"
            onClick={() =>
              change({
                ...c,
                visible_when: {
                  field: fields[0]?.id || "",
                  op: "present",
                  value: null,
                },
              })
            }
          >
            {t("studio.add_condition")}
          </button>
        )}
      </details>
      <details>
        <summary>{t("studio.validation")}</summary>
        <div className="stack">
          {c.validation?.map((v, i) => (
            <div className="studio-rule stack" key={i}>
              <select
                aria-label={t("studio.validation")}
                value={v.kind}
                onChange={(e) =>
                  change({
                    ...c,
                    validation: c.validation!.map((old, n) =>
                      n === i
                        ? { ...v, kind: e.target.value as typeof v.kind }
                        : old,
                    ),
                  })
                }
              >
                {[
                  "min",
                  "max",
                  "min_length",
                  "max_length",
                  "email",
                  "passport",
                  "phone",
                  "digits",
                ].map((k) => (
                  <option key={k} value={k}>
                    {t(`studio.validation_${k}`)}
                  </option>
                ))}
              </select>
              {["min", "max", "min_length", "max_length"].includes(v.kind) && (
                <input
                  aria-label={t("practice.expected")}
                  type="number"
                  value={v.value ?? 0}
                  onChange={(e) =>
                    change({
                      ...c,
                      validation: c.validation!.map((old, n) =>
                        n === i ? { ...v, value: Number(e.target.value) } : old,
                      ),
                    })
                  }
                />
              )}
              <Bilingual
                label={t("studio.error_message")}
                value={v.message ?? lt()}
                onChange={(m) =>
                  change({
                    ...c,
                    validation: c.validation!.map((old, n) =>
                      n === i
                        ? { ...v, message: m.ru || m.uz ? m : null }
                        : old,
                    ),
                  })
                }
              />
              <button
                className="studio-text-danger"
                onClick={() =>
                  change({
                    ...c,
                    validation: c.validation!.filter((_, n) => n !== i),
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
                ...c,
                validation: [
                  ...(c.validation ?? []),
                  { kind: "min_length", value: 1 },
                ],
              })
            }
          >
            {t("studio.add_validation")}
          </button>
        </div>
      </details>
      <small className="muted">ID: {c.id}</small>
    </div>
  );
}
