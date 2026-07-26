// Cloudflare Pages Function: POST /api/face-search, /api/face-search/url
export async function onRequestPost(context) {
  const { request, env } = context;
  const cors = { 'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/json' };
  try {
    const url = new URL(request.url);
    const backendUrl = env.BACKEND_URL || 'https://sosint-api.onrender.com';
    const backendPath = url.pathname.replace('/api', '/api');
    const resp = await fetch(`${backendUrl}${backendPath}`, {
      method: 'POST', headers: request.headers, body: request.body,
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
