INSERT INTO projects (slug, name, status, summary, url, model, stack, visibility, sort_order, created_at, updated_at)
VALUES ('public-herbarium', 'public herbarium', 'live', 'A shared paper wall where each visitor word grows a deterministic procedural plant and can be pressed forever into the archive.', '/public-herbarium/', 'claude-fable-5 + rogue', 'Cloudflare Worker + D1 + deterministic SVG', 'public', 30, '2026-07-02T00:00:00.000Z', '2026-07-02T00:00:00.000Z')
ON CONFLICT(slug) DO UPDATE SET
  name=excluded.name,
  status=excluded.status,
  summary=excluded.summary,
  url=excluded.url,
  model=excluded.model,
  stack=excluded.stack,
  visibility=excluded.visibility,
  sort_order=excluded.sort_order,
  updated_at=excluded.updated_at;
