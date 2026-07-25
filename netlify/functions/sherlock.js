const { corsHeaders } = require('./keys-store');

const SITES = [
  { name: 'GitHub', url: 'https://github.com/{u}', check: /login|sign/i },
  { name: 'Twitter', url: 'https://x.com/{u}', check: /doesn.t exist|not found/i },
  { name: 'Instagram', url: 'https://www.instagram.com/{u}/', check: /Sorry, this page|page not found/i },
  { name: 'Reddit', url: 'https://www.reddit.com/user/{u}', check: /Sorry, nobody/i },
  { name: 'TikTok', url: 'https://www.tiktok.com/@{u}', check: /not found/i },
  { name: 'Pinterest', url: 'https://pinterest.com/{u}/', check: /not found/i },
  { name: 'LinkedIn', url: 'https://linkedin.com/in/{u}', check: /not found/i },
  { name: 'YouTube', url: 'https://www.youtube.com/@{u}', check: /not found/i },
  { name: 'Twitch', url: 'https://www.twitch.tv/{u}', check: /not found/i },
  { name: 'Spotify', url: 'https://open.spotify.com/user/{u}', check: /not found/i },
  { name: 'Steam', url: 'https://steamcommunity.com/id/{u}', check: /hasn.t set up their profile/i },
  { name: 'DeviantArt', url: 'https://www.deviantart.com/{u}', check: /does not exist/i },
  { name: 'Flickr', url: 'https://www.flickr.com/people/{u}/', check: /not found/i },
  { name: 'Medium', url: 'https://medium.com/@{u}', check: /PAGE NOT FOUND/i },
  { name: 'VK', url: 'https://vk.com/{u}', check: /Page not found/i },
  { name: 'Telegram', url: 'https://t.me/{u}', check: /if you have/i },
  { name: 'LinkedIn', url: 'https://github.com/{u}', check: /404/i },
];

exports.handler = async (event) => {
  if (event.httpMethod === 'OPTIONS') {
    return { statusCode: 200, headers: corsHeaders(), body: '' };
  }

  try {
    const { username } = JSON.parse(event.body || '{}');
    if (!username) {
      return { statusCode: 400, headers: corsHeaders(), body: JSON.stringify({ detail: 'Username required' }) };
    }

    const results = [];
    const promises = SITES.map(async (site) => {
      const url = site.url.replace('{u}', username);
      try {
        const resp = await fetch(url, { method: 'GET', redirect: 'follow', signal: AbortSignal.timeout(4000) });
        const text = await resp.text();
        const found = resp.ok && !site.check.test(text);
        results.push({ site: site.name, url, status: found ? 'found' : 'not_found' });
      } catch {
        results.push({ site: site.name, url, status: 'error' });
      }
    });

    await Promise.allSettled(promises);

    return {
      statusCode: 200,
      headers: { ...corsHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, results, found_count: results.filter(r => r.status === 'found').length }),
    };
  } catch (e) {
    return { statusCode: 500, headers: corsHeaders(), body: JSON.stringify({ detail: 'Sherlock error: ' + e.message }) };
  }
};
