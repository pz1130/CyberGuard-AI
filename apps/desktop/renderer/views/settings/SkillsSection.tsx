import type { ReactElement } from "react";
import { Button, Card, Disclosure, Field, Select } from "../../ui";
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
      <Card>
        <h3 className="settings-card-title">技能 SOP</h3>
        <p className="settings-hint">
          流程：新建/导入 → 草稿 → <strong>批准</strong> 后进入 agent catalog。
          内置只读；运行时用 <code className="mono">load_skill</code> 拉正文。
        </p>
        <div className="settings-actions" style={{ marginTop: 0 }}>
          <Button
            variant="secondary"
            onClick={resetSkillEditor}
            disabled={skillBusy}
          >
            + 新建
          </Button>
          <Button
            variant="ghost"
            onClick={() => void onImportSkill()}
            disabled={skillBusy}
          >
            从 Markdown 导入…
          </Button>
          <Button
            variant="ghost"
            onClick={() => void onRevealSkillDir("drafts")}
          >
            打开草稿目录
          </Button>
          <Button
            variant="ghost"
            onClick={() => void onRevealSkillDir("approved")}
          >
            打开已批准
          </Button>
        </div>
      </Card>

      <Disclosure summary={`已生效（catalog）${skills.length ? ` · ${skills.length}` : ""}`} defaultOpen>
        <div className="settings-list">
          {skills.length === 0 && (
            <p className="settings-hint">暂无（sidecar 离线？）</p>
          )}
          {skills.map((s) => (
            <button
              key={`${s.source}-${s.name}`}
              type="button"
              className={`skill-list-item${
                skillSelected === s.name && skillEditSource !== "draft"
                  ? " active"
                  : ""
              }`}
              onClick={() => void openSkill(s.name, s.source)}
            >
              <strong>{s.name}</strong>
              <span className="settings-hint" style={{ margin: 0 }}>
                {s.source || "?"}
                {s.version ? ` · v${s.version}` : ""}
                {s.readonly ? " · 只读" : ""}
              </span>
              <div className="mono-xs">{s.description}</div>
            </button>
          ))}
        </div>
      </Disclosure>

      <Disclosure
        summary={`草稿 · 不参与装配${skillDrafts.length ? ` · ${skillDrafts.length}` : ""}`}
      >
        <div className="settings-list">
          {skillDrafts.length === 0 && (
            <p className="settings-hint">无草稿</p>
          )}
          {skillDrafts.map((s) => (
            <button
              key={`draft-${s.name}`}
              type="button"
              className={`skill-list-item${
                skillSelected === s.name && skillEditSource === "draft"
                  ? " active"
                  : ""
              }`}
              onClick={() => void openSkill(s.name, "draft")}
            >
              <strong>{s.name}</strong>
              <span className="settings-hint" style={{ margin: 0 }}>
                draft{s.version ? ` · v${s.version}` : ""}
              </span>
              <div className="mono-xs">{s.description}</div>
            </button>
          ))}
        </div>
      </Disclosure>

      <Card>
        <h3 className="settings-card-title">
          编辑器{" "}
          <span className="pill">{skillEditSource}</span>
        </h3>
        <Field label="Name（字母开头，a-z 0-9 _ -）">
          <input
            className="data-input"
            value={skillName}
            onChange={(e) => setSkillName(e.target.value)}
            disabled={skillBusy || skillEditSource === "builtin"}
            placeholder="my_custom_sop"
          />
        </Field>
        <Field label="Description（catalog 一行摘要）">
          <input
            className="data-input"
            value={skillDesc}
            onChange={(e) => setSkillDesc(e.target.value)}
            disabled={skillBusy || skillEditSource === "builtin"}
            placeholder="When to use this SOP"
          />
        </Field>
        <div className="settings-row-pair">
          <Field label="Version">
            <input
              className="data-input"
              value={skillVersion}
              onChange={(e) => setSkillVersion(e.target.value)}
              disabled={skillBusy || skillEditSource === "builtin"}
            />
          </Field>
          <Field label="Mode">
            <Select
              ariaLabel="Skill mode"
              value={skillMode as "both" | "advisory" | "operator"}
              onChange={setSkillMode}
              disabled={skillBusy || skillEditSource === "builtin"}
              options={[
                { value: "both", label: "both" },
                { value: "advisory", label: "advisory" },
                { value: "operator", label: "operator" },
              ]}
            />
          </Field>
        </div>
        <Field label="Body（Markdown 规程正文）">
          <textarea
            className="skill-body-edit"
            rows={12}
            value={skillBody}
            onChange={(e) => setSkillBody(e.target.value)}
            disabled={skillBusy || skillEditSource === "builtin"}
            placeholder="# SOP …"
          />
        </Field>
        <div className="settings-actions">
          {skillEditSource === "builtin" ? (
            <Button
              variant="secondary"
              onClick={() => void onForkSkill()}
              disabled={skillBusy}
            >
              复制到草稿编辑
            </Button>
          ) : (
            <>
              <Button
                variant="secondary"
                onClick={() => void onSaveSkillDraft()}
                disabled={skillBusy}
              >
                保存草稿
              </Button>
              <Button
                variant="primary"
                onClick={() => void onApproveSkill()}
                disabled={skillBusy}
              >
                批准生效
              </Button>
              {(skillEditSource === "draft" ||
                skillEditSource === "approved") && (
                <Button
                  variant="danger"
                  onClick={() => void onDeleteSkill()}
                  disabled={skillBusy}
                >
                  删除
                </Button>
              )}
            </>
          )}
        </div>
        {skillMsg && <pre className="settings-msg">{skillMsg}</pre>}
      </Card>
    </div>
  );
}
