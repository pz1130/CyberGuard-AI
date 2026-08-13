import "./Timestamp.css";

/** 把毫秒时间戳格式化成中文相对时间。now 可注入以便测试。 */
export function formatRelative(ms: number, now: number = Date.now()): string {
  const diff = Math.max(0, now - ms);
  const min = Math.floor(diff / 60000);
  if (min < 1) return "刚刚";
  if (min < 60) return `${min} 分钟前`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr} 小时前`;
  const day = Math.floor(hr / 24);
  if (day < 30) return `${day} 天前`;
  return new Date(ms).toLocaleDateString("zh-CN");
}

export type TimestampProps = {
  /** 毫秒时间戳；秒级时间戳会被自动放大 */
  value: number | string;
  relative?: boolean;
};

export function Timestamp({ value, relative = true }: TimestampProps) {
  const raw = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(raw)) return <span className="ui-ts">—</span>;
  const ms = raw < 1e12 ? raw * 1000 : raw;
  const iso = new Date(ms).toISOString();
  return (
    <time className="ui-ts" dateTime={iso} title={new Date(ms).toLocaleString("zh-CN")}>
      {relative ? formatRelative(ms) : new Date(ms).toLocaleTimeString("zh-CN")}
    </time>
  );
}
