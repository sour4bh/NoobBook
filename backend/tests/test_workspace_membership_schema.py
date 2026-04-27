from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "backend/supabase/migrations/00023_workspace_membership.sql"
BRAND_MIGRATION = ROOT / "backend/supabase/migrations/00024_workspace_brand_settings.sql"
INIT_SQL = ROOT / "backend/supabase/init.sql"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_workspace_membership_migration_defines_private_membership_contract() -> None:
    sql = _read(MIGRATION)

    for statement in [
        "CREATE TYPE workspace_role AS ENUM ('owner', 'admin', 'member')",
        "CREATE TYPE project_role AS ENUM ('owner', 'editor', 'viewer')",
        "CREATE TABLE IF NOT EXISTS workspaces",
        "CREATE TABLE IF NOT EXISTS workspace_members",
        "CREATE TABLE IF NOT EXISTS workspace_invites",
        "CREATE TABLE IF NOT EXISTS workspace_provider_secrets",
        "CREATE TABLE IF NOT EXISTS project_members",
        "ADD COLUMN IF NOT EXISTS workspace_id UUID REFERENCES workspaces(id)",
        "ALTER COLUMN workspace_id SET NOT NULL",
    ]:
        assert statement in sql

    assert "Workspace membership alone does not grant project access" in sql
    assert "user_has_project_access" in sql
    assert "user_can_edit_project" in sql
    assert "user_can_manage_project" in sql


def test_workspace_membership_migration_normalizes_legacy_roles() -> None:
    sql = _read(MIGRATION)

    assert "ALTER TABLE users ALTER COLUMN role TYPE TEXT" in sql
    assert "ADD CONSTRAINT valid_user_role CHECK (role IN ('admin', 'user'))" in sql
    assert "ALTER TABLE project_members RENAME COLUMN role TO legacy_role" in sql
    assert "WHEN COALESCE(legacy_role::text, '') = 'owner' THEN 'owner'::project_role" in sql
    assert "WHEN COALESCE(can_edit, false) THEN 'editor'::project_role" in sql


def test_workspace_membership_migration_backfills_personal_workspaces() -> None:
    sql = _read(MIGRATION)

    assert "INSERT INTO workspaces (name, owner_user_id, personal_owner_user_id)" in sql
    assert "INSERT INTO workspace_members (workspace_id, user_id, role)" in sql
    assert "UPDATE projects" in sql and "workspaces.personal_owner_user_id = projects.user_id" in sql
    assert "INSERT INTO project_members (project_id, user_id, role)" in sql
    assert "'owner'::workspace_role" in sql
    assert "'owner'::project_role" in sql


def test_workspace_storage_paths_are_workspace_project_aware() -> None:
    sql = _read(MIGRATION)
    init_sql = _read(INIT_SQL)

    for content in [sql, init_sql]:
        assert "p_workspace_id || '/' || p_project_id" in content
        assert "Project editors can upload raw files" in content
        assert "Project members can read raw files" in content
        assert "Project editors can upload studio outputs" in content
        assert "(storage.foldername(name))[2]" in content

    assert "SET name = projects.workspace_id::text" in sql
    assert "SET raw_file_path = projects.workspace_id::text" in sql
    assert "SET processed_file_path = projects.workspace_id::text" in sql


def test_brand_settings_are_workspace_scoped() -> None:
    sql = _read(BRAND_MIGRATION)
    init_sql = _read(INIT_SQL)

    for content in [sql, init_sql]:
        assert "brand_config_workspace_id_key UNIQUE (workspace_id)" in content
        assert "Workspace members can view brand config" in content
        assert "Workspace managers can update brand assets" in content
        assert "user_has_workspace_access(workspace_id, auth.uid())" in content
        assert "{workspace_id}/brand/{asset_id}/{filename}" in content

    assert "ALTER TABLE brand_config DROP COLUMN IF EXISTS user_id" in sql
    assert "ALTER TABLE brand_assets DROP COLUMN IF EXISTS user_id" in sql
