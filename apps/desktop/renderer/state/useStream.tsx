import {
  createContext,
  useCallback,
  useContext,
  useState,
  type ReactNode,
} from "react";
import type { Ev } from "../lib/types";

/**
 * 流式域拆成三个 context，刻意不合并：
 *
 *   StreamTextContext     每 token 变一次 —— 只有 StreamEvent 订阅
 *   StreamFlagContext     只在 false↔true 时变 —— Timeline 等订阅
 *   StreamDispatchContext 引用恒定 —— 写侧永不重渲染
 *
 * 合并 text 与 flag 会让「只关心在不在流」的消费者随每个 token 重渲染
 * （Context 无选择性订阅，解构不减少订阅面），Timeline 会拖着全部事件卡
 * 一起重渲染。这正是本域存在的理由，不要为了少一个 context 合回去。
 */

const StreamTextContext = createContext<string | null>(null);
const StreamFlagContext = createContext<boolean | null>(null);
const StreamDispatchContext = createContext<((ev: Ev) => void) | null>(null);

export function StreamProvider({ children }: { children: ReactNode }) {
  const [streamText, setStreamText] = useState("");
  const [streaming, setStreaming] = useState(false);

  // 引用恒定：不依赖任何 state
  const ingest = useCallback((ev: Ev) => {
    if (ev.type === "token" && typeof ev.delta === "string") {
      setStreaming(true);
      setStreamText((prev) => prev + String(ev.delta));
      return;
    }
    if (ev.type === "token_done") {
      setStreaming(false);
      return;
    }
    // 新一轮工具调用：清掉中间模型碎碎念，保证最终流式输出干净
    if (ev.type === "tool_call_start" || ev.type === "run_started") {
      setStreamText("");
      setStreaming(false);
      return;
    }
    // 完整答案已成卡片，清空实时缓冲
    if (ev.type === "answer_ready" || ev.type === "error") {
      setStreamText("");
      setStreaming(false);
    }
  }, []);

  return (
    <StreamDispatchContext.Provider value={ingest}>
      <StreamFlagContext.Provider value={streaming}>
        <StreamTextContext.Provider value={streamText}>
          {children}
        </StreamTextContext.Provider>
      </StreamFlagContext.Provider>
    </StreamDispatchContext.Provider>
  );
}

/** 只订阅「在不在流」。不会随 token 重渲染。 */
export function useStreamFlag(): boolean {
  const ctx = useContext(StreamFlagContext);
  if (ctx === null)
    throw new Error("useStreamFlag must be used within StreamProvider");
  return ctx;
}

/**
 * 订阅流式正文 —— 每个 token 都会重渲染调用方。
 * 只有真正渲染正文的组件才允许用（目前仅 StreamEvent）。
 */
export function useStreamText(): string {
  const ctx = useContext(StreamTextContext);
  if (ctx === null)
    throw new Error("useStreamText must be used within StreamProvider");
  return ctx;
}

export function useStreamDispatch(): (ev: Ev) => void {
  const ctx = useContext(StreamDispatchContext);
  if (!ctx)
    throw new Error("useStreamDispatch must be used within StreamProvider");
  return ctx;
}
