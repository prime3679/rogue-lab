INSERT INTO projects (slug, name, status, summary, url, model, stack, visibility, sort_order, created_at, updated_at)
VALUES (
  'morning-edition',
  'morning edition',
  'live',
  'A daily generated NYC broadsheet with weather prose, sun and moon almanac data, and a deterministic weather rose.',
  '/morning-edition/',
  'claude-fable-5 + rogue',
  'Cloudflare Cron + Worker + D1 + Open-Meteo',
  'public',
  20,
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
