// Cloudflare Pages Function: /api/auth/admin/*
export async function onRequestPost(context) {
  const { request, env } = context;
  const cors = { 'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/json' };
  const url = new URL(request.url);
  const adminKey = url.searchParams.get('key');
  if (adminKey !== (env.ADMIN_KEY || '67zovpokoyo')) {
    return new Response(JSON.stringify({ detail: 'Admin access denied' }), { status: 403, headers: cors });
  }
  try {
    const path = url.pathname;
    const body = await request.json();
    const keysRaw = await env.DB.get('keys', { type: 'json' }) || [];

    if (path.includes('/keys/create')) {
      const key = 'sk_' + Math.random().toString(36).substring(2, 14);
      keysRaw.push({ key, username: body.username || '', comment: body.comment || '', status: 'active', created: new Date().toISOString().replace('T', ' ').substring(0, 19), last_login: null, login_count: 0 });
      await env.DB.put('keys', JSON.stringify(keysRaw));
      return new Response(JSON.stringify({ status: 'ok', key }), { headers: cors });
    }
    if (path.includes('/keys/manage')) {
      const k = keysRaw.find(x => x.key === body.key);
      if (!k) return new Response(JSON.stringify({ detail: 'Not found' }), { status: 404, headers: cors });
      if (body.action === 'block') k.status = 'blocked';
      else if (body.action === 'unblock') k.status = 'active';
      else if (body.action === 'delete') { const i = keysRaw.indexOf(k); keysRaw.splice(i, 1); }
      await env.DB.put('keys', JSON.stringify(keysRaw));
      return new Response(JSON.stringify({ status: 'ok' }), { headers: cors });
    }
    return new Response(JSON.stringify({ detail: 'Unknown action' }), { status: 400, headers: cors });
  } catch (e) {
    return new Response(JSON.stringify({ detail: e.message }), { status: 500, headers: cors });
  }
}

export async function onRequestGet(context) {
  const { request, env } = context;
  const cors = { 'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/json' };
  const url = new URL(request.url);
  const adminKey = url.searchParams.get('key');
  if (adminKey !== (env.ADMIN_KEY || '67zovpokoyo')) {
    return new Response(JSON.stringify({ detail: 'Admin access denied' }), { status: 403, headers: cors });
  }
  const keysRaw = await env.DB.get('keys', { type: 'json' }) || [];
  return new Response(JSON.stringify({ status: 'ok', keys: keysRaw }), { headers: cors });
}

export async function onRequestOptions() {
  return new Response(null, { headers: { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Methods': 'GET, POST, OPTIONS', 'Access-Control-Allow-Headers': 'Content-Type' } });
}
