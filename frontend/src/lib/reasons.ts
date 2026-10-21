import { useTranslation } from "react-i18next";

import type { Reason } from "../api/types";
import { dateTime } from "./format";

/** Why a test can't start, in words (codes come from the server's eligibility check). */
export function useReasonText() {
  const { t } = useTranslation();
  return (reason: Reason): string => {
    const params: Record<string, unknown> = { ...reason.params };
    if (typeof params.until === "string") params.until = dateTime(params.until);
    const key = `reason.${reason.code.replace(/\./g, "_")}`;
    const text = t(key, { ...params, defaultValue: "" });
    return typeof text === "string" && text ? text : t("reason.unknown");
  };
}
