/**
 * Stable text for any JSON value: object keys sorted, lists of strings sorted.
 * Two values that mean the same thing give the same text, whatever the order
 * their keys or string lists were written in.
 */
export function canonical(value: unknown): string {
  if (Array.isArray(value)) {
    const items = value.map(canonical);
    return `[${(value.every((item) => typeof item === "string") ? items.sort() : items).join(",")}]`;
  }
  if (typeof value === "object" && value !== null) {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${key}:${canonical((value as Record<string, unknown>)[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}
