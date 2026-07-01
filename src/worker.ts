export interface Env {
  ASSETS: Fetcher;
  DB?: D1Database;
}

type SpecimenInput = {
  kind?: unknown;
  note?: unknown;
  doctrine?: unknown;
  readings?: unknown;
};

type ProjectInput = {
  slug?: unknown;
  name?: unknown;
  status?: unknown;
  summary?: unknown;
  url?: unknown;
  model?: unknown;
  stack?: unknown;
  visibility?: unknown;
  sort_order?: unknown;
};

const allowedKinds = new Set(['tap', 'jot', 'sprint', 'longread', 'meander', 'loop', 'steady']);
const allowedProjectStatus = new Set(['live', 'building', 'archived']);
const allowedVisibility = new Set(['public', 'private', 'hidden']);

function json(data: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(data), {
    ...init,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': 'no-store',
      ...init.headers,
    },
  });
}

function cleanText(value: unknown, max: number) {
  return String(value ?? '')
    .replace(/[<>]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, max);
}

function cleanSlug(value: unknown) {
  return cleanText(value, 80).toLowerCase().replace(/[^a-z0-9-]/g, '-').replace(/-+/g, '-').replace(/^-|-$/g, '');
}

function cleanUrl(value: unknown) {
  const url = cleanText(value, 180);
  if (!url.startsWith('/') && !url.startsWith('https://')) return '';
  return url;
}

function id() {
  return crypto.randomUUID();
}

async function listSpecimens(env: Env) {
  const rows = await env.DB!.prepare(
    'SELECT id, kind, note, doctrine, readings, created_at FROM specimens ORDER BY created_at DESC LIMIT 12'
  ).all();
  return json({ specimens: rows.results ?? [] });
}

async function createSpecimen(request: Request, env: Env) {
  const body = (await request.json().catch(() => ({}))) as SpecimenInput;
  const kind = cleanText(body.kind, 32);
  if (!allowedKinds.has(kind)) return json({ error: 'invalid kind' }, { status: 400 });
  const note = cleanText(body.note, 420);
  const doctrine = cleanText(body.doctrine, 120);
  const readings = cleanText(body.readings, 160);
  if (!note || !doctrine || !readings) return json({ error: 'missing fields' }, { status: 400 });
  const specimenId = id();
  const createdAt = new Date().toISOString();
  await env.DB!.prepare(
    'INSERT INTO specimens (id, kind, note, doctrine, readings, created_at) VALUES (?, ?, ?, ?, ?, ?)'
  ).bind(specimenId, kind, note, doctrine, readings, createdAt).run();
  return json({ ok: true, id: specimenId, created_at: createdAt }, { status: 201 });
}

async function listProjects(env: Env) {
  const rows = await env.DB!.prepare(
    'SELECT slug, name, status, summary, url, model, stack, visibility, sort_order, created_at, updated_at FROM projects ORDER BY sort_order ASC, updated_at DESC'
  ).all();
  return json({ projects: rows.results ?? [], state: 'd1' });
}

async function upsertProject(request: Request, env: Env) {
  const body = (await request.json().catch(() => ({}))) as ProjectInput;
  const slug = cleanSlug(body.slug);
  const name = cleanText(body.name, 120);
  const status = cleanText(body.status, 32);
  const summary = cleanText(body.summary, 520);
  const url = cleanUrl(body.url);
  const model = cleanText(body.model, 120);
  const stack = cleanText(body.stack, 160);
  const visibility = cleanText(body.visibility || 'public', 32);
  const sortOrder = Number.isFinite(Number(body.sort_order)) ? Math.trunc(Number(body.sort_order)) : 100;
  if (!slug || !name || !summary || !url || !model || !stack) return json({ error: 'missing fields' }, { status: 400 });
  if (!allowedProjectStatus.has(status)) return json({ error: 'invalid status' }, { status: 400 });
  if (!allowedVisibility.has(visibility)) return json({ error: 'invalid visibility' }, { status: 400 });
  const now = new Date().toISOString();
  await env.DB!.prepare(`
    INSERT INTO projects (slug, name, status, summary, url, model, stack, visibility, sort_order, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(slug) DO UPDATE SET
      name = excluded.name,
      status = excluded.status,
      summary = excluded.summary,
      url = excluded.url,
      model = excluded.model,
      stack = excluded.stack,
      visibility = excluded.visibility,
      sort_order = excluded.sort_order,
      updated_at = excluded.updated_at
  `).bind(slug, name, status, summary, url, model, stack, visibility, sortOrder, now, now).run();
  return json({ ok: true, slug, updated_at: now }, { status: 201 });
}

async function handleApi(request: Request, env: Env) {
  const url = new URL(request.url);
  if (!env.DB) {
    if (url.pathname === '/api/projects') return json({ projects: [], state: 'static-fallback' });
    if (url.pathname === '/api/specimens') return json({ specimens: [], state: 'static-fallback' });
    return json({ error: 'not found' }, { status: 404 });
  }

  if (url.pathname === '/api/specimens') {
    if (request.method === 'GET') return listSpecimens(env);
    if (request.method === 'POST') return createSpecimen(request, env);
    return json({ error: 'method not allowed' }, { status: 405, headers: { allow: 'GET, POST' } });
  }

  if (url.pathname === '/api/projects') {
    if (request.method === 'GET') return listProjects(env);
    if (request.method === 'POST') return upsertProject(request, env);
    return json({ error: 'method not allowed' }, { status: 405, headers: { allow: 'GET, POST' } });
  }

  return json({ error: 'not found' }, { status: 404 });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname.startsWith('/api/')) return handleApi(request, env);
    return env.ASSETS.fetch(request);
  },
};
