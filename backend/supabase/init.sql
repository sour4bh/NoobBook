-- NoobBook Database Initialization
-- Run this SQL in Supabase SQL Editor for fresh setup
-- Combines all migrations into a single file

-- ============================================================================
-- EXTENSIONS
-- ============================================================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

-- ============================================================================
-- USERS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email TEXT UNIQUE,
  role TEXT NOT NULL DEFAULT 'user',
  memory JSONB DEFAULT '{}'::jsonb,
  settings JSONB DEFAULT '{}'::jsonb,
  google_tokens JSONB DEFAULT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  CONSTRAINT valid_user_role CHECK (role IN ('admin', 'user'))
);

-- Backfill/migrate role column for existing installations
ALTER TABLE users ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'user';

-- Default user for single-user mode
INSERT INTO users (id, email, role, memory, settings)
VALUES (
  '00000000-0000-0000-0000-000000000001',
  'local@noobbook.local',
  'admin',
  '{}'::jsonb,
  '{}'::jsonb
) ON CONFLICT (id) DO NOTHING;

-- Ensure the default user is admin (for single-user mode)
UPDATE users
SET role = 'admin'
WHERE id = '00000000-0000-0000-0000-000000000001'
  AND role <> 'admin';

-- ============================================================================
-- OAUTH STATES TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS oauth_states (
  nonce TEXT PRIMARY KEY,
  provider TEXT NOT NULL,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at TIMESTAMPTZ NOT NULL,
  consumed_at TIMESTAMPTZ,
  CONSTRAINT oauth_states_provider_not_empty CHECK (length(trim(provider)) > 0),
  CONSTRAINT oauth_states_nonce_not_empty CHECK (length(trim(nonce)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_oauth_states_user_id ON oauth_states(user_id);
CREATE INDEX IF NOT EXISTS idx_oauth_states_expiry ON oauth_states(expires_at);
CREATE INDEX IF NOT EXISTS idx_oauth_states_unconsumed
  ON oauth_states(provider, user_id, expires_at)
  WHERE consumed_at IS NULL;

-- ============================================================================
-- PROJECTS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS projects (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES users(id) ON DELETE CASCADE DEFAULT '00000000-0000-0000-0000-000000000001',
  name TEXT NOT NULL,
  description TEXT,
  custom_prompt TEXT,
  memory JSONB DEFAULT '{}'::jsonb,
  costs JSONB DEFAULT '{
    "total_input_tokens": 0,
    "total_output_tokens": 0,
    "total_cost_usd": 0,
    "by_model": {}
  }'::jsonb,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  last_accessed TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_projects_user_id ON projects(user_id);
CREATE INDEX IF NOT EXISTS idx_projects_last_accessed ON projects(last_accessed DESC);

-- ============================================================================
-- SOURCES TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS sources (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  description TEXT,
  type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'uploaded',
  raw_file_path TEXT,
  processed_file_path TEXT,
  token_count INTEGER,
  page_count INTEGER,
  file_size BIGINT,
  embedding_info JSONB DEFAULT '{}'::jsonb,
  summary_info JSONB DEFAULT '{}'::jsonb,
  processing_info JSONB DEFAULT '{}'::jsonb,
  error_message TEXT,
  url TEXT,
  is_active BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sources_project_id ON sources(project_id);
CREATE INDEX IF NOT EXISTS idx_sources_status ON sources(status);
CREATE INDEX IF NOT EXISTS idx_sources_type ON sources(type);

-- ============================================================================
-- DATABASE CONNECTIONS (Account-level)
-- ============================================================================
CREATE TABLE IF NOT EXISTS database_connections (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  description TEXT,
  db_type TEXT NOT NULL,
  connection_uri TEXT NOT NULL,
  is_active BOOLEAN DEFAULT true,
  visible_to_all BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  CONSTRAINT valid_db_type CHECK (db_type IN ('postgresql', 'mysql')),
  CONSTRAINT name_not_empty CHECK (length(trim(name)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_database_connections_owner_user_id ON database_connections(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_database_connections_db_type ON database_connections(db_type);

-- Users allowed to use a database connection (for multi-user mode)
CREATE TABLE IF NOT EXISTS database_connection_users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  connection_id UUID NOT NULL REFERENCES database_connections(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(connection_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_database_connection_users_connection_id ON database_connection_users(connection_id);
CREATE INDEX IF NOT EXISTS idx_database_connection_users_user_id ON database_connection_users(user_id);

-- ============================================================================
-- MCP CONNECTIONS (Account-level)
-- ============================================================================
CREATE TABLE IF NOT EXISTS mcp_connections (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  description TEXT,
  server_url TEXT,
  transport TEXT NOT NULL DEFAULT 'sse',
  auth_type TEXT NOT NULL DEFAULT 'none',
  auth_config JSONB DEFAULT '{}'::jsonb,
  stdio_config JSONB DEFAULT '{}'::jsonb,
  tools_enabled BOOLEAN DEFAULT false,
  cached_tools JSONB DEFAULT NULL,
  tools_cached_at TIMESTAMPTZ DEFAULT NULL,
  is_active BOOLEAN DEFAULT true,
  visible_to_all BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  CONSTRAINT valid_transport CHECK (transport IN ('sse', 'stdio')),
  CONSTRAINT valid_auth_type CHECK (auth_type IN ('none', 'bearer', 'api_key', 'header')),
  CONSTRAINT mcp_name_not_empty CHECK (length(trim(name)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_mcp_connections_owner_user_id ON mcp_connections(owner_user_id);

-- Users allowed to use an MCP connection (for multi-user mode)
CREATE TABLE IF NOT EXISTS mcp_connection_users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  connection_id UUID NOT NULL REFERENCES mcp_connections(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(connection_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_mcp_connection_users_connection_id ON mcp_connection_users(connection_id);
CREATE INDEX IF NOT EXISTS idx_mcp_connection_users_user_id ON mcp_connection_users(user_id);

-- ============================================================================
-- CHATS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS chats (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  title TEXT NOT NULL DEFAULT 'New Chat',
  selected_source_ids UUID[] DEFAULT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chats_project_id ON chats(project_id);
CREATE INDEX IF NOT EXISTS idx_chats_updated_at ON chats(updated_at DESC);

-- ============================================================================
-- MESSAGES TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  chat_id UUID NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
  role TEXT NOT NULL,
  content JSONB NOT NULL,
  citations TEXT[] DEFAULT ARRAY[]::TEXT[],
  model TEXT,
  tokens_input INTEGER,
  tokens_output INTEGER,
  cost_usd NUMERIC(10, 6),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages(chat_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);

-- ============================================================================
-- CHUNKS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS chunks (
  id TEXT PRIMARY KEY,
  source_id UUID NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  content TEXT NOT NULL,
  page_number INTEGER,
  chunk_number INTEGER,
  token_count INTEGER,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chunks_source_id ON chunks(source_id);

-- ============================================================================
-- BACKGROUND TASKS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS background_tasks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  target_id UUID NOT NULL,
  target_type TEXT NOT NULL,
  task_type TEXT NOT NULL,
  status TEXT DEFAULT 'pending',
  progress INTEGER DEFAULT 0,
  message TEXT,
  error_message TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  completed_at TIMESTAMPTZ,
  started_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_tasks_target ON background_tasks(target_id, target_type);
CREATE INDEX IF NOT EXISTS idx_tasks_project_status ON background_tasks(project_id, status, created_at);
CREATE INDEX IF NOT EXISTS idx_tasks_user_status ON background_tasks(user_id, status, created_at);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON background_tasks(status);

-- ============================================================================
-- STUDIO SIGNALS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS studio_signals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  chat_id UUID NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
  message_id UUID REFERENCES messages(id) ON DELETE CASCADE,
  studio_item TEXT NOT NULL,
  direction TEXT NOT NULL,
  source_ids UUID[] DEFAULT ARRAY[]::UUID[],
  status TEXT DEFAULT 'pending',
  output_path TEXT,
  error_message TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_studio_signals_chat_id ON studio_signals(chat_id);

-- ============================================================================
-- BRAND ASSETS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS brand_assets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  description TEXT,
  asset_type TEXT NOT NULL,
  file_path TEXT NOT NULL,
  file_name TEXT NOT NULL,
  mime_type TEXT,
  file_size BIGINT,
  metadata JSONB DEFAULT '{}'::jsonb,
  is_primary BOOLEAN DEFAULT false,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  CONSTRAINT valid_asset_type CHECK (asset_type IN ('logo', 'icon', 'font', 'image')),
  CONSTRAINT name_not_empty CHECK (length(trim(name)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_brand_assets_user_id ON brand_assets(user_id);
CREATE INDEX IF NOT EXISTS idx_brand_assets_type ON brand_assets(asset_type);

-- ============================================================================
-- BRAND CONFIG TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS brand_config (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID UNIQUE NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  colors JSONB DEFAULT '{
    "primary": "#000000",
    "secondary": "#666666",
    "accent": "#0066CC",
    "background": "#FFFFFF",
    "text": "#1A1A1A",
    "custom": []
  }'::jsonb,
  typography JSONB DEFAULT '{
    "heading_font": "Inter",
    "body_font": "Inter",
    "heading_sizes": {"h1": "2.5rem", "h2": "2rem", "h3": "1.5rem"},
    "body_size": "1rem",
    "line_height": "1.6"
  }'::jsonb,
  spacing JSONB DEFAULT '{
    "base": "1rem",
    "small": "0.5rem",
    "large": "2rem",
    "section": "4rem"
  }'::jsonb,
  guidelines TEXT,
  best_practices JSONB DEFAULT '{"dos": [], "donts": []}'::jsonb,
  voice JSONB DEFAULT '{"tone": "professional", "personality": [], "keywords": []}'::jsonb,
  feature_settings JSONB DEFAULT '{
    "chat": true,
    "infographic": true,
    "presentation": true,
    "mind_map": false,
    "blog": true,
    "email": true,
    "ads_creative": true,
    "social_post": true,
    "prd": false,
    "business_report": true
  }'::jsonb,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- UPDATED_AT TRIGGER FUNCTION
-- ============================================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply triggers
DROP TRIGGER IF EXISTS update_users_updated_at ON users;
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_projects_updated_at ON projects;
CREATE TRIGGER update_projects_updated_at BEFORE UPDATE ON projects
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_sources_updated_at ON sources;
CREATE TRIGGER update_sources_updated_at BEFORE UPDATE ON sources
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_database_connections_updated_at ON database_connections;
CREATE TRIGGER update_database_connections_updated_at BEFORE UPDATE ON database_connections
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_mcp_connections_updated_at ON mcp_connections;
CREATE TRIGGER update_mcp_connections_updated_at BEFORE UPDATE ON mcp_connections
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_chats_updated_at ON chats;
CREATE TRIGGER update_chats_updated_at BEFORE UPDATE ON chats
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_background_tasks_updated_at ON background_tasks;
CREATE TRIGGER update_background_tasks_updated_at BEFORE UPDATE ON background_tasks
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_studio_signals_updated_at ON studio_signals;
CREATE TRIGGER update_studio_signals_updated_at BEFORE UPDATE ON studio_signals
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_brand_assets_updated_at ON brand_assets;
CREATE TRIGGER update_brand_assets_updated_at BEFORE UPDATE ON brand_assets
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_brand_config_updated_at ON brand_config;
CREATE TRIGGER update_brand_config_updated_at BEFORE UPDATE ON brand_config
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- HELPER FUNCTIONS
-- ============================================================================
CREATE OR REPLACE FUNCTION update_project_last_accessed(p_project_id UUID)
RETURNS VOID AS $$
BEGIN
  UPDATE projects SET last_accessed = NOW() WHERE id = p_project_id;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION get_project_stats(p_project_id UUID)
RETURNS JSON AS $$
DECLARE
  v_stats JSON;
BEGIN
  SELECT json_build_object(
    'total_sources', (SELECT COUNT(*) FROM sources WHERE project_id = p_project_id),
    'active_sources', (SELECT COUNT(*) FROM sources WHERE project_id = p_project_id AND is_active = true),
    'total_chats', (SELECT COUNT(*) FROM chats WHERE project_id = p_project_id),
    'total_messages', (
      SELECT COUNT(*) FROM messages m
      JOIN chats c ON c.id = m.chat_id
      WHERE c.project_id = p_project_id
    )
  ) INTO v_stats;
  RETURN v_stats;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION is_google_connected(p_user_id UUID)
RETURNS BOOLEAN AS $$
BEGIN
  RETURN EXISTS (
    SELECT 1 FROM users
    WHERE id = p_user_id
    AND google_tokens IS NOT NULL
    AND google_tokens->>'refresh_token' IS NOT NULL
  );
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- STORAGE BUCKETS
-- ============================================================================
INSERT INTO storage.buckets (id, name, public)
VALUES ('raw-files', 'raw-files', false)
ON CONFLICT (id) DO NOTHING;

INSERT INTO storage.buckets (id, name, public)
VALUES ('processed-files', 'processed-files', false)
ON CONFLICT (id) DO NOTHING;

INSERT INTO storage.buckets (id, name, public)
VALUES ('chunks', 'chunks', false)
ON CONFLICT (id) DO NOTHING;

INSERT INTO storage.buckets (id, name, public)
VALUES ('studio-outputs', 'studio-outputs', false)
ON CONFLICT (id) DO NOTHING;

INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
  'brand-assets',
  'brand-assets',
  false,
  52428800,
  ARRAY[
    'image/svg+xml',
    'image/png',
    'image/jpeg',
    'image/webp',
    'image/x-icon',
    'font/ttf',
    'font/otf',
    'font/woff',
    'font/woff2',
    'application/pdf'
  ]
) ON CONFLICT (id) DO NOTHING;

-- ============================================================================
-- STORAGE POLICIES
-- ============================================================================
DO $$
BEGIN
  -- Early bootstrap owner-prefix policies. NBB-010 replaces these below for
  -- project-owned buckets once workspace/project membership helpers exist.
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can upload raw files to own projects') THEN
    CREATE POLICY "Users can upload raw files to own projects" ON storage.objects FOR INSERT
    WITH CHECK (bucket_id = 'raw-files' AND auth.uid()::text = (storage.foldername(name))[1]);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can read raw files from own projects') THEN
    CREATE POLICY "Users can read raw files from own projects" ON storage.objects FOR SELECT
    USING (bucket_id = 'raw-files' AND auth.uid()::text = (storage.foldername(name))[1]);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can update raw files in own projects') THEN
    CREATE POLICY "Users can update raw files in own projects" ON storage.objects FOR UPDATE
    USING (bucket_id = 'raw-files' AND auth.uid()::text = (storage.foldername(name))[1]);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can delete raw files from own projects') THEN
    CREATE POLICY "Users can delete raw files from own projects" ON storage.objects FOR DELETE
    USING (bucket_id = 'raw-files' AND auth.uid()::text = (storage.foldername(name))[1]);
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can upload processed files to own projects') THEN
    CREATE POLICY "Users can upload processed files to own projects" ON storage.objects FOR INSERT
    WITH CHECK (bucket_id = 'processed-files' AND auth.uid()::text = (storage.foldername(name))[1]);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can read processed files from own projects') THEN
    CREATE POLICY "Users can read processed files from own projects" ON storage.objects FOR SELECT
    USING (bucket_id = 'processed-files' AND auth.uid()::text = (storage.foldername(name))[1]);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can update processed files in own projects') THEN
    CREATE POLICY "Users can update processed files in own projects" ON storage.objects FOR UPDATE
    USING (bucket_id = 'processed-files' AND auth.uid()::text = (storage.foldername(name))[1]);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can delete processed files from own projects') THEN
    CREATE POLICY "Users can delete processed files from own projects" ON storage.objects FOR DELETE
    USING (bucket_id = 'processed-files' AND auth.uid()::text = (storage.foldername(name))[1]);
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can upload chunks to own projects') THEN
    CREATE POLICY "Users can upload chunks to own projects" ON storage.objects FOR INSERT
    WITH CHECK (bucket_id = 'chunks' AND auth.uid()::text = (storage.foldername(name))[1]);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can read chunks from own projects') THEN
    CREATE POLICY "Users can read chunks from own projects" ON storage.objects FOR SELECT
    USING (bucket_id = 'chunks' AND auth.uid()::text = (storage.foldername(name))[1]);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can delete chunks from own projects') THEN
    CREATE POLICY "Users can delete chunks from own projects" ON storage.objects FOR DELETE
    USING (bucket_id = 'chunks' AND auth.uid()::text = (storage.foldername(name))[1]);
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can upload studio outputs to own projects') THEN
    CREATE POLICY "Users can upload studio outputs to own projects" ON storage.objects FOR INSERT
    WITH CHECK (bucket_id = 'studio-outputs' AND auth.uid()::text = (storage.foldername(name))[1]);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can read studio outputs from own projects') THEN
    CREATE POLICY "Users can read studio outputs from own projects" ON storage.objects FOR SELECT
    USING (bucket_id = 'studio-outputs' AND auth.uid()::text = (storage.foldername(name))[1]);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can update studio outputs in own projects') THEN
    CREATE POLICY "Users can update studio outputs in own projects" ON storage.objects FOR UPDATE
    USING (bucket_id = 'studio-outputs' AND auth.uid()::text = (storage.foldername(name))[1]);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can delete studio outputs from own projects') THEN
    CREATE POLICY "Users can delete studio outputs from own projects" ON storage.objects FOR DELETE
    USING (bucket_id = 'studio-outputs' AND auth.uid()::text = (storage.foldername(name))[1]);
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can upload brand assets to own account') THEN
    CREATE POLICY "Users can upload brand assets to own account" ON storage.objects FOR INSERT
    WITH CHECK (bucket_id = 'brand-assets' AND auth.uid()::text = (storage.foldername(name))[1]);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can read brand assets from own account') THEN
    CREATE POLICY "Users can read brand assets from own account" ON storage.objects FOR SELECT
    USING (bucket_id = 'brand-assets' AND auth.uid()::text = (storage.foldername(name))[1]);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can update brand assets in own account') THEN
    CREATE POLICY "Users can update brand assets in own account" ON storage.objects FOR UPDATE
    USING (bucket_id = 'brand-assets' AND auth.uid()::text = (storage.foldername(name))[1]);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Users can delete brand assets from own account') THEN
    CREATE POLICY "Users can delete brand assets from own account" ON storage.objects FOR DELETE
    USING (bucket_id = 'brand-assets' AND auth.uid()::text = (storage.foldername(name))[1]);
  END IF;
END $$;

-- ============================================================================
-- STUDIO JOBS TABLE (replaces studio_index.json)
-- ============================================================================
CREATE TABLE IF NOT EXISTS studio_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    job_type TEXT NOT NULL,
    source_id UUID,
    source_name TEXT,
    direction TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    progress TEXT,
    error_message TEXT,
    job_data JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_studio_jobs_project_id ON studio_jobs(project_id);
CREATE INDEX IF NOT EXISTS idx_studio_jobs_project_type ON studio_jobs(project_id, job_type);
CREATE INDEX IF NOT EXISTS idx_studio_jobs_status ON studio_jobs(status);

CREATE OR REPLACE FUNCTION update_studio_jobs_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_studio_jobs_updated_at ON studio_jobs;
CREATE TRIGGER trigger_studio_jobs_updated_at
    BEFORE UPDATE ON studio_jobs
    FOR EACH ROW
    EXECUTE FUNCTION update_studio_jobs_updated_at();

-- ============================================================================
-- WORKSPACE MEMBERSHIP (NBB-010)
-- ============================================================================
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'workspace_role') THEN
    CREATE TYPE workspace_role AS ENUM ('owner', 'admin', 'member');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'project_role') THEN
    CREATE TYPE project_role AS ENUM ('owner', 'editor', 'viewer');
  END IF;
END $$;

COMMENT ON COLUMN users.role IS 'Global instance role: admin or user. Workspace ownership lives in workspace_members.';

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

CREATE TABLE IF NOT EXISTS project_members (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role project_role NOT NULL DEFAULT 'viewer',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT unique_project_member UNIQUE (project_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_project_members_project_id ON project_members(project_id);
CREATE INDEX IF NOT EXISTS idx_project_members_user_id ON project_members(user_id);
CREATE INDEX IF NOT EXISTS idx_project_members_role ON project_members(role);

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

ALTER TABLE projects
  ADD COLUMN IF NOT EXISTS workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_projects_workspace_id ON projects(workspace_id);

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
ON CONFLICT (workspace_id, user_id) DO NOTHING;

UPDATE projects
SET workspace_id = workspaces.id
FROM workspaces
WHERE projects.workspace_id IS NULL
  AND workspaces.personal_owner_user_id = projects.user_id;

INSERT INTO project_members (project_id, user_id, role)
SELECT id, user_id, 'owner'::project_role
FROM projects
ON CONFLICT (project_id, user_id) DO NOTHING;

CREATE OR REPLACE FUNCTION user_has_workspace_access(
  p_workspace_id UUID,
  p_user_id UUID DEFAULT auth.uid()
)
RETURNS BOOLEAN AS $$
BEGIN
  RETURN EXISTS (
    SELECT 1 FROM workspace_members
    WHERE workspace_id = p_workspace_id AND user_id = p_user_id
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
    SELECT 1 FROM workspace_members
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
  WHERE project_id = p_project_id AND user_id = p_user_id;
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

-- Replace owner-prefix storage policies for project-owned buckets with
-- workspace/project-aware policies. Brand assets remain user-prefixed until
-- workspace brand ownership moves in NBB-1006.
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
