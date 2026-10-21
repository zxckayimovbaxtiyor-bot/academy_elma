import { useTranslation } from "react-i18next";

import type { Lang } from "../api/types";

export function useLang(): Lang {
  const { i18n } = useTranslation();
  return i18n.language === "ru" ? "ru" : "uz";
}

type Localized<K extends string> = { [P in `${K}_uz` | `${K}_ru`]: string | null };

/** The uz or ru variant of a bilingual field: pick(module, "title", lang). */
export function pick<K extends string>(obj: Localized<K>, key: K, lang: Lang): string {
  const own = obj[`${key}_${lang}` as `${K}_uz`];
  return own ?? obj[`${key}_uz` as `${K}_uz`] ?? "";
}

/** Same, for reference rows (branch, region, job role) that use name_*. */
export function name(ref: { name_uz: string; name_ru: string } | null | undefined, lang: Lang) {
  if (!ref) return "";
  return lang === "ru" ? ref.name_ru : ref.name_uz;
}
