import type { ReactElement } from "react";
import type { SkillsSectionModel } from "./useSkillsSection";

export type SkillsSectionProps = SkillsSectionModel;

export function SkillsSection({
  skills,
  skillDrafts,
  skillMsg,
  skillBusy,
  skillName,
  setSkillName,
  skillDesc,
  setSkillDesc,
  skillBody,
  setSkillBody,
  skillVersion,
  setSkillVersion,
  skillMode,
  setSkillMode,
  skillEditSource,
  skillSelected,
  resetSkillEditor,
  openSkill,
  onSaveSkillDraft,
  onApproveSkill,
  onDeleteSkill,
  onImportSkill,
  onForkSkill,
  onRevealSkillDir,
}: SkillsSectionProps): ReactElement {
  return (
    <div className="settings-detail">
      <div className="settings-card">
        <h3>技能 SOP</h3>
        <p className="data-hint">
          流程：新建/导入 → 草稿 → <strong>批准</strong> 后进入 agent catalog。
          内置只读；运行时用 <code className="mono">load_skill</code> 拉正文。
        </p>
        <div className="empty-actions">
          <button
            type="button"
            className="primary"
            onClick={resetSkillEditor}
            disabled={skillBusy}
          >
            + 新建
          </button>
          <button
            type="button"
            className="secondary"
            onClick={() => void onImportSkill()}
            disabled={skillBusy}
          >
            从 Markdown 导入…
          </button>
          <button
            type="button"
            className="secondary"
            onClick={() => void onRevealSkillDir("drafts")}
          >
            打开草稿目录
          </button>
          <button
            type="button"
            className="secondary"
            onClick={() => void onRevealSkillDir("approved")}
          >
            打开已批准
          </button>
        </div>
      </div>

      <div className="settings-card">
        <h3>已生效（catalog）</h3>
        <div className="mcp-list">
          {skills.length === 0 && (
            <p className="muted-copy">暂无（sidecar 离线？）</p>
          )}
          {skills.map((s) => (
            <button
              key={`${s.source}-${s.name}`}
              type="button"
              className={`mcp-list-item${
                skillSelected === s.name && skillEditSource !== "draft"
                  ? " active"
                  : ""
              }`}
              onClick={() => void openSkill(s.name, s.source)}
            >
              <strong>{s.name}</strong>
              <span className="muted-copy">
                {s.source || "?"}
                {s.version ? ` · v${s.version}` : ""}
                {s.readonly ? " · 只读" : ""}
              </span>
              <div className="mono-xs">{s.description}</div>
            </button>
          ))}
        </div>
      </div>

      <div className="settings-card">
        <h3>
          草稿{" "}
          <span className="pill warn">不参与装配</span>
        </h3>
        <div className="mcp-list">
          {skillDrafts.length === 0 && (
            <p className="muted-copy">无草稿</p>
          )}
          {skillDrafts.map((s) => (
            <button
              key={`draft-${s.name}`}
              type="button"
              className={`mcp-list-item${
                skillSelected === s.name && skillEditSource === "draft"
                  ? " active"
                  : ""
              }`}
              onClick={() => void openSkill(s.name, "draft")}
            >
              <strong>{s.name}</strong>
              <span className="muted-copy">
                draft{s.version ? ` · v${s.version}` : ""}
              </span>
              <div className="mono-xs">{s.description}</div>
            </button>
          ))}
        </div>
      </div>

      <div className="settings-card">
        <h3>
          编辑器{" "}
          {skillEditSource !== "new" ? (
            <span
              className={`pill${
                skillEditSource === "builtin"
                  ? ""
                  : skillEditSource === "approved"
                    ? " ok"
                    : " warn"
              }`}
            >
              {skillEditSource}
            </span>
          ) : (
            <span className="pill">new</span>
          )}
        </h3>
        <label className="field-label">
          Name（字母开头，a-z 0-9 _ -）
          <input
            className="data-input"
            value={skillName}
            onChange={(e) => setSkillName(e.target.value)}
            disabled={skillBusy || skillEditSource === "builtin"}
            placeholder="my_custom_sop"
          />
        </label>
        <label className="field-label">
          Description（catalog 一行摘要）
          <input
            className="data-input"
            value={skillDesc}
            onChange={(e) => setSkillDesc(e.target.value)}
            disabled={skillBusy || skillEditSource === "builtin"}
            placeholder="When to use this SOP"
          />
        </label>
        <div className="row mt-8">
          <label className="field-label" style={{ flex: 1, marginTop: 0 }}>
            Version
            <input
              className="data-input"
              value={skillVersion}
              onChange={(e) => setSkillVersion(e.target.value)}
              disabled={skillBusy || skillEditSource === "builtin"}
            />
          </label>
          <label className="field-label" style={{ flex: 1, marginTop: 0 }}>
            Mode
            <select
              value={skillMode}
              onChange={(e) => setSkillMode(e.target.value)}
              disabled={skillBusy || skillEditSource === "builtin"}
            >
              <option value="both">both</option>
              <option value="advisory">advisory</option>
              <option value="operator">operator</option>
            </select>
          </label>
        </div>
        <label className="field-label">
          Body（Markdown 规程正文）
          <textarea
            className="plan-edit skill-body-edit"
            rows={12}
            value={skillBody}
            onChange={(e) => setSkillBody(e.target.value)}
            disabled={skillBusy || skillEditSource === "builtin"}
            placeholder="# SOP …"
          />
        </label>
        <div className="empty-actions mt-10">
          {skillEditSource === "builtin" ? (
            <button
              type="button"
              className="primary"
              onClick={() => void onForkSkill()}
              disabled={skillBusy}
            >
              复制到草稿编辑
            </button>
          ) : (
            <>
              <button
                type="button"
                className="secondary"
                onClick={() => void onSaveSkillDraft()}
                disabled={skillBusy}
              >
                保存草稿
              </button>
              <button
                type="button"
                className="primary"
                onClick={() => void onApproveSkill()}
                disabled={skillBusy}
              >
                批准生效
              </button>
              {(skillEditSource === "draft" ||
                skillEditSource === "approved") && (
                <button
                  type="button"
                  className="btn-reject"
                  onClick={() => void onDeleteSkill()}
                  disabled={skillBusy}
                >
                  删除
                </button>
              )}
            </>
          )}
        </div>
        {skillMsg && <pre className="data-msg">{skillMsg}</pre>}
      </div>
    </div>
  );
}
