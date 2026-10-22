export function groupNumber(text: string): string {
  return text.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
}

/** Format the integer part only, preserving a decimal separator while typing. */
export function editNumber(
  previous: string,
  raw: string,
  caret: number,
  inputType = "",
) {
  if (
    inputType.startsWith("delete") &&
    raw.replace(/\s/g, "") === previous.replace(/\s/g, "")
  ) {
    // Deleting a grouping space should delete the adjacent digit, not put the
    // space straight back and leave the caret apparently stuck.
    const at = inputType === "deleteContentBackward" ? caret - 1 : caret;
    if (at >= 0) {
      raw = raw.slice(0, at) + raw.slice(at + 1);
      caret = at;
    }
  }
  const clean = raw.replace(/\s/g, "");
  if (!/^-?\d*(?:[.,]\d*)?$/.test(clean)) return null;
  const value =
    clean === "" ||
    clean === "-" ||
    clean === "." ||
    clean === "," ||
    clean === "-." ||
    clean === "-,"
      ? null
      : Number(clean.replace(",", "."));
  if (value !== null && !Number.isFinite(value)) return null;
  const [integer, fraction] = clean.split(/[.,]/);
  const separator = clean.includes(",") ? "," : ".";
  const text =
    groupNumber(integer) + (fraction === undefined ? "" : separator + fraction);
  const characters = raw.slice(0, caret).replace(/\s/g, "").length;
  let position = 0;
  let count = 0;
  while (position < text.length && count < characters) {
    if (text[position] !== " ") count++;
    position++;
  }
  return { text, value, caret: position };
}

export function numberText(value: unknown): string {
  return typeof value === "number" && Number.isFinite(value)
    ? (editNumber("", String(value), 0)?.text ?? String(value))
    : "";
}
