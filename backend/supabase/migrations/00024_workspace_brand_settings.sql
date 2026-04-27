-- Migration: Move Brand Kit from User-Level to Workspace-Level
-- Description: Brand config/assets become true workspace settings for NBB-1006.
-- Created: 2026-04-28

-- ============================================================================
-- BRAND CONFIG / ASSETS OWNERSHIP
-- ============================================================================

ALTER TABLE brand_config
  ADD COLUMN IF NOT EXISTS workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE;

ALTER TABLE brand_assets
  ADD COLUMN IF NOT EXISTS workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE;

UPDATE brand_config bc
SET workspace_id = w.id
FROM workspaces w
WHERE bc.workspace_id IS NULL
  AND bc.user_id = w.personal_owner_user_id;

UPDATE brand_assets ba
SET workspace_id = w.id
FROM workspaces w
WHERE ba.workspace_id IS NULL
  AND ba.user_id = w.personal_owner_user_id;

-- Safety fallback for rows owned by a user whose only workspace is not marked
-- personal. Existing NBB-1002 backfill creates personal workspaces, but this
-- keeps self-hosted drift from blocking the migration.
UPDATE brand_config bc
SET workspace_id = w.id
FROM workspaces w
WHERE bc.workspace_id IS NULL
  AND bc.user_id = w.owner_user_id;

UPDATE brand_assets ba
SET workspace_id = w.id
FROM workspaces w
WHERE ba.workspace_id IS NULL
  AND ba.user_id = w.owner_user_id;

DELETE FROM brand_config
WHERE id IN (
  SELECT id
  FROM (
    SELECT
      id,
      ROW_NUMBER() OVER (
        PARTITION BY workspace_id
        ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST, id
      ) AS row_number
    FROM brand_config
    WHERE workspace_id IS NOT NULL
  ) ranked
  WHERE ranked.row_number > 1
);

ALTER TABLE brand_config ALTER COLUMN workspace_id SET NOT NULL;
ALTER TABLE brand_assets ALTER COLUMN workspace_id SET NOT NULL;

DROP INDEX IF EXISTS idx_brand_assets_user_id;
DROP INDEX IF EXISTS idx_brand_config_user_id;

ALTER TABLE brand_config DROP CONSTRAINT IF EXISTS brand_config_user_id_key;
ALTER TABLE brand_config ADD CONSTRAINT brand_config_workspace_id_key UNIQUE (workspace_id);

CREATE INDEX IF NOT EXISTS idx_brand_assets_workspace_id ON brand_assets(workspace_id);
CREATE INDEX IF NOT EXISTS idx_brand_config_workspace_id ON brand_config(workspace_id);

DROP POLICY IF EXISTS "Users can view own brand assets" ON brand_assets;
DROP POLICY IF EXISTS "Users can insert own brand assets" ON brand_assets;
DROP POLICY IF EXISTS "Users can update own brand assets" ON brand_assets;
DROP POLICY IF EXISTS "Users can delete own brand assets" ON brand_assets;
DROP POLICY IF EXISTS "Users can view own brand config" ON brand_config;
DROP POLICY IF EXISTS "Users can insert own brand config" ON brand_config;
DROP POLICY IF EXISTS "Users can update own brand config" ON brand_config;
DROP POLICY IF EXISTS "Users can delete own brand config" ON brand_config;

CREATE POLICY "Workspace members can view brand assets"
ON brand_assets FOR SELECT
USING (user_has_workspace_access(workspace_id, auth.uid()));

CREATE POLICY "Workspace managers can insert brand assets"
ON brand_assets FOR INSERT
WITH CHECK (user_can_manage_workspace(workspace_id, auth.uid()));

CREATE POLICY "Workspace managers can update brand assets"
ON brand_assets FOR UPDATE
USING (user_can_manage_workspace(workspace_id, auth.uid()))
WITH CHECK (user_can_manage_workspace(workspace_id, auth.uid()));

CREATE POLICY "Workspace managers can delete brand assets"
ON brand_assets FOR DELETE
USING (user_can_manage_workspace(workspace_id, auth.uid()));

CREATE POLICY "Workspace members can view brand config"
ON brand_config FOR SELECT
USING (user_has_workspace_access(workspace_id, auth.uid()));

CREATE POLICY "Workspace managers can insert brand config"
ON brand_config FOR INSERT
WITH CHECK (user_can_manage_workspace(workspace_id, auth.uid()));

CREATE POLICY "Workspace managers can update brand config"
ON brand_config FOR UPDATE
USING (user_can_manage_workspace(workspace_id, auth.uid()))
WITH CHECK (user_can_manage_workspace(workspace_id, auth.uid()));

CREATE POLICY "Workspace managers can delete brand config"
ON brand_config FOR DELETE
USING (user_can_manage_workspace(workspace_id, auth.uid()));

ALTER TABLE brand_config DROP COLUMN IF EXISTS user_id;
ALTER TABLE brand_assets DROP COLUMN IF EXISTS user_id;

COMMENT ON TABLE brand_config IS 'Brand configuration per workspace (colors, typography, guidelines, voice)';
COMMENT ON TABLE brand_assets IS 'Brand assets (logos, icons, fonts, images) per workspace';

-- ============================================================================
-- STORAGE POLICY AND PATH HELPER
-- ============================================================================

DROP POLICY IF EXISTS "Users can upload brand assets to own projects" ON storage.objects;
DROP POLICY IF EXISTS "Users can read brand assets from own projects" ON storage.objects;
DROP POLICY IF EXISTS "Users can update brand assets in own projects" ON storage.objects;
DROP POLICY IF EXISTS "Users can delete brand assets from own projects" ON storage.objects;
DROP POLICY IF EXISTS "Users can upload brand assets to own account" ON storage.objects;
DROP POLICY IF EXISTS "Users can read brand assets from own account" ON storage.objects;
DROP POLICY IF EXISTS "Users can update brand assets in own account" ON storage.objects;
DROP POLICY IF EXISTS "Users can delete brand assets from own account" ON storage.objects;

CREATE POLICY "Workspace managers can upload brand assets"
ON storage.objects FOR INSERT
WITH CHECK (
  bucket_id = 'brand-assets' AND
  user_can_manage_workspace(NULLIF((storage.foldername(name))[1], '')::uuid, auth.uid())
);

CREATE POLICY "Workspace members can read brand assets"
ON storage.objects FOR SELECT
USING (
  bucket_id = 'brand-assets' AND
  user_has_workspace_access(NULLIF((storage.foldername(name))[1], '')::uuid, auth.uid())
);

CREATE POLICY "Workspace managers can update brand assets"
ON storage.objects FOR UPDATE
USING (
  bucket_id = 'brand-assets' AND
  user_can_manage_workspace(NULLIF((storage.foldername(name))[1], '')::uuid, auth.uid())
);

CREATE POLICY "Workspace managers can delete brand assets"
ON storage.objects FOR DELETE
USING (
  bucket_id = 'brand-assets' AND
  user_can_manage_workspace(NULLIF((storage.foldername(name))[1], '')::uuid, auth.uid())
);

CREATE OR REPLACE FUNCTION generate_brand_asset_path(
  p_workspace_id UUID,
  p_asset_id UUID,
  p_filename TEXT
)
RETURNS TEXT AS $$
BEGIN
  RETURN p_workspace_id || '/brand/' || p_asset_id || '/' || p_filename;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION generate_brand_asset_path(UUID, UUID, TEXT)
IS 'Generate storage path for brand assets: {workspace_id}/brand/{asset_id}/{filename}';
