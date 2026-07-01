CREATE TABLE IF NOT EXISTS projects (
  slug TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  status TEXT NOT NULL,
  summary TEXT NOT NULL,
  url TEXT NOT NULL,
  model TEXT NOT NULL,
  stack TEXT NOT NULL,
  visibility TEXT NOT NULL,
  sort_order INTEGER NOT NULL DEFAULT 100,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

INSERT INTO projects (slug, name, status, summary, url, model, stack, visibility, sort_order, created_at, updated_at)
VALUES (
  'fable-field-recorder',
  'fable field recorder',
  'live',
  'A tactile field notebook for drawing gestures, filing specimens, and testing Fable-built interaction quality.',
  '/fable-field-recorder/',
  'claude-fable-5',
  'Cloudflare Worker + D1 + static assets',
  'public',
  10,
  '2026-07-01T00:00:00.000Z',
  '2026-07-01T00:00:00.000Z'
)
ON CONFLICT(slug) DO UPDATE SET
  name = excluded.name,
  status = excluded.status,
  summary = excluded.summary,
  url = excluded.url,
  model = excluded.model,
  stack = excluded.stack,
  visibility = excluded.visibility,
  sort_order = excluded.sort_order,
  updated_at = excluded.updated_at;
