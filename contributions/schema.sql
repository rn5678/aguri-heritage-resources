PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS contributions (
  id TEXT PRIMARY KEY,
  client_id TEXT NOT NULL UNIQUE,
  token_hash TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  type TEXT NOT NULL CHECK (type IN ('story','document','correction')),
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  contributor_name TEXT NOT NULL,
  email TEXT NOT NULL DEFAULT '',
  place TEXT NOT NULL DEFAULT '',
  date_text TEXT NOT NULL DEFAULT '',
  source_url TEXT NOT NULL DEFAULT '',
  credit TEXT NOT NULL DEFAULT '',
  source_page TEXT NOT NULL DEFAULT '',
  language TEXT NOT NULL CHECK (language IN ('en','bn')),
  consent TEXT NOT NULL CHECK (consent = 'yes'),
  attachment_rights TEXT NOT NULL DEFAULT '' CHECK (attachment_rights IN ('','yes')),
  status TEXT NOT NULL DEFAULT 'received' CHECK (status IN ('received','under_review','needs_information','approved','published','declined')),
  public_note TEXT NOT NULL DEFAULT '',
  internal_note TEXT NOT NULL DEFAULT '',
  published_url TEXT NOT NULL DEFAULT '',
  version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS contributions_status_created ON contributions(status, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS contributions_created ON contributions(created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS contribution_storage (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  used_bytes INTEGER NOT NULL DEFAULT 0 CHECK (used_bytes >= 0 AND used_bytes <= 200000000)
);
INSERT OR IGNORE INTO contribution_storage(id, used_bytes) VALUES (1, 0);

CREATE TABLE IF NOT EXISTS contribution_files (
  id TEXT PRIMARY KEY,
  contribution_id TEXT NOT NULL REFERENCES contributions(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  type TEXT NOT NULL,
  size INTEGER NOT NULL CHECK (size > 0 AND size <= 1500000),
  data BLOB NOT NULL CHECK (length(data) = size)
);
CREATE INDEX IF NOT EXISTS contribution_files_parent ON contribution_files(contribution_id);
CREATE TRIGGER IF NOT EXISTS contribution_files_capacity BEFORE INSERT ON contribution_files
BEGIN
  SELECT (CASE WHEN (SELECT used_bytes FROM contribution_storage WHERE id = 1) + NEW.size > 200000000
    THEN RAISE(ABORT, 'attachment_capacity') END);
  SELECT (CASE WHEN (SELECT count(*) FROM contribution_files WHERE contribution_id = NEW.contribution_id) >= 3
    THEN RAISE(ABORT, 'attachment_count') END);
  UPDATE contribution_storage SET used_bytes = used_bytes + NEW.size WHERE id = 1;
END;
CREATE TRIGGER IF NOT EXISTS contribution_files_removed AFTER DELETE ON contribution_files
BEGIN
  UPDATE contribution_storage SET used_bytes = used_bytes - OLD.size WHERE id = 1;
END;

CREATE TABLE IF NOT EXISTS contribution_history (
  id TEXT PRIMARY KEY,
  contribution_id TEXT NOT NULL REFERENCES contributions(id) ON DELETE CASCADE,
  status TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  internal_note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS contribution_history_parent ON contribution_history(contribution_id, created_at);
CREATE TRIGGER IF NOT EXISTS contribution_editor_history AFTER UPDATE OF status, public_note, internal_note, published_url ON contributions
BEGIN
  INSERT INTO contribution_history(id,contribution_id,status,note,internal_note,created_at)
    VALUES(lower(hex(randomblob(16))),NEW.id,NEW.status,NEW.public_note,NEW.internal_note,NEW.updated_at);
END;

CREATE TABLE IF NOT EXISTS contribution_replies (
  id TEXT PRIMARY KEY,
  contribution_id TEXT NOT NULL REFERENCES contributions(id) ON DELETE CASCADE,
  message TEXT NOT NULL CHECK (length(message) BETWEEN 1 AND 5000),
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS contribution_replies_parent ON contribution_replies(contribution_id, created_at);
CREATE TRIGGER IF NOT EXISTS contribution_replies_limit BEFORE INSERT ON contribution_replies
BEGIN
  SELECT (CASE WHEN (SELECT count(*) FROM contribution_replies WHERE contribution_id = NEW.contribution_id) >= 20
    THEN RAISE(ABORT, 'reply_limit') END);
END;

CREATE TABLE IF NOT EXISTS contribution_rate_limits (
  bucket TEXT PRIMARY KEY,
  count INTEGER NOT NULL,
  expires_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS contribution_rate_expiry ON contribution_rate_limits(expires_at);

-- Opt-in web push notifications (added 2026-10-06). Safe to apply repeatedly.
CREATE TABLE IF NOT EXISTS push_subscriptions (
  id TEXT PRIMARY KEY,               -- SHA-256 of the endpoint
  endpoint TEXT NOT NULL UNIQUE,
  p256dh TEXT NOT NULL,
  auth TEXT NOT NULL,
  language TEXT NOT NULL CHECK (language IN ('en','bn')),
  failures INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_success_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS push_campaigns (
  id TEXT PRIMARY KEY,
  payload TEXT NOT NULL,
  audience TEXT NOT NULL CHECK (audience IN ('all','en','bn')),
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS push_campaigns_created ON push_campaigns(created_at DESC);
CREATE TABLE IF NOT EXISTS push_deliveries (
  campaign_id TEXT NOT NULL REFERENCES push_campaigns(id) ON DELETE CASCADE,
  subscription_id TEXT NOT NULL,
  outcome TEXT NOT NULL CHECK (outcome IN ('sent','expired','failed')),
  created_at TEXT NOT NULL,
  PRIMARY KEY (campaign_id, subscription_id)
);

-- Aggregate page views (added 2026-10-09). No visitor or request identities.
CREATE TABLE IF NOT EXISTS page_views (
  page TEXT PRIMARY KEY,
  views INTEGER NOT NULL DEFAULT 0 CHECK (views >= 0)
);

-- Private contact-mail idempotency metadata. No message body, name or email.
CREATE TABLE IF NOT EXISTS contact_requests (
  request_id TEXT PRIMARY KEY,
  payload_hash TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending','sent')),
  created_at TEXT NOT NULL
);
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
