import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import type { Lang } from "../api/types";
import ru from "./ru.json";
import uz from "./uz.json";

const KEY = "academy.lang";

function saved(): Lang {
  try {
    return localStorage.getItem(KEY) === "ru" ? "ru" : "uz";
  } catch {
    return "uz"; // storage may be blocked
  }
}

export function remember(lang: Lang): void {
  try {
    localStorage.setItem(KEY, lang);
  } catch {
    /* not essential */
  }
  document.documentElement.lang = lang;
}

void i18n.use(initReactI18next).init({
  resources: { uz: { translation: uz }, ru: { translation: ru } },
  lng: saved(),
  fallbackLng: "uz",
  interpolation: { escapeValue: false }, // React escapes
  returnNull: false,
});
document.documentElement.lang = i18n.language;

export default i18n;
