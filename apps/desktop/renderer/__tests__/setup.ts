import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

/**
 * Node 22+/26 在未传 --localstorage-file 时把 globalThis.localStorage
 * 设成 undefined，并连带让 jsdom 的 window.localStorage 也不可用。
 * 自建一份最小 Storage，挂到 globalThis 与 window，供折叠持久化测试使用。
 */
function installLocalStorage() {
  const store = new Map<string, string>();
  const storage: Storage = {
    get length() {
      return store.size;
    },
    clear() {
      store.clear();
    },
    getItem(key: string) {
      return store.has(key) ? store.get(key)! : null;
    },
    key(index: number) {
      return Array.from(store.keys())[index] ?? null;
    },
    removeItem(key: string) {
      store.delete(key);
    },
    setItem(key: string, value: string) {
      store.set(String(key), String(value));
    },
  };
  Object.defineProperty(globalThis, "localStorage", {
    value: storage,
    configurable: true,
    writable: true,
  });
  Object.defineProperty(window, "localStorage", {
    value: storage,
    configurable: true,
    writable: true,
  });
}

if (
  typeof globalThis.localStorage === "undefined" ||
  globalThis.localStorage == null ||
  typeof globalThis.localStorage.getItem !== "function"
) {
  installLocalStorage();
}

// jsdom 不实现 matchMedia，主题与 reduced-motion 代码会用到
const defaultMatchMedia = ((query: string) => ({
  matches: false,
  media: query,
  onchange: null,
  addEventListener: () => {},
  removeEventListener: () => {},
  addListener: () => {},
  removeListener: () => {},
  dispatchEvent: () => false,
})) as unknown as typeof window.matchMedia;

if (!window.matchMedia) {
  window.matchMedia = defaultMatchMedia;
}

afterEach(() => {
  cleanup();
  // 共享 Map 不随 jsdom 文档重置；不清会把折叠键泄漏到同 worker 后续文件
  try {
    localStorage.clear();
  } catch {
    /* ignore */
  }
  // responsive 等用例会覆盖 matchMedia；恢复恒 false 桩避免污染主题/断点
  window.matchMedia = defaultMatchMedia;
});
