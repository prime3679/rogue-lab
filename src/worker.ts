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

const allowedKinds = new Set(['tap', 'jot', 'sprint', 'longread', 'meander', 'loop', 'steady']);

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

function id() {
  return crypto.randomUUID();
}

async function handleApi(request: Request, env: Env) {
  const url = new URL(request.url);
  if (url.pathname !== '/api/specimens') return json({ error: 'not found' }, { status: 404 });
  if (!env.DB) return json({ specimens: [], state: 'static-fallback' });

  if (request.method === 'GET') {
    const rows = await env.DB.prepare(
      'SELECT id, kind, note, doctrine, readings, created_at FROM specimens ORDER BY created_at DESC LIMIT 12'
    ).all();
    return json({ specimens: rows.results ?? [] });
  }

  if (request.method === 'POST') {
    const body = (await request.json().catch(() => ({}))) as SpecimenInput;
    const kind = cleanText(body.kind, 32);
    if (!allowedKinds.has(kind)) return json({ error: 'invalid kind' }, { status: 400 });
    const note = cleanText(body.note, 420);
    const doctrine = cleanText(body.doctrine, 120);
    const readings = cleanText(body.readings, 160);
    if (!note || !doctrine || !readings) return json({ error: 'missing fields' }, { status: 400 });
    const specimenId = id();
    const createdAt = new Date().toISOString();
    await env.DB.prepare(
      'INSERT INTO specimens (id, kind, note, doctrine, readings, created_at) VALUES (?, ?, ?, ?, ?, ?)'
    ).bind(specimenId, kind, note, doctrine, readings, createdAt).run();
    return json({ ok: true, id: specimenId, created_at: createdAt }, { status: 201 });
  }

  return json({ error: 'method not allowed' }, { status: 405, headers: { allow: 'GET, POST' } });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname.startsWith('/api/')) return handleApi(request, env);
    return env.ASSETS.fetch(request);
  },
};
