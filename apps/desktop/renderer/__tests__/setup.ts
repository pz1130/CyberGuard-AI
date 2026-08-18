import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
});

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
if (!window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}
