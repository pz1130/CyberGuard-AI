import { useI18n, type TFunc } from "../i18n/I18nProvider";
import type { Resolved } from "../i18n/plural";
import "./Timestamp.css";

function localeOf(resolved: Resolved): string {
  return resolved === "zh" ? "zh-CN" : "en-US";
}

/** Relative time; `now` injectable for tests. */
export function formatRelative(
  ms: number,
  t: TFunc,
  resolved: Resolved = "zh",
  now: number = Date.now()
): string {
  const diff = Math.max(0, now - ms);
  const min = Math.floor(diff / 60000);
  if (min < 1) return t("time.justNow");
  if (min < 60) return t("time.minutesAgo", { n: min });
  const hr = Math.floor(min / 60);
  if (hr < 24) return t("time.hoursAgo", { n: hr });
  const day = Math.floor(hr / 24);
  if (day < 30) return t("time.daysAgo", { n: day });
  return new Date(ms).toLocaleDateString(localeOf(resolved));
}

export type TimestampProps = {
  /** Milliseconds; second-scale values are scaled up */
  value: number | string;
  relative?: boolean;
};

export function Timestamp({ value, relative = true }: TimestampProps) {
  const { t, resolved } = useI18n();
  const raw = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(raw)) return <span className="ui-ts">—</span>;
  const ms = raw < 1e12 ? raw * 1000 : raw;
  const iso = new Date(ms).toISOString();
  const loc = localeOf(resolved);
  return (
    <time className="ui-ts" dateTime={iso} title={new Date(ms).toLocaleString(loc)}>
      {relative ? formatRelative(ms, t, resolved) : new Date(ms).toLocaleTimeString(loc)}
    </time>
  );
}
