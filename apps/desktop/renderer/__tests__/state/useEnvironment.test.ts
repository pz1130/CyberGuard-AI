import { describe, expect, it } from "vitest";
import {
  deriveDegradations,
  initialEnvState,
  type EnvState,
} from "../../state/degradations";

const healthy: EnvState = {
  ...initialEnvState,
  pingOk: true,
  providerMode: "live",
  sandboxImpl: "seatbelt",
  tccSummary: "fda_likely",
};

describe("deriveDegradations", () => {
  it("全健康时无降级", () => {
    expect(deriveDegradations(healthy)).toEqual([]);
  });

  it("sidecar 离线 → danger + security", () => {
    const d = deriveDegradations({ ...healthy, pingOk: false });
    const item = d.find((x) => x.id === "offline");
    expect(item?.level).toBe("danger");
    expect(item?.security).toBe(true);
  });

  it("sandbox_impl=none → danger + security（INV-16）", () => {
    const d = deriveDegradations({ ...healthy, sandboxImpl: "none" });
    const item = d.find((x) => x.id === "sandbox");
    expect(item?.level).toBe("danger");
    expect(item?.security).toBe(true);
  });

  it("FileVault 告警 → danger + security", () => {
    const d = deriveDegradations({ ...healthy, fvWarning: "FileVault 未开启" });
    const item = d.find((x) => x.id === "filevault");
    expect(item?.level).toBe("danger");
    expect(item?.security).toBe(true);
    expect(item?.detail).toContain("FileVault");
  });

  it("TCC 受限 → warn + security", () => {
    const d = deriveDegradations({ ...healthy, tccSummary: "restricted" });
    const item = d.find((x) => x.id === "tcc");
    expect(item?.level).toBe("warn");
    expect(item?.security).toBe(true);
  });

  it("mock 模型 → warn 但不是安全降级（不占顶部浮出）", () => {
    const d = deriveDegradations({ ...healthy, providerMode: "mock" });
    const item = d.find((x) => x.id === "mock");
    expect(item?.level).toBe("warn");
    expect(item?.security).toBe(false);
  });

  it("多项同时降级时按 danger 在前排序", () => {
    const d = deriveDegradations({
      ...healthy,
      providerMode: "mock",
      tccSummary: "restricted",
      sandboxImpl: "none",
    });
    expect(d[0].level).toBe("danger");
    expect(d.map((x) => x.id)).toContain("mock");
  });

  it("pingOk=null（连接中）不算降级", () => {
    const d = deriveDegradations({ ...healthy, pingOk: null });
    expect(d.find((x) => x.id === "offline")).toBeUndefined();
  });
});
