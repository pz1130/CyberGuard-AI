export type Resolved = "zh" | "en";

/**
 * 复数选择。en 只区分 1 与非 1（英文规则），zh 无单复数变化恒取 _other。
 * 不引入 Intl.PluralRules —— 只有两种语言，规则写死比引依赖清楚。
 */
export function pickPluralKey(
  resolved: Resolved,
  key: string,
  count: number
): string {
  if (resolved === "en" && count === 1) return `${key}_one`;
  return `${key}_other`;
}

/** `{name}` 直替。不求值表达式，缺参数原样保留 —— 词条里出现裸占位符要看得见。 */
export function interpolate(
  tpl: string,
  params: Record<string, string | number> = {}
): string {
  return tpl.replace(/\{(\w+)\}/g, (whole, name: string) =>
    name in params ? String(params[name]) : whole
  );
}
