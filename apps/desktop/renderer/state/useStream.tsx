import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { Ev } from "../lib/types";

type StreamValue = { streamText: string; streaming: boolean };

const StreamStateContext = createContext<StreamValue | null>(null);
const StreamDispatchContext = createContext<((ev: Ev) => void) | null>(null);

export function StreamProvider({ children }: { children: ReactNode }) {
  const [streamText, setStreamText] = useState("");
  const [streaming, setStreaming] = useState(false);

  // 引用恒定：不随 streamText 变化，故写侧消费者永不因流式更新重渲染
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

  const value = useMemo<StreamValue>(
    () => ({ streamText, streaming }),
    [streamText, streaming]
  );

  return (
    <StreamDispatchContext.Provider value={ingest}>
      <StreamStateContext.Provider value={value}>
        {children}
      </StreamStateContext.Provider>
    </StreamDispatchContext.Provider>
  );
}

export function useStream(): StreamValue {
  const ctx = useContext(StreamStateContext);
  if (!ctx) throw new Error("useStream must be used within StreamProvider");
  return ctx;
}

export function useStreamDispatch(): (ev: Ev) => void {
  const ctx = useContext(StreamDispatchContext);
  if (!ctx)
    throw new Error("useStreamDispatch must be used within StreamProvider");
  return ctx;
}
