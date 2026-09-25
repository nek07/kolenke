/** Russian plural: plural(5, "отклик", "отклика", "откликов") → "откликов". */
export function plural(n: number, one: string, few: string, many: string): string {
  const a = Math.abs(n) % 100;
  const b = a % 10;
  if (a > 10 && a < 20) return many;
  if (b > 1 && b < 5) return few;
  if (b === 1) return one;
  return many;
}

export const pluralN = (n: number, one: string, few: string, many: string) => `${n} ${plural(n, one, few, many)}`;

const time = (d: Date) => d.toTimeString().slice(0, 5);
const sameDay = (a: Date, b: Date) => a.toDateString() === b.toDateString();

/** «только что», «5 мин назад», «14:32», «3 мар, 14:32». */
export function ago(ts: string | null | undefined): string {
  if (!ts) return "";
  const d = new Date(ts);
  const s = (Date.now() - d.getTime()) / 1000;
  if (s < 60) return "только что";
  if (s < 3600) return `${Math.floor(s / 60)} мин назад`;
  if (s < 86400 && sameDay(d, new Date())) return time(d);
  return `${d.toLocaleDateString("ru-RU", { day: "numeric", month: "short" })}, ${time(d)}`;
}

/** «Сегодня 15:00», «Завтра 10:30», «3 мар 12:00». */
export function whenText(at: string | null | undefined): string {
  if (!at) return "";
  const d = new Date(at);
  const today = new Date();
  const tomorrow = new Date();
  tomorrow.setDate(today.getDate() + 1);
  if (sameDay(d, today)) return `Сегодня ${time(d)}`;
  if (sameDay(d, tomorrow)) return `Завтра ${time(d)}`;
  return `${d.toLocaleDateString("ru-RU", { day: "numeric", month: "short" })} ${time(d)}`;
}

/** «сегодня», «вчера», «4 дня назад». */
export function daysAgo(ts: string | null | undefined): string {
  if (!ts) return "";
  const n = Math.floor((Date.now() - new Date(ts).getTime()) / 864e5);
  if (n <= 0) return "сегодня";
  if (n === 1) return "вчера";
  return `${pluralN(n, "день", "дня", "дней")} назад`;
}

export function dateTime(ts: string | null | undefined): string {
  if (!ts) return "";
  return new Date(ts).toLocaleString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

/** Local date as YYYY-MM-DD (the backend stores local times). */
export const isoDay = (d = new Date()) => d.toLocaleDateString("sv-SE");

/** A refusal is shown softly: «не сейчас». */
export const gentle = (text: string | null | undefined) => (text ?? "").replace(/отказ/gi, "не сейчас");

export const INVITE_RE = /приглаш|собесед|выход/;

// hh message bodies were stored with invisible padding before the backend cleaned them
const cleanMsg = (s: string) =>
  s
    .replace(/[\u00a0\u200b\u2060\ufeff]/g, " ")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();

/** One stored chat item may hold several messages separated by the backend's MSG_SEP. */
export const messageParts = (s: string | null | undefined) =>
  cleanMsg(s ?? "")
    .split(/\n\n———\n\n/)
    .map(cleanMsg)
    .filter(Boolean);
