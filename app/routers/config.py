"""System configuration export/import router."""
import json
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependencies import get_db, require_role
from app.core.rbac import Role

router = APIRouter()


@router.post("/config/export")
async def export_config(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(Role.ADMIN)),
):
    """
    Export full system configuration as JSON (excluding chat history, audit logs, executions, approvals, token usage, backups).
    Includes: providers, users (no passwords), agents, skills, tools, prompt_templates, knowledge_bases (with documents),
    scheduled_tasks, webhooks, mcp_servers, mcp_tools, n8n_connections, env_vars, security_settings,
    master_agent_config, ocr_config, sso_config, sso_role_mapping, gov_frameworks, gov_requirements,
    gov_assessments, gov_req_assessments, gov_evidences.
    """
    from app.models import (
        User, AgentConfig, Skill, Tool, KnowledgeBase, Document, PromptTemplate,
        ScheduledTask, Webhook, MCPServer, MCPTool, N8NConnection, EnvVar,
        SecuritySettings, MasterAgentConfig, OcrConfig, SsoConfig, SsoRoleMapping,
        Framework, Requirement, ComplianceAssessment, RequirementAssessment, Evidence,
        Provider
    )

    # Export agents
    from sqlalchemy import select
    agents_result = await db.execute(select(AgentConfig))
    agents = [
        {k: v for k, v in {
            "id": a.id, "agent_name": a.agent_name, "backend_type": a.backend_type,
            "endpoint_url": a.endpoint_url, "description": a.description,
            "permission_level": a.permission_level,
        }.items()}
        for a in agents_result.scalars().all()
    ]

    # Export skills
    skills_result = await db.execute(select(Skill))
    skills = [
        {k: v for k, v in s.__dict__.items() if not k.startswith("_")}
        for s in skills_result.scalars().all()
    ]

    # Export tools
    tools_result = await db.execute(select(Tool))
    tools = [
        {k: v for k, v in t.__dict__.items() if not k.startswith("_")}
        for t in tools_result.scalars().all()
    ]

    # Export knowledge bases + documents
    kbs_result = await db.execute(select(KnowledgeBase))
    kbs = [
        {k: v for k, v in kb.__dict__.items() if not k.startswith("_")}
        for kb in kbs_result.scalars().all()
    ]
    docs_result = await db.execute(select(Document))
    documents = [
        {k: v for k, v in d.__dict__.items() if not k.startswith("_")}
        for d in docs_result.scalars().all()
    ]

    # Export providers (includes encrypted keys - restore requires matching ENCRYPTION_KEY)
    providers_result = await db.execute(select(Provider))
    providers = [
        {k: v for k, v in p.__dict__.items() if not k.startswith("_")}
        for p in providers_result.scalars().all()
    ]

    # Export users (no passwords)
    users_result = await db.execute(select(User))
    users = [
        {k: v for k, v in {
            "id": u.id, "username": u.username, "email": u.email,
            "role": u.role, "is_active": u.is_active, "full_name": u.full_name,
        }.items()}
        for u in users_result.scalars().all()
    ]

    # Export prompt templates
    prompts_result = await db.execute(select(PromptTemplate))
    prompt_templates = [
        {k: v for k, v in p.__dict__.items() if not k.startswith("_")}
        for p in prompts_result.scalars().all()
    ]

    # Export scheduled tasks
    schedules_result = await db.execute(select(ScheduledTask))
    scheduled_tasks = [
        {k: v for k, v in s.__dict__.items() if not k.startswith("_")}
        for s in schedules_result.scalars().all()
    ]

    # Export webhooks
    webhooks_result = await db.execute(select(Webhook))
    webhooks = [
        {k: v for k, v in w.__dict__.items() if not k.startswith("_")}
        for w in webhooks_result.scalars().all()
    ]

    # Export MCP
    mcp_servers_result = await db.execute(select(MCPServer))
    mcp_servers = [
        {k: v for k, v in s.__dict__.items() if not k.startswith("_")}
        for s in mcp_servers_result.scalars().all()
    ]
    mcp_tools_result = await db.execute(select(MCPTool))
    mcp_tools = [
        {k: v for k, v in t.__dict__.items() if not k.startswith("_")}
        for t in mcp_tools_result.scalars().all()
    ]

    # Export N8N
    n8n_result = await db.execute(select(N8NConnection))
    n8n_connections = [
        {k: v for k, v in n.__dict__.items() if not k.startswith("_")}
        for n in n8n_result.scalars().all()
    ]

    # Export env vars (encrypted)
    env_result = await db.execute(select(EnvVar))
    env_vars = [
        {k: v for k, v in e.__dict__.items() if not k.startswith("_")}
        for e in env_result.scalars().all()
    ]

    # Export security settings
    sec_result = await db.execute(select(SecuritySettings))
    security_settings = [
        {k: v for k, v in s.__dict__.items() if not k.startswith("_")}
        for s in sec_result.scalars().all()
    ]

    # Export master config
    mac_result = await db.execute(select(MasterAgentConfig))
    master_agent_config = [
        {k: v for k, v in m.__dict__.items() if not k.startswith("_")}
        for m in mac_result.scalars().all()
    ]

    # Export OCR
    ocr_result = await db.execute(select(OcrConfig))
    ocr_config = [
        {k: v for k, v in o.__dict__.items() if not k.startswith("_")}
        for o in ocr_result.scalars().all()
    ]

    # Export SSO
    sso_result = await db.execute(select(SsoConfig))
    sso_config = [
        {k: v for k, v in s.__dict__.items() if not k.startswith("_")}
        for s in sso_result.scalars().all()
    ]
    sso_role_result = await db.execute(select(SsoRoleMapping))
    sso_role_mapping = [
        {k: v for k, v in s.__dict__.items() if not k.startswith("_")}
        for s in sso_role_result.scalars().all()
    ]

    # Export governance
    frameworks_result = await db.execute(select(Framework))
    gov_frameworks = [
        {k: v for k, v in f.__dict__.items() if not k.startswith("_")}
        for f in frameworks_result.scalars().all()
    ]
    requirements_result = await db.execute(select(Requirement))
    gov_requirements = [
        {k: v for k, v in r.__dict__.items() if not k.startswith("_")}
        for r in requirements_result.scalars().all()
    ]
    assessments_result = await db.execute(select(ComplianceAssessment))
    gov_assessments = [
        {k: v for k, v in a.__dict__.items() if not k.startswith("_")}
        for a in assessments_result.scalars().all()
    ]
    req_assessments_result = await db.execute(select(RequirementAssessment))
    gov_req_assessments = [
        {k: v for k, v in r.__dict__.items() if not k.startswith("_")}
        for r in req_assessments_result.scalars().all()
    ]
    evidences_result = await db.execute(select(Evidence))
    gov_evidences = [
        {k: v for k, v in e.__dict__.items() if not k.startswith("_")}
        for e in evidences_result.scalars().all()
    ]

    from datetime import datetime, timezone
    config = {
        "version": "1.0.0",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "providers": providers,
        "users": users,
        "agents": agents,
        "skills": skills,
        "tools": tools,
        "prompt_templates": prompt_templates,
        "knowledge_bases": kbs,
        "documents": documents,
        "scheduled_tasks": scheduled_tasks,
        "webhooks": webhooks,
        "mcp_servers": mcp_servers,
        "mcp_tools": mcp_tools,
        "n8n_connections": n8n_connections,
        "env_vars": env_vars,
        "security_settings": security_settings,
        "master_agent_config": master_agent_config,
        "ocr_config": ocr_config,
        "sso_config": sso_config,
        "sso_role_mapping": sso_role_mapping,
        "gov_frameworks": gov_frameworks,
        "gov_requirements": gov_requirements,
        "gov_assessments": gov_assessments,
        "gov_req_assessments": gov_req_assessments,
        "gov_evidences": gov_evidences,
    }
    return config


@router.post("/config/import")
async def import_config(
    config: dict,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(Role.ADMIN)),
):
    """
    Import system configuration from JSON.
    Performs conflict resolution: skips items that already exist (by name/id).
    """
    required_keys = ["version", "agents", "skills", "tools", "knowledge_bases"]
    for key in required_keys:
        if key not in config:
            return {"status": "error", "detail": f"Missing required key: {key}"}

    imported = {
        "providers": 0, "users": 0, "agents": 0, "skills": 0, "tools": 0,
        "prompt_templates": 0, "knowledge_bases": 0, "documents": 0,
        "scheduled_tasks": 0, "webhooks": 0, "mcp_servers": 0, "mcp_tools": 0,
        "n8n_connections": 0, "env_vars": 0, "security_settings": 0,
        "master_agent_config": 0, "ocr_config": 0, "sso_config": 0, "sso_role_mapping": 0,
        "gov_frameworks": 0, "gov_requirements": 0, "gov_assessments": 0,
        "gov_req_assessments": 0, "gov_evidences": 0,
    }
    errors = []

    from sqlalchemy import select
    from app.models import (
        Provider, User, AgentConfig, Skill, Tool, PromptTemplate, ScheduledTask,
        Webhook, MCPServer, MCPTool, N8NConnection, EnvVar, SecuritySettings,
        MasterAgentConfig, OcrConfig, SsoConfig, SsoRoleMapping,
        Framework, Requirement, ComplianceAssessment, RequirementAssessment, Evidence,
        KnowledgeBase, Document
    )
    import bcrypt

    # Import agents
    from app.routers.agents import _validate_agent_payload
    from pydantic import BaseModel
    from typing import Optional as _Opt

    class _ImportAgentBody(BaseModel):
        kind: str = "external"
        backend_type: _Opt[str] = None
        endpoint_url: _Opt[str] = None
        llm_provider_id: _Opt[int] = None

    for agent_data in config.get("agents", []):
        try:
            existing = await db.execute(
                select(AgentConfig).where(AgentConfig.agent_name == agent_data.get("agent_name"))
            )
            if existing.scalar_one_or_none():
                continue  # skip existing
            # Validate the imported agent config
            _validate_agent_payload(_ImportAgentBody(
                kind=agent_data.get("kind", "external"),
                backend_type=agent_data.get("backend_type"),
                endpoint_url=agent_data.get("endpoint_url"),
                llm_provider_id=agent_data.get("llm_provider_id"),
            ))
            agent = AgentConfig(
                agent_name=agent_data.get("agent_name"),
                kind=agent_data.get("kind", "external"),
                backend_type=agent_data.get("backend_type", "custom"),
                endpoint_url=agent_data.get("endpoint_url"),
                description=agent_data.get("description"),
                permission_level=agent_data.get("permission_level", "medium"),
                llm_provider_id=agent_data.get("llm_provider_id"),
                is_active=True,
            )
            db.add(agent)
            imported["agents"] += 1
        except Exception as e:
            errors.append(f"agent {agent_data.get('agent_name')}: {e}")

    # Import skills
    for skill_data in config.get("skills", []):
        try:
            existing = await db.execute(
                select(Skill).where(Skill.name == skill_data.get("name"))
            )
            if existing.scalar_one_or_none():
                continue
            skill = Skill(
                name=skill_data.get("name"),
                description=skill_data.get("description"),
                md_content=skill_data.get("md_content", ""),
                version=skill_data.get("version", "1.0.0"),
                is_active=True,
            )
            db.add(skill)
            imported["skills"] += 1
        except Exception as e:
            errors.append(f"skill {skill_data.get('name')}: {e}")

    # Import tools
    for tool_data in config.get("tools", []):
        try:
            existing = await db.execute(
                select(Tool).where(Tool.name == tool_data.get("name"))
            )
            if existing.scalar_one_or_none():
                continue
            tool = Tool(
                name=tool_data.get("name"),
                description=tool_data.get("description"),
                md_content=tool_data.get("md_content", ""),
                permission_level=tool_data.get("permission_level", "medium"),
                requires_approval=tool_data.get("requires_approval", False),
                is_active=True,
            )
            db.add(tool)
            imported["tools"] += 1
        except Exception as e:
            errors.append(f"tool {tool_data.get('name')}: {e}")

    # Import knowledge bases
    for kb_data in config.get("knowledge_bases", []):
        try:
            existing = await db.execute(
                select(KnowledgeBase).where(KnowledgeBase.name == kb_data.get("name"))
            )
            if existing.scalar_one_or_none():
                continue
            kb = KnowledgeBase(
                name=kb_data.get("name"),
                description=kb_data.get("description"),
                embedding_model=kb_data.get("embedding_model", ""),
                rerank_model=kb_data.get("rerank_model", ""),
                is_active=True,
            )
            db.add(kb)
            imported["knowledge_bases"] += 1
        except Exception as e:
            errors.append(f"knowledge_base {kb_data.get('name')}: {e}")

    # Import documents (associated with kbs by kb_id; assume kbs imported first or exist)
    for doc_data in config.get("documents", []):
        try:
            existing = await db.execute(
                select(Document).where(Document.file_hash == doc_data.get("file_hash"))
            )
            if existing.scalar_one_or_none():
                continue
            doc = Document(
                kb_id=doc_data.get("kb_id"),
                filename=doc_data.get("filename"),
                content_chunks_json=doc_data.get("content_chunks_json"),
                file_hash=doc_data.get("file_hash"),
                file_size=doc_data.get("file_size"),
                mime_type=doc_data.get("mime_type"),
                metadata_json=doc_data.get("metadata_json"),
            )
            db.add(doc)
            imported["documents"] += 1
        except Exception as e:
            errors.append(f"document {doc_data.get('filename')}: {e}")

    # Import providers (encrypted keys preserved; requires matching ENCRYPTION_KEY on target system)
    for prov_data in config.get("providers", []):
        try:
            existing = await db.execute(
                select(Provider).where(Provider.name == prov_data.get("name"))
            )
            if existing.scalar_one_or_none():
                continue
            prov = Provider(
                name=prov_data.get("name"),
                provider_type=prov_data.get("provider_type", "openai"),
                api_key_encrypted=prov_data.get("api_key_encrypted"),
                base_url=prov_data.get("base_url"),
                api_version=prov_data.get("api_version"),
                models=prov_data.get("models"),
                is_active=prov_data.get("is_active", True),
                metadata_json=prov_data.get("metadata_json"),
            )
            db.add(prov)
            imported["providers"] += 1
        except Exception as e:
            errors.append(f"provider {prov_data.get('name')}: {e}")

    # Import users (no password; new users will need password reset or default)
    for user_data in config.get("users", []):
        try:
            existing = await db.execute(
                select(User).where(User.username == user_data.get("username"))
            )
            if existing.scalar_one_or_none():
                continue
            # Create with default password "imported-user" - admin should reset
            default_pass = "imported-user"
            hashed = bcrypt.hashpw(default_pass.encode(), bcrypt.gensalt()).decode()
            user = User(
                username=user_data.get("username"),
                email=user_data.get("email"),
                hashed_password=hashed,
                role=user_data.get("role", "viewer"),
                is_active=user_data.get("is_active", True),
                full_name=user_data.get("full_name"),
            )
            db.add(user)
            imported["users"] += 1
        except Exception as e:
            errors.append(f"user {user_data.get('username')}: {e}")

    # Import prompt templates
    for pt_data in config.get("prompt_templates", []):
        try:
            existing = await db.execute(
                select(PromptTemplate).where(PromptTemplate.name == pt_data.get("name"))
            )
            if existing.scalar_one_or_none():
                continue
            pt = PromptTemplate(
                name=pt_data.get("name"),
                description=pt_data.get("description"),
                content=pt_data.get("content", ""),
                category=pt_data.get("category", "general"),
                is_active=pt_data.get("is_active", True),
            )
            db.add(pt)
            imported["prompt_templates"] += 1
        except Exception as e:
            errors.append(f"prompt_template {pt_data.get('name')}: {e}")

    # Import scheduled tasks
    for st_data in config.get("scheduled_tasks", []):
        try:
            existing = await db.execute(
                select(ScheduledTask).where(ScheduledTask.name == st_data.get("name"))
            )
            if existing.scalar_one_or_none():
                continue
            st = ScheduledTask(
                name=st_data.get("name"),
                description=st_data.get("description"),
                task_type=st_data.get("task_type", "backup"),
                schedule_cron=st_data.get("schedule_cron"),
                is_active=st_data.get("is_active", True),
                target=st_data.get("target"),
                params_json=st_data.get("params_json"),
                retention_days=st_data.get("retention_days", 30),
            )
            db.add(st)
            imported["scheduled_tasks"] += 1
        except Exception as e:
            errors.append(f"scheduled_task {st_data.get('name')}: {e}")

    # Import webhooks
    for wh_data in config.get("webhooks", []):
        try:
            existing = await db.execute(
                select(Webhook).where(Webhook.name == wh_data.get("name"))
            )
            if existing.scalar_one_or_none():
                continue
            wh = Webhook(
                name=wh_data.get("name"),
                description=wh_data.get("description"),
                url=wh_data.get("url"),
                secret=wh_data.get("secret"),
                direction=wh_data.get("direction", "outgoing"),
                is_active=wh_data.get("is_active", True),
                metadata_json=wh_data.get("metadata_json"),
            )
            db.add(wh)
            imported["webhooks"] += 1
        except Exception as e:
            errors.append(f"webhook {wh_data.get('name')}: {e}")

    # Import MCP
    for srv_data in config.get("mcp_servers", []):
        try:
            existing = await db.execute(
                select(MCPServer).where(MCPServer.name == srv_data.get("name"))
            )
            if existing.scalar_one_or_none():
                continue
            srv = MCPServer(
                name=srv_data.get("name"),
                transport_type=srv_data.get("transport_type", "stdio"),
                command=srv_data.get("command"),
                args=srv_data.get("args"),
                env_vars_encrypted=srv_data.get("env_vars_encrypted"),
                url=srv_data.get("url"),
                auth_token_encrypted=srv_data.get("auth_token_encrypted"),
                headers_json=srv_data.get("headers_json"),
                description=srv_data.get("description"),
                is_active=srv_data.get("is_active", True),
                timeout_seconds=srv_data.get("timeout_seconds", 30),
                metadata_json=srv_data.get("metadata_json"),
            )
            db.add(srv)
            imported["mcp_servers"] += 1
        except Exception as e:
            errors.append(f"mcp_server {srv_data.get('name')}: {e}")

    for tool_data in config.get("mcp_tools", []):
        try:
            existing = await db.execute(
                select(MCPTool).where(MCPTool.tool_name == tool_data.get("tool_name"))
            )
            if existing.scalar_one_or_none():
                continue
            tool = MCPTool(
                server_id=tool_data.get("server_id"),
                tool_name=tool_data.get("tool_name"),
                description=tool_data.get("description"),
                input_schema_json=tool_data.get("input_schema_json"),
                category=tool_data.get("category"),
                is_active=tool_data.get("is_active", True),
                required_permission=tool_data.get("required_permission"),
            )
            db.add(tool)
            imported["mcp_tools"] += 1
        except Exception as e:
            errors.append(f"mcp_tool {tool_data.get('tool_name')}: {e}")

    # Import N8N
    for n8n_data in config.get("n8n_connections", []):
        try:
            existing = await db.execute(
                select(N8NConnection).where(N8NConnection.name == n8n_data.get("name"))
            )
            if existing.scalar_one_or_none():
                continue
            n8n = N8NConnection(
                name=n8n_data.get("name"),
                base_url=n8n_data.get("base_url"),
                api_key_encrypted=n8n_data.get("api_key_encrypted"),
                is_active=n8n_data.get("is_active", True),
                is_default=n8n_data.get("is_default", False),
                metadata_json=n8n_data.get("metadata_json"),
            )
            db.add(n8n)
            imported["n8n_connections"] += 1
        except Exception as e:
            errors.append(f"n8n_connection {n8n_data.get('name')}: {e}")

    # Import env vars (encrypted)
    for ev_data in config.get("env_vars", []):
        try:
            existing = await db.execute(
                select(EnvVar).where(EnvVar.key == ev_data.get("key"))
            )
            if existing.scalar_one_or_none():
                continue
            ev = EnvVar(
                key=ev_data.get("key"),
                value_encrypted=ev_data.get("value_encrypted"),
                value_type=ev_data.get("value_type", "text"),
                description=ev_data.get("description"),
                is_active=ev_data.get("is_active", True),
            )
            db.add(ev)
            imported["env_vars"] += 1
        except Exception as e:
            errors.append(f"env_var {ev_data.get('key')}: {e}")

    # Import security settings
    for ss_data in config.get("security_settings", []):
        try:
            # Only one row typically
            existing = await db.execute(select(SecuritySettings))
            if existing.scalar_one_or_none():
                continue
            ss = SecuritySettings(
                aes_key_rotation_days=ss_data.get("aes_key_rotation_days", 90),
                rbac_enabled=ss_data.get("rbac_enabled", True),
                audit_enabled=ss_data.get("audit_enabled", True),
                rate_limit_per_minute=ss_data.get("rate_limit_per_minute", 30),
                rate_limit_per_hour=ss_data.get("rate_limit_per_hour", 500),
                burst_limit=ss_data.get("burst_limit", 5),
                max_concurrent_requests=ss_data.get("max_concurrent_requests", 5),
            )
            db.add(ss)
            imported["security_settings"] += 1
        except Exception as e:
            errors.append(f"security_settings: {e}")

    # Import master agent config
    for mac_data in config.get("master_agent_config", []):
        try:
            existing = await db.execute(select(MasterAgentConfig))
            if existing.scalar_one_or_none():
                continue
            mac = MasterAgentConfig(
                llm_provider_id=mac_data.get("llm_provider_id"),
                llm_model=mac_data.get("llm_model"),
                system_prompt=mac_data.get("system_prompt"),
                temperature=mac_data.get("temperature", 0.7),
                max_tokens=mac_data.get("max_tokens"),
                context_compression_enabled=mac_data.get("context_compression_enabled", True),
                compression_model=mac_data.get("compression_model"),
                compression_max_tokens=mac_data.get("compression_max_tokens"),
                intent_parser_prompt=mac_data.get("intent_parser_prompt"),
                summarizer_prompt=mac_data.get("summarizer_prompt"),
                max_rounds=mac_data.get("max_rounds"),
                auto_approve_threshold=mac_data.get("auto_approve_threshold"),
                branding_logo=mac_data.get("branding_logo"),
                branding_company_name=mac_data.get("branding_company_name"),
            )
            db.add(mac)
            imported["master_agent_config"] += 1
        except Exception as e:
            errors.append(f"master_agent_config: {e}")

    # Import OCR
    for ocr_data in config.get("ocr_config", []):
        try:
            existing = await db.execute(select(OcrConfig))
            if existing.scalar_one_or_none():
                continue
            ocr = OcrConfig(
                enabled=ocr_data.get("enabled", True),
                tesseract_lang=ocr_data.get("tesseract_lang", "eng+chi_sim"),
                max_image_size_mb=ocr_data.get("max_image_size_mb", 10),
            )
            db.add(ocr)
            imported["ocr_config"] += 1
        except Exception as e:
            errors.append(f"ocr_config: {e}")

    # Import SSO
    for sso_data in config.get("sso_config", []):
        try:
            existing = await db.execute(select(SsoConfig))
            if existing.scalar_one_or_none():
                continue
            sso = SsoConfig(
                enabled=sso_data.get("enabled", False),
                provider=sso_data.get("provider", "azure"),
                tenant_id=sso_data.get("tenant_id"),
                client_id=sso_data.get("client_id"),
                redirect_uri=sso_data.get("redirect_uri"),
                metadata_json=sso_data.get("metadata_json"),
            )
            db.add(sso)
            imported["sso_config"] += 1
        except Exception as e:
            errors.append(f"sso_config: {e}")

    for srm_data in config.get("sso_role_mapping", []):
        try:
            existing = await db.execute(
                select(SsoRoleMapping).where(SsoRoleMapping.azure_group_id == srm_data.get("azure_group_id"))
            )
            if existing.scalar_one_or_none():
                continue
            srm = SsoRoleMapping(
                azure_group_id=srm_data.get("azure_group_id"),
                azure_group_name=srm_data.get("azure_group_name"),
                local_role=srm_data.get("local_role", "viewer"),
            )
            db.add(srm)
            imported["sso_role_mapping"] += 1
        except Exception as e:
            errors.append(f"sso_role_mapping: {e}")

    # Import governance
    for fw_data in config.get("gov_frameworks", []):
        try:
            existing = await db.execute(select(Framework).where(Framework.urn == fw_data.get("urn")))
            if existing.scalar_one_or_none():
                continue
            fw = Framework(
                urn=fw_data.get("urn"),
                name=fw_data.get("name"),
                version=fw_data.get("version"),
                description=fw_data.get("description"),
                is_active=fw_data.get("is_active", True),
                metadata_json=fw_data.get("metadata_json"),
            )
            db.add(fw)
            imported["gov_frameworks"] += 1
        except Exception as e:
            errors.append(f"gov_framework {fw_data.get('urn')}: {e}")

    for req_data in config.get("gov_requirements", []):
        try:
            existing = await db.execute(
                select(Requirement).where(Requirement.urn == req_data.get("urn"))
            )
            if existing.scalar_one_or_none():
                continue
            req = Requirement(
                framework_id=req_data.get("framework_id"),
                urn=req_data.get("urn"),
                name=req_data.get("name"),
                description=req_data.get("description"),
                category=req_data.get("category"),
                priority=req_data.get("priority", "medium"),
                evidence_types=req_data.get("evidence_types"),
                metadata_json=req_data.get("metadata_json"),
            )
            db.add(req)
            imported["gov_requirements"] += 1
        except Exception as e:
            errors.append(f"gov_requirement {req_data.get('urn')}: {e}")

    for ass_data in config.get("gov_assessments", []):
        try:
            existing = await db.execute(
                select(ComplianceAssessment).where(ComplianceAssessment.name == ass_data.get("name"))
            )
            if existing.scalar_one_or_none():
                continue
            ass = ComplianceAssessment(
                framework_id=ass_data.get("framework_id"),
                name=ass_data.get("name"),
                description=ass_data.get("description"),
                scope=ass_data.get("scope"),
                status=ass_data.get("status", "draft"),
                metadata_json=ass_data.get("metadata_json"),
            )
            db.add(ass)
            imported["gov_assessments"] += 1
        except Exception as e:
            errors.append(f"gov_assessment {ass_data.get('name')}: {e}")

    for ra_data in config.get("gov_req_assessments", []):
        try:
            existing = await db.execute(
                select(RequirementAssessment).where(
                    RequirementAssessment.assessment_id == ra_data.get("assessment_id"),
                    RequirementAssessment.requirement_id == ra_data.get("requirement_id"),
                )
            )
            if existing.scalar_one_or_none():
                continue
            ra = RequirementAssessment(
                assessment_id=ra_data.get("assessment_id"),
                requirement_id=ra_data.get("requirement_id"),
                status=ra_data.get("status", "pending"),
                score=ra_data.get("score"),
                notes=ra_data.get("notes"),
                metadata_json=ra_data.get("metadata_json"),
            )
            db.add(ra)
            imported["gov_req_assessments"] += 1
        except Exception as e:
            errors.append(f"gov_req_assessment: {e}")

    for ev_data in config.get("gov_evidences", []):
        try:
            existing = await db.execute(
                select(Evidence).where(Evidence.name == ev_data.get("name"))
            )
            if existing.scalar_one_or_none():
                continue
            ev = Evidence(
                req_assessment_id=ev_data.get("req_assessment_id"),
                name=ev_data.get("name"),
                description=ev_data.get("description"),
                content_type=ev_data.get("content_type"),
                content=ev_data.get("content"),
                metadata_json=ev_data.get("metadata_json"),
            )
            db.add(ev)
            imported["gov_evidences"] += 1
        except Exception as e:
            errors.append(f"gov_evidence {ev_data.get('name')}: {e}")

    await db.commit()

    return {
        "status": "ok",
        "detail": "Import completed",
        "imported": imported,
        "errors": errors if errors else None,
    }
