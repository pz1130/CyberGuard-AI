import type { ReactElement } from "react";
import { useI18n } from "../../i18n/I18nProvider";
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
  const { t } = useI18n();

  const catalogSummary =
    t("settings.skills.catalog") +
    (skills.length ? ` · ${skills.length}` : "");
  const draftsSummary =
    t("settings.skills.drafts") +
    (skillDrafts.length ? ` · ${skillDrafts.length}` : "");

  return (
    <div className="settings-detail">
      <Card>
        <h3 className="settings-card-title">{t("settings.skills.title")}</h3>
        <p className="settings-hint">
          {t("settings.skills.hintLead")}
          <strong>{t("settings.skills.approveWord")}</strong>
          {t("settings.skills.hintMid")}
          <code className="mono">load_skill</code>
          {t("settings.skills.hintTail")}
        </p>
        <div className="settings-actions" style={{ marginTop: 0 }}>
          <Button
            variant="secondary"
            onClick={resetSkillEditor}
            disabled={skillBusy}
          >
            {t("settings.skills.new")}
          </Button>
          <Button
            variant="ghost"
            onClick={() => void onImportSkill()}
            disabled={skillBusy}
          >
            {t("settings.skills.importMd")}
          </Button>
          <Button
            variant="ghost"
            onClick={() => void onRevealSkillDir("drafts")}
          >
            {t("settings.skills.openDrafts")}
          </Button>
          <Button
            variant="ghost"
            onClick={() => void onRevealSkillDir("approved")}
          >
            {t("settings.skills.openApproved")}
          </Button>
        </div>
      </Card>

      <Disclosure summary={catalogSummary} defaultOpen>
        <div className="settings-list">
          {skills.length === 0 && (
            <p className="settings-hint">{t("settings.skills.catalogEmpty")}</p>
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
                {s.readonly ? t("settings.skills.readonly") : ""}
              </span>
              <div className="mono-xs">{s.description}</div>
            </button>
          ))}
        </div>
      </Disclosure>

      <Disclosure summary={draftsSummary}>
        <div className="settings-list">
          {skillDrafts.length === 0 && (
            <p className="settings-hint">{t("settings.skills.draftsEmpty")}</p>
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
          {t("settings.skills.editor")}{" "}
          <span className="pill">{skillEditSource}</span>
        </h3>
        <Field label={t("settings.skills.nameLabel")}>
          <input
            className="data-input"
            value={skillName}
            onChange={(e) => setSkillName(e.target.value)}
            disabled={skillBusy || skillEditSource === "builtin"}
            placeholder="my_custom_sop"
          />
        </Field>
        <Field label={t("settings.skills.descLabel")}>
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
        <Field label={t("settings.skills.bodyLabel")}>
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
              {t("settings.skills.fork")}
            </Button>
          ) : (
            <>
              <Button
                variant="secondary"
                onClick={() => void onSaveSkillDraft()}
                disabled={skillBusy}
              >
                {t("settings.skills.saveDraft")}
              </Button>
              <Button
                variant="primary"
                onClick={() => void onApproveSkill()}
                disabled={skillBusy}
              >
                {t("settings.skills.approve")}
              </Button>
              {(skillEditSource === "draft" ||
                skillEditSource === "approved") && (
                <Button
                  variant="danger"
                  onClick={() => void onDeleteSkill()}
                  disabled={skillBusy}
                >
                  {t("settings.skills.delete")}
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
