/** Recovery drafts contain author-only answers; keep them in the current tab and clear on account changes. */
export function clearOtherPracticeDrafts(
  storage: Pick<Storage, "length" | "key" | "removeItem">,
  keepUser?: number,
) {
  try {
    const keys = Array.from({ length: storage.length }, (_, i) =>
      storage.key(i),
    );
    for (const key of keys)
      if (
        key?.startsWith("practice-studio:") &&
        key !== `practice-studio:${keepUser}`
      )
        storage.removeItem(key);
  } catch {
    /* Browsers can block storage. */
  }
}
