import { describe, expect, it } from "vitest";
import zh from "../../i18n/zh.json";
import { deriveTccSummary, extractPausedRunId, parsePing } from "../../state/envParse";
import { formatExportResult } from "../../state/useExport";
import { formatInventory } from "../../state/useUninstall";

describe("parsePing", () => {
  it("完整响应逐字段映射", () => {
    const p = parsePing({
      data_root: "/Users/x/.cyberguard",
      provider: { mode: "live" },
      sandbox: { sandbox_impl: "seatbelt" },
      policy_defaults: { readonly: { sandbox_mode: "strict" } },
      filevault: { warning: null },
      tcc: { summary: "fda_likely", warning: null, guidance: null },
      evidence_count: 4,
    });
    expect(p).toMatchObject({
      pingOk: true,
      dataRoot: "/Users/x/.cyberguard",
      providerMode: "live",
      sandboxImpl: "seatbelt",
      sandboxMode: "strict",
      tccSummary: "fda_likely",
      evidenceCount: 4,
    });
  });

  it("空响应全部回落到安全默认值", () => {
    const p = parsePing({});
    expect(p.providerMode).toBe("mock");
    expect(p.sandboxImpl).toBe("unknown");
    expect(p.evidenceCount).toBe(0);
    expect(p.fvWarning).toBe(null);
  });

  it("字段类型不对时不抛异常，按缺失处理", () => {
    const p = parsePing({
      data_root: 42,
      provider: null,
      sandbox: "nope",
      evidence_count: "4",
    });
    expect(p.dataRoot).toBe("");
    expect(p.providerMode).toBe("mock");
    expect(p.sandboxImpl).toBe("unknown");
    expect(p.evidenceCount).toBe(0);
  });

  it("FileVault 告警原样透传（安全降级不得吞掉）", () => {
    const p = parsePing({ filevault: { warning: "FileVault 未开启" } });
    expect(p.fvWarning).toBe("FileVault 未开启");
  });
});

describe("deriveTccSummary", () => {
  it("summary 优先", () => {
    expect(deriveTccSummary({ summary: "restricted", full_disk_access: true }))
      .toBe("restricted");
  });

  it("无 summary 时从 full_disk_access 推断", () => {
    expect(deriveTccSummary({ full_disk_access: true })).toBe("fda_likely");
    expect(deriveTccSummary({ full_disk_access: false })).toBe("restricted");
  });

  it("两者都没有时回落", () => {
    expect(deriveTccSummary(undefined)).toBe("—");
    expect(deriveTccSummary({ full_disk_access: null })).toBe("—");
  });
});

describe("extractPausedRunId", () => {
  it("取第一条暂停运行的 run_id", () => {
    expect(
      extractPausedRunId({ paused_runs: [{ run_id: "r-1" }, { run_id: "r-2" }] })
    ).toBe("r-1");
  });

  it("空列表或缺字段返回 null", () => {
    expect(extractPausedRunId({})).toBe(null);
    expect(extractPausedRunId({ paused_runs: [] })).toBe(null);
    expect(extractPausedRunId({ paused_runs: [{}] })).toBe(null);
  });
});

describe("formatExportResult", () => {
  // 钉中文词条，保持既有断言意图（成功路径 / 取消 / 失败）
  const tZh = (k: string, params?: Record<string, string | number>) => {
    const raw = String((zh as Record<string, string>)[k] ?? "");
    return raw.replace(/\{(\w+)\}/g, (_, n: string) =>
      params && n in params ? String(params[n]) : `{${n}}`
    );
  };

  it("成功时含目标路径与哈希前缀", () => {
    const s = formatExportResult(
      {
        ok: true,
        method: "age",
        dest: "/tmp/out.age",
        plaintext_sha256: "abcdef0123456789",
      },
      tZh
    );
    expect(s).toContain("/tmp/out.age");
    expect(s).toContain("abcdef012345");
  });

  it("取消与失败各自成文", () => {
    expect(formatExportResult({ canceled: true }, tZh)).toBe("已取消");
    expect(formatExportResult({ ok: false, error: "磁盘满" }, tZh)).toBe(
      "磁盘满"
    );
  });
});

describe("formatInventory", () => {
  it("外部证据必须显式列出「不会删」", () => {
    const s = formatInventory({
      data_root: "/d",
      will_delete: [{ name: "sessions", approx_bytes: 100 }],
      will_not_delete: { evidence_outside_data_root: ["/Volumes/ext/a.pcap"] },
    });
    expect(s).toContain("will NOT delete");
    expect(s).toContain("/Volumes/ext/a.pcap");
  });

  it("空清单也给出明确占位而非空白", () => {
    const s = formatInventory({});
    expect(s).toContain("(empty)");
    expect(s).toContain("(none)");
  });
});
