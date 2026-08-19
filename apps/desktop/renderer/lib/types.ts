export type Tier = "readonly" | "full";

export type ThemeMode = "dark" | "light" | "system";

export type Caps = {
  tier: string;
  has_read: boolean;
  has_exec: boolean;
  has_edit: boolean;
  mock?: boolean;
  real_read?: boolean;
  real_edit?: boolean;
  real_exec?: boolean;
  sandbox_impl?: string;
  policy?: { sandbox_mode?: string };
};

export type Ev = { type: string; [k: string]: unknown };

export type SessionRow = {
  session_id: string;
  title: string;
  tier: string;
  updated_at: number;
  event_count: number;
};

export type PendingPlan = {
  plan_id: string;
  plan?: {
    summary?: string;
    steps?: string[];
    risk_level?: string;
    blast_radius?: Record<string, unknown>;
  };
  approval_type?: string;
  ui_label?: string;
  local_approve_allowed?: boolean;
  timeout_seconds?: number;
  revisedDraft?: string;
};

export type ActiveView = "workbench" | "evidence" | "settings";

export type SettingsSection =
  | "hub"
  | "llm"
  | "mcp"
  | "skills"
  | "appearance"
  | "data"
  | "about";

export type SkillPublic = {
  name: string;
  description: string;
  version?: string;
  source?: string;
  mode?: string;
  requires_tools?: string[];
  sha256?: string;
  path?: string | null;
  readonly?: boolean;
  body?: string;
};

export type ProviderPublic = {
  mode: string;
  base_url: string;
  model: string;
  temperature: number;
  has_api_key: boolean;
  preset_id?: string | null;
  local?: boolean;
  requires_api_key?: boolean;
  effective?: {
    mode?: string;
    model?: string;
    has_api_key?: boolean;
    local?: boolean;
  };
  ok?: boolean;
};

export type McpServerPublic = {
  id: string;
  command: string;
  args: string[];
  env?: Record<string, string>;
  env_keys?: string[];
  timeout_seconds?: number;
  readonly: boolean;
  enabled: boolean;
  description?: string;
  secret_env?: string;
  has_secret?: boolean;
};

export type EvidenceItem = {
  evidence_id: string;
  path: string;
  name: string;
  sha256: string;
  size: number;
  readonly: boolean;
  trusted_dir?: boolean;
  registered_at: number;
  note?: string;
  source?: string;
  mount?: string;
};

export type EvidenceVerifyResult = {
  ok: boolean;
  evidence_id: string;
  expected_sha256?: string;
  current_sha256?: string;
  error?: string;
  path?: string;
  name?: string;
  readonly?: boolean;
};

declare global {
  interface Window {
    cyberguard?: {
      ping: () => Promise<Record<string, unknown> & { ok?: boolean; data_root?: string }>;
      capabilities: (tier: Tier) => Promise<Caps>;
      run: (
        task: string,
        tier: Tier,
        sessionId?: string,
        systemPrompt?: string
      ) => Promise<{ result: unknown; events: Ev[] }>;
      abort: (runId: string) => Promise<{ ok: boolean }>;
      steer: (runId: string, message: string) => Promise<{ ok: boolean }>;
      listSessions: () => Promise<{ sessions: SessionRow[] }>;
      createSession: (
        title: string,
        tier: Tier
      ) => Promise<{ session_id: string; title: string }>;
      sessionEvents: (sessionId: string) => Promise<{ events: Ev[] }>;
      deleteSession?: (
        sessionId: string
      ) => Promise<{ ok?: boolean; deleted?: boolean }>;
      skillsList?: () => Promise<{
        ok?: boolean;
        skills: SkillPublic[];
        drafts?: SkillPublic[];
        dirs?: { approved?: string; drafts?: string; builtin?: string };
      }>;
      skillsGet?: (
        name: string,
        source?: string
      ) => Promise<{ ok?: boolean; skill?: SkillPublic; error?: string }>;
      skillsSaveDraft?: (params: {
        name: string;
        description?: string;
        body: string;
        version?: string;
        mode?: string;
        requires_tools?: string[];
      }) => Promise<{
        ok?: boolean;
        skill?: SkillPublic;
        error?: string;
        warning?: string;
      }>;
      skillsImport?: (params: {
        path?: string;
        content?: string;
        name?: string;
      }) => Promise<{
        ok?: boolean;
        skill?: SkillPublic;
        error?: string;
        warning?: string;
      }>;
      skillsApprove?: (
        name: string
      ) => Promise<{
        ok?: boolean;
        skill?: SkillPublic;
        error?: string;
        message?: string;
      }>;
      skillsDelete?: (
        name: string,
        source: string
      ) => Promise<{ ok?: boolean; deleted?: string; error?: string }>;
      skillsFork?: (
        name: string
      ) => Promise<{
        ok?: boolean;
        skill?: SkillPublic;
        error?: string;
        warning?: string;
      }>;
      resume?: (runId: string) => Promise<{ ok?: boolean }>;
      planApprove?: (
        planId: string,
        revisedPlan?: string
      ) => Promise<{ ok: boolean; plan?: unknown }>;
      planReject?: (
        planId: string,
        reason?: string
      ) => Promise<{ ok: boolean }>;
      planList?: () => Promise<{ plans: unknown[] }>;
      providerGet?: () => Promise<ProviderPublic>;
      providerSet?: (params: {
        mode?: string;
        base_url?: string;
        model?: string;
        temperature?: number;
        api_key?: string;
        preset_id?: string;
      }) => Promise<ProviderPublic & { ok?: boolean }>;
      providerTest?: () => Promise<{
        ok: boolean;
        mode?: string;
        latency_ms?: number;
        error?: string;
        message?: string;
      }>;
      prefsGet?: () => Promise<{
        theme?: string;
        font_size?: string;
        language?: string;
      }>;
      prefsSet?: (params: {
        theme?: string;
        font_size?: string;
        language?: string;
      }) => Promise<{
        ok?: boolean;
        prefs?: { theme?: string; font_size?: string; language?: string };
      }>;
      mcpConfigList?: () => Promise<{ servers: McpServerPublic[] }>;
      mcpConfigUpsert?: (
        params: Record<string, unknown>
      ) => Promise<{ ok?: boolean; server?: McpServerPublic }>;
      mcpConfigDelete?: (id: string) => Promise<{ ok?: boolean }>;
      mcpConfigInstallDemo?: () => Promise<{
        ok?: boolean;
        server?: McpServerPublic;
      }>;
      mcpConfigInstallFileAlerts?: (path?: string) => Promise<{
        ok?: boolean;
        server?: McpServerPublic;
      }>;
      mcpDiscover?: (
        tier?: string
      ) => Promise<{ tools?: Array<{ name: string }>; servers?: string[] }>;
      pickFile?: (opts?: {
        title?: string;
        properties?: string[];
      }) => Promise<{ ok?: boolean; canceled?: boolean; path?: string }>;
      showItemInFolder?: (
        path: string
      ) => Promise<{ ok?: boolean; error?: string; path?: string }>;
      evidenceList?: (limit?: number) => Promise<{ evidence: EvidenceItem[] }>;
      evidenceRegister?: (
        path: string,
        note?: string
      ) => Promise<{ ok?: boolean; item?: EvidenceItem }>;
      evidenceVerify?: (evidenceId: string) => Promise<EvidenceVerifyResult>;
      exportEncrypted?: (passphrase: string) => Promise<{
        ok?: boolean;
        canceled?: boolean;
        method?: string;
        dest?: string;
        path?: string;
        sha256?: string;
        plaintext_sha256?: string;
        error?: string;
      }>;
      uninstallInventory?: () => Promise<{
        data_root?: string;
        will_delete?: Array<{ name: string; approx_bytes?: number }>;
        will_not_delete?: { evidence_outside_data_root?: string[] };
        manual_steps?: Array<{ item: string; action: string }>;
      }>;
      uninstallExecute?: (opts: {
        confirm: boolean;
        dryRun: boolean;
      }) => Promise<{
        ok?: boolean;
        canceled?: boolean;
        executed?: boolean;
        deleted?: string[];
        dry_run?: boolean;
      }>;
      onEvent: (handler: (ev: Ev) => void) => () => void;
      onOpenDataPanel?: (handler: () => void) => () => void;
    };
  }
}

export {};
