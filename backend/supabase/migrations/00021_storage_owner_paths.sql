-- Migration: Owner-prefixed storage object paths
-- Description: Align source and studio storage keys with storage.objects policies.
-- Created: 2026-04-27

-- Existing runtime paths used project_id as the first segment for source,
-- chunk, studio, and generated image objects. Hosted storage policies expect
-- auth.uid() as the first segment, so prefix existing names when their first
-- segment is a known project id.
UPDATE storage.objects AS obj
SET name = projects.user_id::text || '/' || obj.name
FROM projects
WHERE obj.bucket_id IN ('raw-files', 'processed-files', 'chunks', 'studio-outputs')
  AND split_part(obj.name, '/', 1) = projects.id::text;

UPDATE sources
SET raw_file_path = projects.user_id::text || '/' || sources.raw_file_path
FROM projects
WHERE sources.project_id = projects.id
  AND sources.raw_file_path IS NOT NULL
  AND split_part(sources.raw_file_path, '/', 1) = sources.project_id::text;

UPDATE sources
SET processed_file_path = projects.user_id::text || '/' || sources.processed_file_path
FROM projects
WHERE sources.project_id = projects.id
  AND sources.processed_file_path IS NOT NULL
  AND split_part(sources.processed_file_path, '/', 1) = sources.project_id::text;

-- Remove the permissive self-hosted policies and recreate first-folder owner
-- checks for every bucket. Backend service-role access still bypasses RLS, so
-- route guards remain the primary application barrier.
DROP POLICY IF EXISTS "Allow all on raw-files" ON storage.objects;
DROP POLICY IF EXISTS "Allow all on processed-files" ON storage.objects;
DROP POLICY IF EXISTS "Allow all on chunks" ON storage.objects;
DROP POLICY IF EXISTS "Allow all on studio-outputs" ON storage.objects;
DROP POLICY IF EXISTS "Allow all on brand-assets" ON storage.objects;

DROP POLICY IF EXISTS "Users can upload raw files to own projects" ON storage.objects;
DROP POLICY IF EXISTS "Users can read raw files from own projects" ON storage.objects;
DROP POLICY IF EXISTS "Users can update raw files in own projects" ON storage.objects;
DROP POLICY IF EXISTS "Users can delete raw files from own projects" ON storage.objects;

CREATE POLICY "Users can upload raw files to own projects"
ON storage.objects FOR INSERT
WITH CHECK (
  bucket_id = 'raw-files' AND
  auth.uid()::text = (storage.foldername(name))[1]
);

CREATE POLICY "Users can read raw files from own projects"
ON storage.objects FOR SELECT
USING (
  bucket_id = 'raw-files' AND
  auth.uid()::text = (storage.foldername(name))[1]
);

CREATE POLICY "Users can update raw files in own projects"
ON storage.objects FOR UPDATE
USING (
  bucket_id = 'raw-files' AND
  auth.uid()::text = (storage.foldername(name))[1]
);

CREATE POLICY "Users can delete raw files from own projects"
ON storage.objects FOR DELETE
USING (
  bucket_id = 'raw-files' AND
  auth.uid()::text = (storage.foldername(name))[1]
);

DROP POLICY IF EXISTS "Users can upload processed files to own projects" ON storage.objects;
DROP POLICY IF EXISTS "Users can read processed files from own projects" ON storage.objects;
DROP POLICY IF EXISTS "Users can update processed files in own projects" ON storage.objects;
DROP POLICY IF EXISTS "Users can delete processed files from own projects" ON storage.objects;

CREATE POLICY "Users can upload processed files to own projects"
ON storage.objects FOR INSERT
WITH CHECK (
  bucket_id = 'processed-files' AND
  auth.uid()::text = (storage.foldername(name))[1]
);

CREATE POLICY "Users can read processed files from own projects"
ON storage.objects FOR SELECT
USING (
  bucket_id = 'processed-files' AND
  auth.uid()::text = (storage.foldername(name))[1]
);

CREATE POLICY "Users can update processed files in own projects"
ON storage.objects FOR UPDATE
USING (
  bucket_id = 'processed-files' AND
  auth.uid()::text = (storage.foldername(name))[1]
);

CREATE POLICY "Users can delete processed files from own projects"
ON storage.objects FOR DELETE
USING (
  bucket_id = 'processed-files' AND
  auth.uid()::text = (storage.foldername(name))[1]
);

DROP POLICY IF EXISTS "Users can upload chunks to own projects" ON storage.objects;
DROP POLICY IF EXISTS "Users can read chunks from own projects" ON storage.objects;
DROP POLICY IF EXISTS "Users can delete chunks from own projects" ON storage.objects;

CREATE POLICY "Users can upload chunks to own projects"
ON storage.objects FOR INSERT
WITH CHECK (
  bucket_id = 'chunks' AND
  auth.uid()::text = (storage.foldername(name))[1]
);

CREATE POLICY "Users can read chunks from own projects"
ON storage.objects FOR SELECT
USING (
  bucket_id = 'chunks' AND
  auth.uid()::text = (storage.foldername(name))[1]
);

CREATE POLICY "Users can delete chunks from own projects"
ON storage.objects FOR DELETE
USING (
  bucket_id = 'chunks' AND
  auth.uid()::text = (storage.foldername(name))[1]
);

DROP POLICY IF EXISTS "Users can upload studio outputs to own projects" ON storage.objects;
DROP POLICY IF EXISTS "Users can read studio outputs from own projects" ON storage.objects;
DROP POLICY IF EXISTS "Users can update studio outputs in own projects" ON storage.objects;
DROP POLICY IF EXISTS "Users can delete studio outputs from own projects" ON storage.objects;

CREATE POLICY "Users can upload studio outputs to own projects"
ON storage.objects FOR INSERT
WITH CHECK (
  bucket_id = 'studio-outputs' AND
  auth.uid()::text = (storage.foldername(name))[1]
);

CREATE POLICY "Users can read studio outputs from own projects"
ON storage.objects FOR SELECT
USING (
  bucket_id = 'studio-outputs' AND
  auth.uid()::text = (storage.foldername(name))[1]
);

CREATE POLICY "Users can update studio outputs in own projects"
ON storage.objects FOR UPDATE
USING (
  bucket_id = 'studio-outputs' AND
  auth.uid()::text = (storage.foldername(name))[1]
);

CREATE POLICY "Users can delete studio outputs from own projects"
ON storage.objects FOR DELETE
USING (
  bucket_id = 'studio-outputs' AND
  auth.uid()::text = (storage.foldername(name))[1]
);

DROP POLICY IF EXISTS "Users can upload brand assets to own projects" ON storage.objects;
DROP POLICY IF EXISTS "Users can read brand assets from own projects" ON storage.objects;
DROP POLICY IF EXISTS "Users can update brand assets in own projects" ON storage.objects;
DROP POLICY IF EXISTS "Users can delete brand assets from own projects" ON storage.objects;
DROP POLICY IF EXISTS "Users can upload brand assets to own account" ON storage.objects;
DROP POLICY IF EXISTS "Users can read brand assets from own account" ON storage.objects;
DROP POLICY IF EXISTS "Users can update brand assets in own account" ON storage.objects;
DROP POLICY IF EXISTS "Users can delete brand assets from own account" ON storage.objects;

CREATE POLICY "Users can upload brand assets to own account"
ON storage.objects FOR INSERT
WITH CHECK (
  bucket_id = 'brand-assets' AND
  auth.uid()::text = (storage.foldername(name))[1]
);

CREATE POLICY "Users can read brand assets from own account"
ON storage.objects FOR SELECT
USING (
  bucket_id = 'brand-assets' AND
  auth.uid()::text = (storage.foldername(name))[1]
);

CREATE POLICY "Users can update brand assets in own account"
ON storage.objects FOR UPDATE
USING (
  bucket_id = 'brand-assets' AND
  auth.uid()::text = (storage.foldername(name))[1]
);

CREATE POLICY "Users can delete brand assets from own account"
ON storage.objects FOR DELETE
USING (
  bucket_id = 'brand-assets' AND
  auth.uid()::text = (storage.foldername(name))[1]
);

CREATE OR REPLACE FUNCTION generate_chunk_file_path(
  p_user_id UUID,
  p_project_id UUID,
  p_source_id UUID,
  p_chunk_id TEXT
)
RETURNS TEXT AS $$
BEGIN
  RETURN p_user_id || '/' || p_project_id || '/' || p_source_id || '/' || p_chunk_id || '.txt';
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION generate_chunk_file_path(UUID, UUID, UUID, TEXT)
IS 'Generate storage path for chunk files: {user_id}/{project_id}/{source_id}/{chunk_id}.txt';

DROP FUNCTION IF EXISTS generate_studio_output_path(UUID, UUID, UUID, TEXT);

CREATE OR REPLACE FUNCTION generate_studio_output_path(
  p_user_id UUID,
  p_project_id UUID,
  p_job_type TEXT,
  p_job_id UUID,
  p_filename TEXT
)
RETURNS TEXT AS $$
BEGIN
  RETURN p_user_id || '/' || p_project_id || '/studio/' || p_job_type || '/' || p_job_id || '/' || p_filename;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION generate_studio_output_path(UUID, UUID, TEXT, UUID, TEXT)
IS 'Generate storage path for studio outputs: {user_id}/{project_id}/studio/{job_type}/{job_id}/{filename}';

CREATE OR REPLACE FUNCTION generate_ai_image_path(
  p_user_id UUID,
  p_project_id UUID,
  p_filename TEXT
)
RETURNS TEXT AS $$
BEGIN
  RETURN p_user_id || '/' || p_project_id || '/ai-images/' || p_filename;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION generate_ai_image_path(UUID, UUID, TEXT)
IS 'Generate storage path for generated analysis images: {user_id}/{project_id}/ai-images/{filename}';
