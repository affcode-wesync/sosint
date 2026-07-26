// Cloudflare Pages Function: POST /api/auth/login
export async function onRequestPost(context) {
  const { request, env } = context;
  const cors = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Content-Type': 'application/json',
  };

  try {
    const { key } = await request.json();
    if (!key) return new Response(JSON.stringify({ detail: 'Key required' }), { status: 400, headers: cors });

    const adminKey = env.ADMIN_KEY || '67zovpokoyo';

    if (key === adminKey) {
      return new Response(JSON.stringify({ status: 'ok', role: 'admin', message: 'Admin access granted' }), { headers: cors });
    }

    const keysRaw = await env.DB.get('keys', { type: 'json' }) || [];
    const userKey = keysRaw.find(k => k.key === key && k.status === 'active');
    if (userKey) {
      userKey.last_login = new Date().toISOString().replace('T', ' ').substring(0, 19);
      userKey.login_count = (userKey.login_count || 0) + 1;
      await env.DB.put('keys', JSON.stringify(keysRaw));
      return new Response(JSON.stringify({ status: 'ok', role: 'user', username: userKey.username || '' }), { headers: cors });
    }

    return new Response(JSON.stringify({ detail: 'Invalid key' }), { status: 401, headers: cors });
  } catch (e) {
    return new Response(JSON.stringify({ detail: e.message }), { status: 500, headers: cors });
  }
}

export async function onRequestOptions() {
  return new Response(null, {
    headers: {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
    },
  });
}
