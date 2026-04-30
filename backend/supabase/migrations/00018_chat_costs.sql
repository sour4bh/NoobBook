-- Add cost tracking column to chats table.
--
-- Mirrors the `projects.costs` JSONB structure so we can use the same
-- cost_tracking utility to update both in one locked operation.
--
-- Existing chats get the default on first cost write via
-- _ensure_cost_structure() in app/utils/cost_tracking.py.

ALTER TABLE chats
ADD COLUMN IF NOT EXISTS costs JSONB DEFAULT '{
  "total_cost": 0,
  "by_model": {}
}'::jsonb;

COMMENT ON COLUMN chats.costs IS 'Per-chat cost tracking: total_cost + by_model provider:model breakdown';
