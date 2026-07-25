const { corsHeaders } = require('./keys-store');

function extractSocialLinks(html) {
  const links = [];
  const vkMatch = html.match(/https?:\/\/(?:vk\.com|vkontakte\.ru)\/[^\s"'<>]+/gi);
  const okMatch = html.match(/https?:\/\/(?:ok\.ru|odnoklassniki\.ru)\/[^\s"'<>]+/gi);
  if (vkMatch) vkMatch.forEach(u => links.push({ platform: 'VK', url: u }));
  if (okMatch) okMatch.forEach(u => links.push({ platform: 'Odnoklassniki', url: u }));
  return links;
}

async function searchByUrl(imageUrl) {
  const yandexUrl = `https://yandex.com/images/search?rpt=imageview&url=${encodeURIComponent(imageUrl)}`;
  const resp = await fetch(yandexUrl, {
    headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36' },
    signal: AbortSignal.timeout(10000),
  });
  const html = await resp.text();
  const socialLinks = extractSocialLinks(html);
  return { yandex_url: yandexUrl, social_links: socialLinks, total_found: socialLinks.length };
}

async function searchByFile(file) {
  // Upload to Yandex via their search
  const formData = new FormData();
  formData.append('upfile', file);
  const uploadResp = await fetch('https://yandex.com/images/search', {
    method: 'POST', body: formData,
    signal: AbortSignal.timeout(15000),
  });
  const html = await uploadResp.text();
  const socialLinks = extractSocialLinks(html);
  return { social_links: socialLinks, total_found: socialLinks.length };
}

exports.handler = async (event) => {
  if (event.httpMethod === 'OPTIONS') {
    return { statusCode: 200, headers: corsHeaders(), body: '' };
  }

  try {
    // URL search
    if (event.path.includes('/url')) {
      const { url } = JSON.parse(event.body || '{}');
      if (!url) return { statusCode: 400, headers: corsHeaders(), body: JSON.stringify({ error: 'URL required' }) };
      const result = await searchByUrl(url);
      return { statusCode: 200, headers: { ...corsHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify(result) };
    }

    // File upload search
    if (event.httpMethod === 'POST') {
      const ct = event.headers['content-type'] || '';
      if (ct.includes('multipart/form-data')) {
        // Parse multipart - Netlify passes the raw body
        // For simplicity, redirect to URL-based search
        return { statusCode: 400, headers: corsHeaders(), body: JSON.stringify({ error: 'File upload not supported on serverless. Use URL search instead.' }) };
      }
    }

    return { statusCode: 400, headers: corsHeaders(), body: JSON.stringify({ error: 'Invalid request' }) };
  } catch (e) {
    return { statusCode: 500, headers: corsHeaders(), body: JSON.stringify({ error: 'Face search error: ' + e.message }) };
  }
};
