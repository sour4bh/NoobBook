-- Add direct ownership to background tasks so service-role-backed readers can
-- scope user-facing polling without relying on target-type inference.

ALTER TABLE background_tasks
  ADD COLUMN IF NOT EXISTS project_id UUID REFERENCES projects(id) ON DELETE CASCADE;

ALTER TABLE background_tasks
  ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id) ON DELETE CASCADE;

UPDATE background_tasks AS task
SET project_id = source.project_id
FROM sources AS source
WHERE task.project_id IS NULL
  AND task.target_id = source.id;

UPDATE background_tasks AS task
SET project_id = chat.project_id
FROM chats AS chat
WHERE task.project_id IS NULL
  AND task.target_id = chat.id;

UPDATE background_tasks AS task
SET project_id = chat.project_id
FROM studio_signals AS signal
JOIN chats AS chat ON chat.id = signal.chat_id
WHERE task.project_id IS NULL
  AND task.target_id = signal.id;

UPDATE background_tasks AS task
SET project_id = job.project_id
FROM studio_jobs AS job
WHERE task.project_id IS NULL
  AND task.target_id = job.id;

UPDATE background_tasks AS task
SET user_id = project.user_id
FROM projects AS project
WHERE task.user_id IS NULL
  AND task.project_id = project.id;

CREATE INDEX IF NOT EXISTS idx_tasks_project_status
  ON background_tasks(project_id, status, created_at);

CREATE INDEX IF NOT EXISTS idx_tasks_user_status
  ON background_tasks(user_id, status, created_at);

COMMENT ON COLUMN background_tasks.project_id IS 'Owning project for user-visible task polling';
COMMENT ON COLUMN background_tasks.user_id IS 'Owning user when known at task submission time';

DROP POLICY IF EXISTS "Users can view own background tasks" ON background_tasks;
DROP POLICY IF EXISTS "Users can create own background tasks" ON background_tasks;
DROP POLICY IF EXISTS "Users can update own background tasks" ON background_tasks;
DROP POLICY IF EXISTS "Users can delete own background tasks" ON background_tasks;

CREATE POLICY "Users can view own background tasks"
ON background_tasks FOR SELECT
USING (
  (project_id IS NOT NULL AND EXISTS (
    SELECT 1 FROM projects
    WHERE projects.id = background_tasks.project_id
      AND projects.user_id = auth.uid()
  ))
  OR (user_id IS NOT NULL AND user_id = auth.uid())
  OR (target_type = 'source' AND EXISTS (
    SELECT 1 FROM sources
    JOIN projects ON projects.id = sources.project_id
    WHERE sources.id = background_tasks.target_id
      AND projects.user_id = auth.uid()
  ))
  OR (target_type = 'studio_signal' AND EXISTS (
    SELECT 1 FROM studio_signals
    JOIN chats ON chats.id = studio_signals.chat_id
    JOIN projects ON projects.id = chats.project_id
    WHERE studio_signals.id = background_tasks.target_id
      AND projects.user_id = auth.uid()
  ))
  OR (target_type = 'chat' AND EXISTS (
    SELECT 1 FROM chats
    JOIN projects ON projects.id = chats.project_id
    WHERE chats.id = background_tasks.target_id
      AND projects.user_id = auth.uid()
  ))
);

CREATE POLICY "Users can create own background tasks"
ON background_tasks FOR INSERT
WITH CHECK (
  (project_id IS NOT NULL AND EXISTS (
    SELECT 1 FROM projects
    WHERE projects.id = background_tasks.project_id
      AND projects.user_id = auth.uid()
  ))
  OR (user_id IS NOT NULL AND user_id = auth.uid())
  OR (target_type = 'source' AND EXISTS (
    SELECT 1 FROM sources
    JOIN projects ON projects.id = sources.project_id
    WHERE sources.id = background_tasks.target_id
      AND projects.user_id = auth.uid()
  ))
  OR (target_type = 'studio_signal' AND EXISTS (
    SELECT 1 FROM studio_signals
    JOIN chats ON chats.id = studio_signals.chat_id
    JOIN projects ON projects.id = chats.project_id
    WHERE studio_signals.id = background_tasks.target_id
      AND projects.user_id = auth.uid()
  ))
  OR (target_type = 'chat' AND EXISTS (
    SELECT 1 FROM chats
    JOIN projects ON projects.id = chats.project_id
    WHERE chats.id = background_tasks.target_id
      AND projects.user_id = auth.uid()
  ))
);

CREATE POLICY "Users can update own background tasks"
ON background_tasks FOR UPDATE
USING (
  (project_id IS NOT NULL AND EXISTS (
    SELECT 1 FROM projects
    WHERE projects.id = background_tasks.project_id
      AND projects.user_id = auth.uid()
  ))
  OR (user_id IS NOT NULL AND user_id = auth.uid())
  OR (target_type = 'source' AND EXISTS (
    SELECT 1 FROM sources
    JOIN projects ON projects.id = sources.project_id
    WHERE sources.id = background_tasks.target_id
      AND projects.user_id = auth.uid()
  ))
  OR (target_type = 'studio_signal' AND EXISTS (
    SELECT 1 FROM studio_signals
    JOIN chats ON chats.id = studio_signals.chat_id
    JOIN projects ON projects.id = chats.project_id
    WHERE studio_signals.id = background_tasks.target_id
      AND projects.user_id = auth.uid()
  ))
  OR (target_type = 'chat' AND EXISTS (
    SELECT 1 FROM chats
    JOIN projects ON projects.id = chats.project_id
    WHERE chats.id = background_tasks.target_id
      AND projects.user_id = auth.uid()
  ))
);

CREATE POLICY "Users can delete own background tasks"
ON background_tasks FOR DELETE
USING (
  (project_id IS NOT NULL AND EXISTS (
    SELECT 1 FROM projects
    WHERE projects.id = background_tasks.project_id
      AND projects.user_id = auth.uid()
  ))
  OR (user_id IS NOT NULL AND user_id = auth.uid())
  OR (target_type = 'source' AND EXISTS (
    SELECT 1 FROM sources
    JOIN projects ON projects.id = sources.project_id
    WHERE sources.id = background_tasks.target_id
      AND projects.user_id = auth.uid()
  ))
  OR (target_type = 'studio_signal' AND EXISTS (
    SELECT 1 FROM studio_signals
    JOIN chats ON chats.id = studio_signals.chat_id
    JOIN projects ON projects.id = chats.project_id
    WHERE studio_signals.id = background_tasks.target_id
      AND projects.user_id = auth.uid()
  ))
  OR (target_type = 'chat' AND EXISTS (
    SELECT 1 FROM chats
    JOIN projects ON projects.id = chats.project_id
    WHERE chats.id = background_tasks.target_id
      AND projects.user_id = auth.uid()
  ))
);
