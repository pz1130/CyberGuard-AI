import type { Resolved } from "./plural";

/**
 * 回答语言跟随界面语言（spec §0.1）。走 agent.run 已有的 system_prompt 字段，
 * 不需要改协议。zh 返回 undefined —— 模型默认就跟着用户提问语言走，
 * 多塞一句中文指令只是浪费上下文。
 */
export function languageDirective(resolved: Resolved): string | undefined {
  if (resolved === "zh") return undefined;
  return "Respond in English. Keep tool names, file paths, hashes and identifiers verbatim.";
}
