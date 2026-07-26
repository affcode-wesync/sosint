// Cloudflare Pages Function: POST /api/sherlock
export async function onRequestPost(context) {
  const { request, env } = context;
  const cors = { 'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/json' };
  try {
    const body = await request.json();
    if (!body.username) return new Response(JSON.stringify({ detail: 'Username required' }), { status: 400, headers: cors });
    const backendUrl = env.BACKEND_URL || 'https://sosint-api.onrender.com';
    const resp = await fetch(`${backendUrl}/api/sherlock`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    });
    const data = await resp.json();
    return new Response(JSON.stringify(data), { status: resp.status, headers: cors });
  } catch (e) {
    return new Response(JSON.stringify({ detail: 'Backend error: ' + e.message }), { status: 502, headers: cors });
  }
}
export async function onRequestOptions() {
  return new Response(null, { headers: { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Methods': 'POST, OPTIONS', 'Access-Control-Allow-Headers': 'Content-Type' } });
}
