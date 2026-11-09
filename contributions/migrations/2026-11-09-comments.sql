-- Optional page comments. Apply before enabling COMMENTS_ENABLED, never at runtime.
CREATE TABLE IF NOT EXISTS comment_users (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS comment_sessions (
  token_hash TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES comment_users(id),
  expires_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS comment_sessions_expiry ON comment_sessions(expires_at);
CREATE TABLE IF NOT EXISTS comment_login_nonces (nonce_hash TEXT PRIMARY KEY, expires_at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS comment_nonces_expiry ON comment_login_nonces(expires_at);
CREATE TABLE IF NOT EXISTS comment_rate_limits (bucket TEXT PRIMARY KEY, count INTEGER NOT NULL, expires_at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS comment_rates_expiry ON comment_rate_limits(expires_at);
CREATE TABLE IF NOT EXISTS comments (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES comment_users(id),
  client_id TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  page TEXT NOT NULL,
  name TEXT NOT NULL,
  body TEXT NOT NULL CHECK(length(body)<=2000),
  status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected','hidden','deleted')),
  version INTEGER NOT NULL DEFAULT 1,
  terms_version TEXT NOT NULL,
  consented_at TEXT NOT NULL,
  moderation_note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(user_id,client_id)
);
CREATE INDEX IF NOT EXISTS comments_page_status ON comments(page,status,created_at DESC,id DESC);
CREATE INDEX IF NOT EXISTS comments_review ON comments(status,created_at DESC,id DESC);
CREATE INDEX IF NOT EXISTS comments_author ON comments(user_id,page,created_at DESC,id DESC);
CREATE TABLE IF NOT EXISTS comment_moderation_history (
  id TEXT PRIMARY KEY,
  comment_id TEXT NOT NULL REFERENCES comments(id),
  previous_status TEXT NOT NULL,
  status TEXT NOT NULL,
  actor TEXT NOT NULL,
  note TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS comment_status_audit AFTER UPDATE OF status,moderation_note ON comments
WHEN OLD.status <> NEW.status OR OLD.moderation_note <> NEW.moderation_note
BEGIN
  INSERT INTO comment_moderation_history(id,comment_id,previous_status,status,actor,note,created_at)
  VALUES(lower(hex(randomblob(16))),NEW.id,OLD.status,NEW.status,CASE WHEN NEW.status='deleted' THEN 'author' ELSE 'editor' END,NEW.moderation_note,NEW.updated_at);
END;
CREATE TABLE IF NOT EXISTS comment_reports (
  comment_id TEXT NOT NULL REFERENCES comments(id),
  user_id TEXT NOT NULL REFERENCES comment_users(id),
  reason TEXT NOT NULL CHECK(length(reason) BETWEEN 1 AND 500),
  created_at TEXT NOT NULL,
  PRIMARY KEY(comment_id,user_id)
);
