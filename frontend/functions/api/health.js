// Cloudflare Pages Function: GET /api/health
export async function onRequestGet() {
  return new Response(JSON.stringify({ status: 'ok', platform: 'cloudflare-pages' }), {
    headers: { 'Content-Type': 'application/json' },
  });
}
