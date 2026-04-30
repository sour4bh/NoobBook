-- Migration: Normalize provider-aware project cost tracking shape
-- Description: Align projects.costs with provider/model usage buckets.
-- Created: 2026-04-28

DROP TRIGGER IF EXISTS update_project_costs_on_message_change ON messages;
DROP FUNCTION IF EXISTS trigger_update_project_costs();
DROP FUNCTION IF EXISTS update_project_costs(UUID);

ALTER TABLE projects
  ALTER COLUMN costs SET DEFAULT '{
    "total_cost": 0,
    "by_model": {}
  }'::jsonb;

UPDATE projects
SET costs = jsonb_build_object(
  'total_cost',
  COALESCE(
    NULLIF(costs->>'total_cost', '')::numeric,
    NULLIF(costs->>'total_cost_usd', '')::numeric,
    0
  ),
  'by_model',
  COALESCE(costs->'by_model', '{}'::jsonb)
)
WHERE costs IS NULL
  OR costs ? 'total_cost_usd'
  OR costs ? 'total_input_tokens'
  OR costs ? 'total_output_tokens'
  OR NOT (costs ? 'total_cost')
  OR NOT (costs ? 'by_model');

COMMENT ON COLUMN projects.costs IS 'Per-project cost tracking: total_cost + by_model provider:model breakdown';
