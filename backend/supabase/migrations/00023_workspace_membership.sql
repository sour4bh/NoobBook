-- Migration: Workspace Membership and Private Project Sharing
-- Description: Add workspace/team ownership, private project roles, signed invites, and workspace-aware storage policies.
-- Created: 2026-04-27

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================================
-- ROLE TYPES
-- ============================================================================

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'workspace_role') THEN
    CREATE TYPE workspace_role AS ENUM ('owner', 'admin', 'member');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'project_role') THEN
    CREATE TYPE project_role AS ENUM ('owner', 'editor', 'viewer');
  END IF;
END $$;

COMMENT ON TYPE workspace_role IS 'Workspace role: owner/admin manage team and settings; member uses assigned projects';
COMMENT ON TYPE project_role IS 'Project role: owner manages sharing/delete; editor mutates content; viewer reads';

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'users'
      AND column_name = 'role'
      AND udt_name = 'user_role'
  ) THEN
    ALTER TABLE users ALTER COLUMN role DROP DEFAULT;
    ALTER TABLE users ALTER COLUMN role TYPE TEXT USING
      CASE
        WHEN role::text IN ('owner', 'admin') THEN 'admin'
        ELSE 'user'
      END;
  END IF;
END $$;

ALTER TABLE users DROP CONSTRAINT IF EXISTS valid_user_role;

UPDATE users
SET role = CASE
  WHEN role IN ('owner', 'admin') THEN 'admin'
  ELSE 'user'
END
WHERE role IS DISTINCT FROM CASE
  WHEN role IN ('owner', 'admin') THEN 'admin'
  ELSE 'user'
END;

ALTER TABLE users
  ALTER COLUMN role SET DEFAULT 'user',
  ALTER COLUMN role SET NOT NULL,
  ADD CONSTRAINT valid_user_role CHECK (role IN ('admin', 'user'));

COMMENT ON COLUMN users.role IS 'Global instance role: admin or user. Workspace ownership lives in workspace_members.';

-- ============================================================================
-- WORKSPACES
-- ============================================================================

CREATE TABLE IF NOT EXISTS workspaces (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  personal_owner_user_id UUID UNIQUE REFERENCES users(id) ON DELETE CASCADE,
  settings JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT workspaces_name_not_empty CHECK (length(trim(name)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_workspaces_owner_user_id ON workspaces(owner_user_id);

DROP TRIGGER IF EXISTS update_workspaces_updated_at ON workspaces;
CREATE TRIGGER update_workspaces_updated_at BEFORE UPDATE ON workspaces
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

COMMENT ON TABLE workspaces IS 'Workspace/team boundary. Public signup creates a personal workspace.';
COMMENT ON COLUMN workspaces.owner_user_id IS 'Primary workspace owner for bootstrap and display; membership rows are authoritative.';
COMMENT ON COLUMN workspaces.personal_owner_user_id IS 'Set only for auto-created personal workspaces.';
COMMENT ON COLUMN workspaces.settings IS 'Workspace-scoped settings JSONB; provider secrets live in workspace_provider_secrets.';

CREATE TABLE IF NOT EXISTS workspace_members (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role workspace_role NOT NULL DEFAULT 'member',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT unique_workspace_member UNIQUE (workspace_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_workspace_members_workspace_id ON workspace_members(workspace_id);
CREATE INDEX IF NOT EXISTS idx_workspace_members_user_id ON workspace_members(user_id);
CREATE INDEX IF NOT EXISTS idx_workspace_members_role ON workspace_members(role);

DROP TRIGGER IF EXISTS update_workspace_members_updated_at ON workspace_members;
CREATE TRIGGER update_workspace_members_updated_at BEFORE UPDATE ON workspace_members
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

COMMENT ON TABLE workspace_members IS 'Workspace team membership and workspace-settings role scope';
COMMENT ON COLUMN workspace_members.role IS 'owner/admin/member within the workspace';

CREATE TABLE IF NOT EXISTS workspace_invites (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  email TEXT NOT NULL,
  workspace_role workspace_role NOT NULL DEFAULT 'member',
  project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
  project_role project_role,
  token_hash TEXT NOT NULL UNIQUE,
  invited_by_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires_at TIMESTAMPTZ NOT NULL,
  accepted_at TIMESTAMPTZ,
  revoked_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT workspace_invites_email_not_empty CHECK (length(trim(email)) > 0),
  CONSTRAINT workspace_invites_project_role_requires_project CHECK (
    (project_id IS NULL AND project_role IS NULL)
    OR (project_id IS NOT NULL AND project_role IS NOT NULL)
  )
);

CREATE INDEX IF NOT EXISTS idx_workspace_invites_workspace_id ON workspace_invites(workspace_id);
CREATE INDEX IF NOT EXISTS idx_workspace_invites_email ON workspace_invites(lower(email));
CREATE INDEX IF NOT EXISTS idx_workspace_invites_project_id ON workspace_invites(project_id);
CREATE INDEX IF NOT EXISTS idx_workspace_invites_unaccepted ON workspace_invites(expires_at)
  WHERE accepted_at IS NULL AND revoked_at IS NULL;

COMMENT ON TABLE workspace_invites IS 'Signed one-time workspace invites; optional project role grants private project access on accept';

CREATE TABLE IF NOT EXISTS workspace_provider_secrets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  provider TEXT NOT NULL,
  key TEXT NOT NULL,
  encrypted_value TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT workspace_provider_secrets_key UNIQUE (workspace_id, provider, key),
  CONSTRAINT workspace_provider_secrets_provider_not_empty CHECK (length(trim(provider)) > 0),
  CONSTRAINT workspace_provider_secrets_key_not_empty CHECK (length(trim(key)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_workspace_provider_secrets_workspace_id ON workspace_provider_secrets(workspace_id);

DROP TRIGGER IF EXISTS update_workspace_provider_secrets_updated_at ON workspace_provider_secrets;
CREATE TRIGGER update_workspace_provider_secrets_updated_at BEFORE UPDATE ON workspace_provider_secrets
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

COMMENT ON TABLE workspace_provider_secrets IS 'Workspace-scoped encrypted provider/API secrets';

-- ============================================================================
-- PROJECT MEMBERSHIP
-- ============================================================================

ALTER TABLE projects
  ADD COLUMN IF NOT EXISTS workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_projects_workspace_id ON projects(workspace_id);

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'project_members'
      AND column_name = 'role'
      AND udt_name <> 'project_role'
  ) THEN
    ALTER TABLE project_members RENAME COLUMN role TO legacy_role;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS project_members (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role project_role NOT NULL DEFAULT 'viewer',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT unique_project_member UNIQUE (project_id, user_id)
);

ALTER TABLE project_members
  ADD COLUMN IF NOT EXISTS role project_role;

DO $$
DECLARE
  has_legacy_role BOOLEAN;
  has_can_edit BOOLEAN;
BEGIN
  SELECT EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'project_members'
      AND column_name = 'legacy_role'
  ) INTO has_legacy_role;

  SELECT EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'project_members'
      AND column_name = 'can_edit'
  ) INTO has_can_edit;

  IF has_legacy_role AND has_can_edit THEN
    EXECUTE $sql$
      UPDATE project_members
      SET role = CASE
        WHEN COALESCE(legacy_role::text, '') = 'owner' THEN 'owner'::project_role
        WHEN COALESCE(can_edit, false) THEN 'editor'::project_role
        ELSE 'viewer'::project_role
      END
      WHERE role IS NULL
    $sql$;
  ELSIF has_legacy_role THEN
    EXECUTE $sql$
      UPDATE project_members
      SET role = CASE
        WHEN COALESCE(legacy_role::text, '') = 'owner' THEN 'owner'::project_role
        WHEN COALESCE(legacy_role::text, '') IN ('admin', 'member') THEN 'editor'::project_role
        ELSE 'viewer'::project_role
      END
      WHERE role IS NULL
    $sql$;
  ELSE
    UPDATE project_members SET role = 'viewer'::project_role WHERE role IS NULL;
  END IF;
END $$;

ALTER TABLE project_members
  ALTER COLUMN role SET DEFAULT 'viewer',
  ALTER COLUMN role SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_project_members_project_id ON project_members(project_id);
CREATE INDEX IF NOT EXISTS idx_project_members_user_id ON project_members(user_id);
CREATE INDEX IF NOT EXISTS idx_project_members_role ON project_members(role);

DROP TRIGGER IF EXISTS update_project_members_updated_at ON project_members;
CREATE TRIGGER update_project_members_updated_at BEFORE UPDATE ON project_members
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

COMMENT ON TABLE project_members IS 'Private project membership. Workspace membership alone does not grant project access.';
COMMENT ON COLUMN project_members.role IS 'owner/editor/viewer within a private project';

-- ============================================================================
-- BACKFILL PERSONAL WORKSPACES AND OWNER MEMBERSHIPS
-- ============================================================================

INSERT INTO workspaces (name, owner_user_id, personal_owner_user_id)
SELECT
  COALESCE(NULLIF(split_part(email, '@', 1), ''), 'Personal') || '''s Workspace',
  id,
  id
FROM users
ON CONFLICT (personal_owner_user_id) DO NOTHING;

INSERT INTO workspace_members (workspace_id, user_id, role)
SELECT id, owner_user_id, 'owner'::workspace_role
FROM workspaces
ON CONFLICT (workspace_id, user_id) DO UPDATE
SET role = CASE
  WHEN workspace_members.role = 'owner' THEN workspace_members.role
  ELSE EXCLUDED.role
END;

UPDATE projects
SET workspace_id = workspaces.id
FROM workspaces
WHERE projects.workspace_id IS NULL
  AND workspaces.personal_owner_user_id = projects.user_id;

ALTER TABLE projects
  ALTER COLUMN workspace_id SET NOT NULL;

INSERT INTO project_members (project_id, user_id, role)
SELECT id, user_id, 'owner'::project_role
FROM projects
ON CONFLICT (project_id, user_id) DO UPDATE
SET role = CASE
  WHEN project_members.role = 'owner' THEN project_members.role
  ELSE EXCLUDED.role
END;

COMMENT ON COLUMN projects.workspace_id IS 'Owning workspace. Project visibility still requires explicit project_members membership.';

-- ============================================================================
-- MEMBERSHIP HELPERS
-- ============================================================================

CREATE OR REPLACE FUNCTION user_has_workspace_access(
  p_workspace_id UUID,
  p_user_id UUID DEFAULT auth.uid()
)
RETURNS BOOLEAN AS $$
BEGIN
  RETURN EXISTS (
    SELECT 1
    FROM workspace_members
    WHERE workspace_id = p_workspace_id
      AND user_id = p_user_id
  );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE OR REPLACE FUNCTION user_can_manage_workspace(
  p_workspace_id UUID,
  p_user_id UUID DEFAULT auth.uid()
)
RETURNS BOOLEAN AS $$
BEGIN
  RETURN EXISTS (
    SELECT 1
    FROM workspace_members
    WHERE workspace_id = p_workspace_id
      AND user_id = p_user_id
      AND role IN ('owner', 'admin')
  );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE OR REPLACE FUNCTION user_project_role(
  p_project_id UUID,
  p_user_id UUID DEFAULT auth.uid()
)
RETURNS project_role AS $$
DECLARE
  v_role project_role;
BEGIN
  SELECT role INTO v_role
  FROM project_members
  WHERE project_id = p_project_id
    AND user_id = p_user_id;

  RETURN v_role;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE OR REPLACE FUNCTION user_has_project_access(
  p_project_id UUID,
  p_user_id UUID DEFAULT auth.uid()
)
RETURNS BOOLEAN AS $$
BEGIN
  RETURN user_project_role(p_project_id, p_user_id) IS NOT NULL;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE OR REPLACE FUNCTION user_can_edit_project(
  p_project_id UUID,
  p_user_id UUID DEFAULT auth.uid()
)
RETURNS BOOLEAN AS $$
BEGIN
  RETURN user_project_role(p_project_id, p_user_id) IN ('owner', 'editor');
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE OR REPLACE FUNCTION user_can_manage_project(
  p_project_id UUID,
  p_user_id UUID DEFAULT auth.uid()
)
RETURNS BOOLEAN AS $$
BEGIN
  RETURN user_project_role(p_project_id, p_user_id) = 'owner';
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

COMMENT ON FUNCTION user_has_workspace_access(UUID, UUID) IS 'Check workspace membership';
COMMENT ON FUNCTION user_can_manage_workspace(UUID, UUID) IS 'Check workspace owner/admin role';
COMMENT ON FUNCTION user_project_role(UUID, UUID) IS 'Return private project role for a user';
COMMENT ON FUNCTION user_has_project_access(UUID, UUID) IS 'Check explicit project membership';
COMMENT ON FUNCTION user_can_edit_project(UUID, UUID) IS 'Check project owner/editor role';
COMMENT ON FUNCTION user_can_manage_project(UUID, UUID) IS 'Check project owner role';

-- ============================================================================
-- RLS POLICIES
-- ============================================================================

ALTER TABLE workspaces ENABLE ROW LEVEL SECURITY;
ALTER TABLE workspace_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE workspace_invites ENABLE ROW LEVEL SECURITY;
ALTER TABLE workspace_provider_secrets ENABLE ROW LEVEL SECURITY;
ALTER TABLE project_members ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Workspace members can view workspaces" ON workspaces;
CREATE POLICY "Workspace members can view workspaces"
  ON workspaces FOR SELECT
  USING (user_has_workspace_access(id, auth.uid()));

DROP POLICY IF EXISTS "Workspace owners can update workspaces" ON workspaces;
CREATE POLICY "Workspace owners can update workspaces"
  ON workspaces FOR UPDATE
  USING (user_can_manage_workspace(id, auth.uid()));

DROP POLICY IF EXISTS "Workspace members can view membership" ON workspace_members;
CREATE POLICY "Workspace members can view membership"
  ON workspace_members FOR SELECT
  USING (user_has_workspace_access(workspace_id, auth.uid()));

DROP POLICY IF EXISTS "Workspace owners can manage membership" ON workspace_members;
CREATE POLICY "Workspace owners can manage membership"
  ON workspace_members FOR ALL
  USING (user_can_manage_workspace(workspace_id, auth.uid()))
  WITH CHECK (user_can_manage_workspace(workspace_id, auth.uid()));

DROP POLICY IF EXISTS "Workspace owners can manage invites" ON workspace_invites;
CREATE POLICY "Workspace owners can manage invites"
  ON workspace_invites FOR ALL
  USING (user_can_manage_workspace(workspace_id, auth.uid()))
  WITH CHECK (user_can_manage_workspace(workspace_id, auth.uid()));

DROP POLICY IF EXISTS "Workspace owners can manage provider secrets" ON workspace_provider_secrets;
CREATE POLICY "Workspace owners can manage provider secrets"
  ON workspace_provider_secrets FOR ALL
  USING (user_can_manage_workspace(workspace_id, auth.uid()))
  WITH CHECK (user_can_manage_workspace(workspace_id, auth.uid()));

DROP POLICY IF EXISTS "Users can view project memberships" ON project_members;
DROP POLICY IF EXISTS "Project owners and admins can add members" ON project_members;
DROP POLICY IF EXISTS "Project owners can update members" ON project_members;
DROP POLICY IF EXISTS "Project owners can remove members" ON project_members;

CREATE POLICY "Project members can view membership"
  ON project_members FOR SELECT
  USING (user_has_project_access(project_id, auth.uid()));

CREATE POLICY "Project owners can manage membership"
  ON project_members FOR ALL
  USING (user_can_manage_project(project_id, auth.uid()))
  WITH CHECK (user_can_manage_project(project_id, auth.uid()));

DROP POLICY IF EXISTS "Users can view own projects" ON projects;
DROP POLICY IF EXISTS "Users can create own projects" ON projects;
DROP POLICY IF EXISTS "Users can update own projects" ON projects;
DROP POLICY IF EXISTS "Users can delete own projects" ON projects;

CREATE POLICY "Project members can view private projects"
  ON projects FOR SELECT
  USING (user_has_project_access(id, auth.uid()));

CREATE POLICY "Workspace members can create projects"
  ON projects FOR INSERT
  WITH CHECK (user_has_workspace_access(workspace_id, auth.uid()) AND user_id = auth.uid());

CREATE POLICY "Project editors can update private projects"
  ON projects FOR UPDATE
  USING (user_can_edit_project(id, auth.uid()));

CREATE POLICY "Project owners can delete private projects"
  ON projects FOR DELETE
  USING (user_can_manage_project(id, auth.uid()));

-- ============================================================================
-- PROJECT-OWNED TABLE RLS UPDATES
-- ============================================================================

DROP POLICY IF EXISTS "Users can view sources in own projects" ON sources;
DROP POLICY IF EXISTS "Users can view sources in accessible projects" ON sources;
CREATE POLICY "Project members can view sources"
  ON sources FOR SELECT
  USING (user_has_project_access(project_id, auth.uid()));

DROP POLICY IF EXISTS "Users can create sources in own projects" ON sources;
DROP POLICY IF EXISTS "Users can create sources in accessible projects" ON sources;
CREATE POLICY "Project editors can create sources"
  ON sources FOR INSERT
  WITH CHECK (user_can_edit_project(project_id, auth.uid()));

DROP POLICY IF EXISTS "Users can update sources in own projects" ON sources;
DROP POLICY IF EXISTS "Users can update sources in accessible projects" ON sources;
CREATE POLICY "Project editors can update sources"
  ON sources FOR UPDATE
  USING (user_can_edit_project(project_id, auth.uid()));

DROP POLICY IF EXISTS "Users can delete sources from own projects" ON sources;
DROP POLICY IF EXISTS "Users can delete sources in accessible projects" ON sources;
CREATE POLICY "Project editors can delete sources"
  ON sources FOR DELETE
  USING (user_can_edit_project(project_id, auth.uid()));

DROP POLICY IF EXISTS "Users can view chats in own projects" ON chats;
DROP POLICY IF EXISTS "Users can view chats in accessible projects" ON chats;
CREATE POLICY "Project members can view chats"
  ON chats FOR SELECT
  USING (user_has_project_access(project_id, auth.uid()));

DROP POLICY IF EXISTS "Users can create chats in own projects" ON chats;
DROP POLICY IF EXISTS "Users can create chats in accessible projects" ON chats;
CREATE POLICY "Project editors can create chats"
  ON chats FOR INSERT
  WITH CHECK (user_can_edit_project(project_id, auth.uid()));

DROP POLICY IF EXISTS "Users can update chats in own projects" ON chats;
DROP POLICY IF EXISTS "Users can update chats in accessible projects" ON chats;
CREATE POLICY "Project editors can update chats"
  ON chats FOR UPDATE
  USING (user_can_edit_project(project_id, auth.uid()));

DROP POLICY IF EXISTS "Users can delete chats from own projects" ON chats;
DROP POLICY IF EXISTS "Users can delete chats in accessible projects" ON chats;
CREATE POLICY "Project editors can delete chats"
  ON chats FOR DELETE
  USING (user_can_edit_project(project_id, auth.uid()));

DROP POLICY IF EXISTS "Users can view messages in own chats" ON messages;
CREATE POLICY "Project members can view messages"
  ON messages FOR SELECT
  USING (
    EXISTS (
      SELECT 1
      FROM chats
      WHERE chats.id = messages.chat_id
        AND user_has_project_access(chats.project_id, auth.uid())
    )
  );

DROP POLICY IF EXISTS "Users can create messages in own chats" ON messages;
CREATE POLICY "Project editors can create messages"
  ON messages FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1
      FROM chats
      WHERE chats.id = messages.chat_id
        AND user_can_edit_project(chats.project_id, auth.uid())
    )
  );

DROP POLICY IF EXISTS "Users can update messages in own chats" ON messages;
CREATE POLICY "Project editors can update messages"
  ON messages FOR UPDATE
  USING (
    EXISTS (
      SELECT 1
      FROM chats
      WHERE chats.id = messages.chat_id
        AND user_can_edit_project(chats.project_id, auth.uid())
    )
  );

DROP POLICY IF EXISTS "Users can delete messages from own chats" ON messages;
CREATE POLICY "Project editors can delete messages"
  ON messages FOR DELETE
  USING (
    EXISTS (
      SELECT 1
      FROM chats
      WHERE chats.id = messages.chat_id
        AND user_can_edit_project(chats.project_id, auth.uid())
    )
  );

DROP POLICY IF EXISTS "Users can view chunks from own sources" ON chunks;
CREATE POLICY "Project members can view chunks"
  ON chunks FOR SELECT
  USING (
    EXISTS (
      SELECT 1
      FROM sources
      WHERE sources.id = chunks.source_id
        AND user_has_project_access(sources.project_id, auth.uid())
    )
  );

DROP POLICY IF EXISTS "Users can create chunks for own sources" ON chunks;
CREATE POLICY "Project editors can create chunks"
  ON chunks FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1
      FROM sources
      WHERE sources.id = chunks.source_id
        AND user_can_edit_project(sources.project_id, auth.uid())
    )
  );

DROP POLICY IF EXISTS "Users can delete chunks from own sources" ON chunks;
CREATE POLICY "Project editors can delete chunks"
  ON chunks FOR DELETE
  USING (
    EXISTS (
      SELECT 1
      FROM sources
      WHERE sources.id = chunks.source_id
        AND user_can_edit_project(sources.project_id, auth.uid())
    )
  );

-- ============================================================================
-- WORKSPACE-AWARE PROJECT STORAGE PATHS
-- ============================================================================

UPDATE storage.objects AS obj
SET name = projects.workspace_id::text || substring(obj.name from position('/' in obj.name))
FROM projects
WHERE obj.bucket_id IN ('raw-files', 'processed-files', 'chunks', 'studio-outputs')
  AND split_part(obj.name, '/', 1) = projects.user_id::text
  AND split_part(obj.name, '/', 2) = projects.id::text
  AND projects.workspace_id IS NOT NULL;

UPDATE sources
SET raw_file_path = projects.workspace_id::text || substring(sources.raw_file_path from position('/' in sources.raw_file_path))
FROM projects
WHERE sources.project_id = projects.id
  AND sources.raw_file_path IS NOT NULL
  AND split_part(sources.raw_file_path, '/', 1) = projects.user_id::text
  AND split_part(sources.raw_file_path, '/', 2) = projects.id::text;

UPDATE sources
SET processed_file_path = projects.workspace_id::text || substring(sources.processed_file_path from position('/' in sources.processed_file_path))
FROM projects
WHERE sources.project_id = projects.id
  AND sources.processed_file_path IS NOT NULL
  AND split_part(sources.processed_file_path, '/', 1) = projects.user_id::text
  AND split_part(sources.processed_file_path, '/', 2) = projects.id::text;

CREATE OR REPLACE FUNCTION generate_raw_file_path(
  p_workspace_id UUID,
  p_project_id UUID,
  p_source_id UUID,
  p_filename TEXT
)
RETURNS TEXT AS $$
BEGIN
  RETURN p_workspace_id || '/' || p_project_id || '/' || p_source_id || '/' || p_filename;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION generate_processed_file_path(
  p_workspace_id UUID,
  p_project_id UUID,
  p_source_id UUID,
  p_filename TEXT
)
RETURNS TEXT AS $$
BEGIN
  RETURN p_workspace_id || '/' || p_project_id || '/' || p_source_id || '/' || p_filename;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION generate_chunk_file_path(
  p_workspace_id UUID,
  p_project_id UUID,
  p_source_id UUID,
  p_chunk_id TEXT
)
RETURNS TEXT AS $$
BEGIN
  RETURN p_workspace_id || '/' || p_project_id || '/' || p_source_id || '/' || p_chunk_id || '.txt';
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION generate_studio_output_path(
  p_workspace_id UUID,
  p_project_id UUID,
  p_job_type TEXT,
  p_job_id UUID,
  p_filename TEXT
)
RETURNS TEXT AS $$
BEGIN
  RETURN p_workspace_id || '/' || p_project_id || '/studio/' || p_job_type || '/' || p_job_id || '/' || p_filename;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION generate_ai_image_path(
  p_workspace_id UUID,
  p_project_id UUID,
  p_filename TEXT
)
RETURNS TEXT AS $$
BEGIN
  RETURN p_workspace_id || '/' || p_project_id || '/ai-images/' || p_filename;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION generate_raw_file_path(UUID, UUID, UUID, TEXT)
IS 'Generate raw file path: {workspace_id}/{project_id}/{source_id}/{filename}';
COMMENT ON FUNCTION generate_processed_file_path(UUID, UUID, UUID, TEXT)
IS 'Generate processed file path: {workspace_id}/{project_id}/{source_id}/{filename}';
COMMENT ON FUNCTION generate_chunk_file_path(UUID, UUID, UUID, TEXT)
IS 'Generate chunk file path: {workspace_id}/{project_id}/{source_id}/{chunk_id}.txt';
COMMENT ON FUNCTION generate_studio_output_path(UUID, UUID, TEXT, UUID, TEXT)
IS 'Generate studio output path: {workspace_id}/{project_id}/studio/{job_type}/{job_id}/{filename}';
COMMENT ON FUNCTION generate_ai_image_path(UUID, UUID, TEXT)
IS 'Generate generated analysis image path: {workspace_id}/{project_id}/ai-images/{filename}';

DROP POLICY IF EXISTS "Users can upload raw files to own projects" ON storage.objects;
DROP POLICY IF EXISTS "Users can read raw files from own projects" ON storage.objects;
DROP POLICY IF EXISTS "Users can update raw files from own projects" ON storage.objects;
DROP POLICY IF EXISTS "Users can update raw files in own projects" ON storage.objects;
DROP POLICY IF EXISTS "Users can delete raw files from own projects" ON storage.objects;

CREATE POLICY "Project editors can upload raw files"
  ON storage.objects FOR INSERT
  WITH CHECK (
    bucket_id = 'raw-files'
    AND user_can_edit_project(NULLIF((storage.foldername(name))[2], '')::uuid, auth.uid())
  );

CREATE POLICY "Project members can read raw files"
  ON storage.objects FOR SELECT
  USING (
    bucket_id = 'raw-files'
    AND user_has_project_access(NULLIF((storage.foldername(name))[2], '')::uuid, auth.uid())
  );

CREATE POLICY "Project editors can update raw files"
  ON storage.objects FOR UPDATE
  USING (
    bucket_id = 'raw-files'
    AND user_can_edit_project(NULLIF((storage.foldername(name))[2], '')::uuid, auth.uid())
  );

CREATE POLICY "Project editors can delete raw files"
  ON storage.objects FOR DELETE
  USING (
    bucket_id = 'raw-files'
    AND user_can_edit_project(NULLIF((storage.foldername(name))[2], '')::uuid, auth.uid())
  );

DROP POLICY IF EXISTS "Users can upload processed files to own projects" ON storage.objects;
DROP POLICY IF EXISTS "Users can read processed files from own projects" ON storage.objects;
DROP POLICY IF EXISTS "Users can update processed files in own projects" ON storage.objects;
DROP POLICY IF EXISTS "Users can delete processed files from own projects" ON storage.objects;

CREATE POLICY "Project editors can upload processed files"
  ON storage.objects FOR INSERT
  WITH CHECK (
    bucket_id = 'processed-files'
    AND user_can_edit_project(NULLIF((storage.foldername(name))[2], '')::uuid, auth.uid())
  );

CREATE POLICY "Project members can read processed files"
  ON storage.objects FOR SELECT
  USING (
    bucket_id = 'processed-files'
    AND user_has_project_access(NULLIF((storage.foldername(name))[2], '')::uuid, auth.uid())
  );

CREATE POLICY "Project editors can update processed files"
  ON storage.objects FOR UPDATE
  USING (
    bucket_id = 'processed-files'
    AND user_can_edit_project(NULLIF((storage.foldername(name))[2], '')::uuid, auth.uid())
  );

CREATE POLICY "Project editors can delete processed files"
  ON storage.objects FOR DELETE
  USING (
    bucket_id = 'processed-files'
    AND user_can_edit_project(NULLIF((storage.foldername(name))[2], '')::uuid, auth.uid())
  );

DROP POLICY IF EXISTS "Users can upload chunks to own projects" ON storage.objects;
DROP POLICY IF EXISTS "Users can read chunks from own projects" ON storage.objects;
DROP POLICY IF EXISTS "Users can delete chunks from own projects" ON storage.objects;

CREATE POLICY "Project editors can upload chunks"
  ON storage.objects FOR INSERT
  WITH CHECK (
    bucket_id = 'chunks'
    AND user_can_edit_project(NULLIF((storage.foldername(name))[2], '')::uuid, auth.uid())
  );

CREATE POLICY "Project members can read chunks"
  ON storage.objects FOR SELECT
  USING (
    bucket_id = 'chunks'
    AND user_has_project_access(NULLIF((storage.foldername(name))[2], '')::uuid, auth.uid())
  );

CREATE POLICY "Project editors can delete chunks"
  ON storage.objects FOR DELETE
  USING (
    bucket_id = 'chunks'
    AND user_can_edit_project(NULLIF((storage.foldername(name))[2], '')::uuid, auth.uid())
  );

DROP POLICY IF EXISTS "Users can upload studio outputs to own projects" ON storage.objects;
DROP POLICY IF EXISTS "Users can read studio outputs from own projects" ON storage.objects;
DROP POLICY IF EXISTS "Users can update studio outputs in own projects" ON storage.objects;
DROP POLICY IF EXISTS "Users can delete studio outputs from own projects" ON storage.objects;

CREATE POLICY "Project editors can upload studio outputs"
  ON storage.objects FOR INSERT
  WITH CHECK (
    bucket_id = 'studio-outputs'
    AND user_can_edit_project(NULLIF((storage.foldername(name))[2], '')::uuid, auth.uid())
  );

CREATE POLICY "Project members can read studio outputs"
  ON storage.objects FOR SELECT
  USING (
    bucket_id = 'studio-outputs'
    AND user_has_project_access(NULLIF((storage.foldername(name))[2], '')::uuid, auth.uid())
  );

CREATE POLICY "Project editors can update studio outputs"
  ON storage.objects FOR UPDATE
  USING (
    bucket_id = 'studio-outputs'
    AND user_can_edit_project(NULLIF((storage.foldername(name))[2], '')::uuid, auth.uid())
  );

CREATE POLICY "Project editors can delete studio outputs"
  ON storage.objects FOR DELETE
  USING (
    bucket_id = 'studio-outputs'
    AND user_can_edit_project(NULLIF((storage.foldername(name))[2], '')::uuid, auth.uid())
  );
