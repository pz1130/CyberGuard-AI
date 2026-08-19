import { useCallback, useEffect, useState } from "react";
import { useI18n } from "../../i18n/I18nProvider";
import type { SkillPublic } from "../../lib/types";

export function useSkillsSection() {
  const { t } = useI18n();
  const api = typeof window !== "undefined" ? window.cyberguard : undefined;

  const [skills, setSkills] = useState<SkillPublic[]>([]);
  const [skillDrafts, setSkillDrafts] = useState<SkillPublic[]>([]);
  const [skillDirs, setSkillDirs] = useState<{
    approved?: string;
    drafts?: string;
    builtin?: string;
  }>({});
  const [skillMsg, setSkillMsg] = useState<string | null>(null);
  const [skillBusy, setSkillBusy] = useState(false);
  const [skillName, setSkillName] = useState("");
  const [skillDesc, setSkillDesc] = useState("");
  const [skillBody, setSkillBody] = useState("");
  const [skillVersion, setSkillVersion] = useState("1.0.0");
  const [skillMode, setSkillMode] = useState("both");
  const [skillEditSource, setSkillEditSource] = useState<
    "new" | "draft" | "approved" | "builtin"
  >("new");
  const [skillSelected, setSkillSelected] = useState<string | null>(null);

  const loadSkills = useCallback(async () => {
    if (!api?.skillsList) return;
    try {
      const r = await api.skillsList();
      setSkills(r.skills || []);
      setSkillDrafts(r.drafts || []);
      setSkillDirs(r.dirs || {});
    } catch {
      setSkills([]);
      setSkillDrafts([]);
    }
  }, [api]);

  const resetSkillEditor = useCallback(() => {
    setSkillName("");
    setSkillDesc("");
    setSkillBody(
      "# SOP · my_skill\n\n1. Step one\n2. Step two\n\nConstraints:\n- Prefer read-only investigation.\n"
    );
    setSkillVersion("1.0.0");
    setSkillMode("both");
    setSkillEditSource("new");
    setSkillSelected(null);
    setSkillMsg(null);
  }, []);

  useEffect(() => {
    void loadSkills();
  }, [loadSkills]);

  const openSkill = useCallback(
    async (name: string, source?: string) => {
      if (!api?.skillsGet) {
        setSkillMsg("skills API unavailable");
        return;
      }
      setSkillBusy(true);
      setSkillMsg(null);
      try {
        const r = await api.skillsGet(name, source);
        if (!r.ok || !r.skill) {
          setSkillMsg(r.error || "load failed");
          return;
        }
        const s = r.skill;
        setSkillName(s.name);
        setSkillDesc(s.description || "");
        setSkillBody(s.body || "");
        setSkillVersion(s.version || "1.0.0");
        setSkillMode(s.mode || "both");
        setSkillEditSource(
          (s.source as "draft" | "approved" | "builtin") || "draft"
        );
        setSkillSelected(s.name);
      } catch (e) {
        setSkillMsg(String(e));
      } finally {
        setSkillBusy(false);
      }
    },
    [api]
  );

  const onSaveSkillDraft = async () => {
    if (!api?.skillsSaveDraft) {
      setSkillMsg("skills save unavailable");
      return;
    }
    if (!skillName.trim() || !skillBody.trim()) {
      setSkillMsg(t("settings.skills.needNameBody"));
      return;
    }
    setSkillBusy(true);
    setSkillMsg(null);
    try {
      const r = await api.skillsSaveDraft({
        name: skillName.trim(),
        description: skillDesc.trim(),
        body: skillBody,
        version: skillVersion.trim() || "1.0.0",
        mode: skillMode,
      });
      if (!r.ok) {
        setSkillMsg(r.error || "save failed");
        return;
      }
      setSkillEditSource("draft");
      setSkillSelected(r.skill?.name || skillName.trim());
      setSkillMsg(
        t("settings.skills.draftSaved", { name: r.skill?.name || "" }) +
          (r.warning
            ? t("settings.skills.draftSavedWarn", { warning: r.warning })
            : t("settings.skills.draftSavedHint"))
      );
      await loadSkills();
    } catch (e) {
      setSkillMsg(String(e));
    } finally {
      setSkillBusy(false);
    }
  };

  const onApproveSkill = async () => {
    if (!api?.skillsApprove || !skillName.trim()) return;
    setSkillBusy(true);
    setSkillMsg(null);
    try {
      // Ensure latest editor content is in drafts first
      if (skillEditSource === "new" || skillEditSource === "draft") {
        const saved = await api.skillsSaveDraft?.({
          name: skillName.trim(),
          description: skillDesc.trim(),
          body: skillBody,
          version: skillVersion.trim() || "1.0.0",
          mode: skillMode,
        });
        if (saved && saved.ok === false) {
          setSkillMsg(saved.error || "save draft failed");
          return;
        }
      }
      const r = await api.skillsApprove(skillName.trim());
      if (!r.ok) {
        setSkillMsg(r.error || "approve failed");
        return;
      }
      setSkillEditSource("approved");
      setSkillMsg(
        r.message || t("settings.skills.approved", { name: skillName })
      );
      await loadSkills();
    } catch (e) {
      setSkillMsg(String(e));
    } finally {
      setSkillBusy(false);
    }
  };

  const onDeleteSkill = async () => {
    if (!api?.skillsDelete || !skillName.trim()) return;
    const src =
      skillEditSource === "approved"
        ? "approved"
        : skillEditSource === "draft"
          ? "draft"
          : null;
    if (!src) {
      setSkillMsg(t("settings.skills.builtinNoDelete"));
      return;
    }
    if (
      !window.confirm(
        t("settings.skills.confirmDelete", { src, name: skillName })
      )
    )
      return;
    setSkillBusy(true);
    setSkillMsg(null);
    try {
      const r = await api.skillsDelete(skillName.trim(), src);
      if (!r.ok) {
        setSkillMsg(r.error || "delete failed");
        return;
      }
      setSkillMsg(
        t("settings.skills.deleted", { name: skillName, src })
      );
      resetSkillEditor();
      await loadSkills();
    } catch (e) {
      setSkillMsg(String(e));
    } finally {
      setSkillBusy(false);
    }
  };

  const onImportSkill = async () => {
    if (!api?.skillsImport || !api.pickFile) {
      setSkillMsg("import / file picker unavailable");
      return;
    }
    setSkillBusy(true);
    setSkillMsg(null);
    try {
      const picked = await api.pickFile({
        title: "Import skill Markdown",
        properties: ["openFile"],
      });
      if (!picked?.path || picked.canceled) {
        setSkillMsg("canceled");
        return;
      }
      const r = await api.skillsImport({ path: picked.path });
      if (!r.ok || !r.skill) {
        setSkillMsg(r.error || "import failed");
        return;
      }
      setSkillName(r.skill.name);
      setSkillDesc(r.skill.description || "");
      setSkillBody(r.skill.body || "");
      setSkillVersion(r.skill.version || "1.0.0");
      setSkillMode(r.skill.mode || "both");
      setSkillEditSource("draft");
      setSkillSelected(r.skill.name);
      setSkillMsg(
        t("settings.skills.imported", { name: r.skill.name }) +
          (r.warning
            ? t("settings.skills.draftSavedWarn", { warning: r.warning })
            : t("settings.skills.importedHint"))
      );
      await loadSkills();
    } catch (e) {
      setSkillMsg(String(e));
    } finally {
      setSkillBusy(false);
    }
  };

  const onForkSkill = async () => {
    if (!api?.skillsFork || !skillName.trim()) return;
    setSkillBusy(true);
    setSkillMsg(null);
    try {
      const r = await api.skillsFork(skillName.trim());
      if (!r.ok || !r.skill) {
        setSkillMsg(r.error || "fork failed");
        return;
      }
      setSkillName(r.skill.name);
      setSkillDesc(r.skill.description || "");
      setSkillBody(r.skill.body || "");
      setSkillVersion(r.skill.version || "1.0.0");
      setSkillMode(r.skill.mode || "both");
      setSkillEditSource("draft");
      setSkillSelected(r.skill.name);
      setSkillMsg(
        t("settings.skills.forked", { name: r.skill.name }) +
          (r.warning
            ? t("settings.skills.draftSavedWarn", { warning: r.warning })
            : t("settings.skills.forkedHint"))
      );
      await loadSkills();
    } catch (e) {
      setSkillMsg(String(e));
    } finally {
      setSkillBusy(false);
    }
  };

  const onRevealSkillDir = async (which: "approved" | "drafts") => {
    const p = which === "approved" ? skillDirs.approved : skillDirs.drafts;
    if (!p || !api?.showItemInFolder) {
      setSkillMsg("path unavailable");
      return;
    }
    try {
      await api.showItemInFolder(p);
    } catch (e) {
      setSkillMsg(String(e));
    }
  };

  return {
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
  };
}
export type SkillsSectionModel = ReturnType<typeof useSkillsSection>;
