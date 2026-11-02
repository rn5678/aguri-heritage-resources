-- Additive and repeatable; existing contribution and notification data is untouched.
-- Only canonical page paths and aggregate totals are stored.
CREATE TABLE IF NOT EXISTS page_views (
  page TEXT PRIMARY KEY,
  views INTEGER NOT NULL DEFAULT 0 CHECK (views >= 0)
);
