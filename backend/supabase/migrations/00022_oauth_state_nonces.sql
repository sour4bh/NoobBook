-- Migration: OAuth one-time state nonces
-- Description: Persist OAuth state nonces so provider callbacks can be consumed once.
-- Created: 2026-04-27

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

ALTER TABLE oauth_states ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can read own OAuth states" ON oauth_states;
DROP POLICY IF EXISTS "Users can create own OAuth states" ON oauth_states;

CREATE POLICY "Users can read own OAuth states"
ON oauth_states FOR SELECT
USING (user_id = auth.uid());

CREATE POLICY "Users can create own OAuth states"
ON oauth_states FOR INSERT
WITH CHECK (user_id = auth.uid());
