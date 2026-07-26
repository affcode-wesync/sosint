// Cloudflare Pages Function: POST /api/sherlock/export, /api/analyze/export, /api/hlr/export
export async function onRequestPost(context) {
  const { request, env } = context;
  const cors = { 'Access-Control-Allow-Origin': '*' };
  try {
    const url = new URL(request.url);
    const backendUrl = env.BACKEND_URL || 'https://sosint-api.onrender.com';
    const resp = await fetch(`${backendUrl}${url.pathname}`, {
      method: 'POST', headers: request.headers, body: request.body,
    });
    const ct = resp.headers.get('content-type') || 'text/html';
    const body = await resp.text();
    return new Response(body, { status: resp.status, headers: { ...cors, 'Content-Type': ct, 'Content-Disposition': resp.headers.get('content-Disposition') || '' } });
  } catch (e) {
    return new Response('Backend error', { status: 502, headers: cors });
  }
}
export async function onRequestOptions() {
  return new Response(null, { headers: { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Methods': 'POST, OPTIONS', 'Access-Control-Allow-Headers': 'Content-Type' } });
}
