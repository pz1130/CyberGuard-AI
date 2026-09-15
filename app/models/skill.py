"""Skill and Tool database models."""
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text, JSON,
    CheckConstraint, ForeignKey, LargeBinary, UniqueConstraint,
)
from app.core.database import Base
from app.core.time import utc_now


class Skill(Base):
    """Skill model for skill pool management."""

    __tablename__ = "skills"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(String(500), nullable=True)
    md_content = Column(Text, nullable=False)
    version = Column(String(20), default="1.0.0")
    category = Column(String(50), nullable=True)  # threat_intel, log_analysis, etc.
    permission_level = Column(String(20), default="medium")
    requires_approval = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True, nullable=False)
    metadata_json = Column(JSON, nullable=True)
    tags = Column(JSON, nullable=True)  # List[str]
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    def __repr__(self):
        return f"<Skill {self.name} (v{self.version})>"


class Tool(Base):
    """Tool model for tool pool management."""

    __tablename__ = "tools"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(String(500), nullable=True)
    md_content = Column(Text, nullable=True)  # now optional human notes/docs
    command_template = Column(Text, nullable=True)  # e.g. "nmap -sV -p {ports} {target}"
    input_schema_json = Column(Text, nullable=True)  # JSON Schema for params
    timeout_seconds = Column(Integer, default=60, server_default="60", nullable=False)
    required_permission = Column(String(100), nullable=True, index=True)
    version = Column(String(20), default="1.0.0")
    category = Column(String(50), nullable=True)
    permission_level = Column(String(20), default="medium")
    action_category = Column(String(20), nullable=True)   # observe|annotate|notify|contain_soft|contain_hard|remediate|mutate
    risk_tier = Column(String(20), nullable=True)         # critical|high|medium|low
    validation_command_template = Column(Text, nullable=True)
    verification_command_template = Column(Text, nullable=True)
    rollback_command_template = Column(Text, nullable=True)
    requires_approval = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True, nullable=False)
    metadata_json = Column(JSON, nullable=True)
    tags = Column(JSON, nullable=True)  # List[str]
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    # --- promoted skill script (NULL source_skill_id => an ordinary pool tool) ---
    source_skill_id = Column(
        Integer, ForeignKey("skills.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_script_path = Column(String(500), nullable=True)   # e.g. scripts/triage.py
    source_bundle_digest = Column(String(64), nullable=True)  # bundle sha256 at approval
    script_network = Column(String(20), nullable=True)        # none | allowlist
    script_network_allowlist = Column(JSON, nullable=True)    # List[str], phase 2

    __table_args__ = (
        CheckConstraint(
            "source_skill_id IS NULL OR ("
            "source_script_path IS NOT NULL AND source_bundle_digest IS NOT NULL "
            "AND script_network IS NOT NULL)",
            name="ck_tools_skill_script_shape",
        ),
    )

    def __repr__(self):
        return f"<Tool {self.name} (v{self.version})>"


class SkillFile(Base):
    """A bundled resource file belonging to a skill (references/, scripts/, assets/).

    Populated when a skill is imported from a zipped bundle. The whole file set
    of a skill is replaced on every re-import, so stale paths never linger.
    """

    __tablename__ = "skill_files"
    __table_args__ = (
        UniqueConstraint("skill_id", "path", name="uq_skill_files_skill_path"),
    )

    id = Column(Integer, primary_key=True, index=True)
    skill_id = Column(
        Integer,
        ForeignKey("skills.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    path = Column(String(500), nullable=False)  # relative to the skill root
    content_text = Column(Text, nullable=True)  # UTF-8 decodable files
    content_blob = Column(LargeBinary, nullable=True)  # everything else
    size_bytes = Column(Integer, nullable=False, default=0)
    mime = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    def __repr__(self):
        return f"<SkillFile {self.skill_id}:{self.path}>"
