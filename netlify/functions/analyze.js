const dns = require('dns').promises;
const net = require('net');
const { corsHeaders } = require('./keys-store');

const FREE_PROVIDERS = ['gmail.com','yahoo.com','hotmail.com','outlook.com','aol.com','mail.ru','yandex.ru','yandex.com','list.ru','bk.ru','icloud.com','protonmail.com','zoho.com','gmx.com','live.com'];
const DISPOSABLE_DOMAINS = ['tempmail.com','throwaway.email','guerrillamail.com','mailinator.com','yopmail.com','10minutemail.com','temp-mail.org','fakeinbox.com','sharklasers.com','guerrillamailblock.com','grr.la'];

async function getMxRecords(domain) {
  try {
    const records = await dns.resolveMx(domain);
    return records.sort((a, b) => a.priority - b.priority).map(r => r.exchange);
  } catch { return []; }
}

async function smtpVerify(mxHost, email) {
  const steps = [];
  const domain = email.split('@')[1];

  // DNS checks
  const hasMx = (await getMxRecords(domain)).length > 0;
  steps.push({ step: 'MX Records', result: hasMx ? 'Found' : 'Not Found', valid: hasMx });

  const hasA = await new Promise(r => dns.resolve4(domain).then(() => r(true)).catch(() => r(false)));
  steps.push({ step: 'A Record', result: hasA ? 'Found' : 'Not Found', valid: hasA });

  let spf = '', dkim = '', dmarc = '';
  try { const txt = await dns.resolveTxt(domain); spf = txt.flat().find(t => t.startsWith('v=spf1')) || ''; } catch {}
  try { const txt = await dns.resolveTxt('_dmarc.' + domain); dmarc = txt.flat().find(t => t.startsWith('v=DMARC')) || ''; } catch {}
  steps.push({ step: 'SPF', result: spf || 'Not Found', valid: !!spf });
  steps.push({ step: 'DMARC', result: dmarc || 'Not Found', valid: !!dmarc });

  // SMTP verification
  const smtpResult = await new Promise(resolve => {
    const socket = new net.Socket();
    let response = '';
    let step = 0;
    const cmds = [`EHLO mx.${domain}`, `MAIL FROM:<check@${domain}>`, `RCPT TO:<${email}>`, 'QUIT'];
    const results = [];

    socket.setTimeout(5000);
    socket.on('connect', () => { socket.write(cmds[0] + '\r\n'); });
    socket.on('data', (data) => {
      response += data.toString();
      if (response.match(/^2[0-9][0-9]/)) {
        if (step < cmds.length - 1) { step++; response = ''; socket.write(cmds[step] + '\r\n'); }
        else { results.push({ cmd: 'RCPT TO', code: response.substring(0, 3), valid: response.startsWith('250') }); socket.destroy(); resolve(results); }
      } else if (response.match(/^[45][0-9][0-9]/)) {
        results.push({ cmd: cmds[step], code: response.substring(0, 3), valid: false });
        socket.destroy(); resolve(results);
      }
    });
    socket.on('error', () => resolve(results));
    socket.on('timeout', () => { socket.destroy(); resolve(results); });
    socket.connect(25, mxHost);
  });

  const finalStatus = smtpResult.find(r => r.cmd === 'RCPT TO') ? (smtpResult.find(r => r.cmd === 'RCPT TO').valid ? 'valid' : 'invalid') : 'unknown';
  steps.push({ step: 'SMTP Verify', result: finalStatus, valid: finalStatus === 'valid' });

  return { steps, final_status: finalStatus, smtp: smtpResult };
}

async function getGoogleProfile(email) {
  const domain = email.split('@')[1];
  const avatarUrl = `https://www.gravatar.com/avatar/${Buffer.from(email).toString('base64url')}?d=404`;
  try {
    const resp = await fetch(avatarUrl);
    if (resp.ok) return { avatar_url: avatarUrl, has_gravatar: true };
  } catch {}
  return { avatar_url: null, has_gravatar: false };
}

async function checkServiceConnections(email) {
  const username = email.split('@')[0];
  const services = [
    { name: 'GitHub', url: `https://github.com/${username}`, pattern: /login|sign/i },
    { name: 'Twitter', url: `https://x.com/${username}`, pattern: /doesn.t exist|not found/i },
    { name: 'Instagram', url: `https://www.instagram.com/${username}/`, pattern: /Sorry, this page|page not found/i },
    { name: 'LinkedIn', url: `https://linkedin.com/in/${username}`, pattern: /page not found/i },
    { name: 'Pinterest', url: `https://pinterest.com/${username}/`, pattern: /not found/i },
    { name: 'TikTok', url: `https://www.tiktok.com/@${username}`, pattern: /Couldn.t find this account/i },
    { name: 'Spotify', url: `https://open.spotify.com/user/${username}`, pattern: /Page not found/i },
    { name: 'Reddit', url: `https://www.reddit.com/user/${username}`, pattern: /Sorry, nobody on Reddit goes by that name/i },
  ];

  const results = [];
  for (const svc of services) {
    try {
      const resp = await fetch(svc.url, { method: 'HEAD', redirect: 'follow', signal: AbortSignal.timeout(3000) });
      results.push({ service: svc.name, url: svc.url, status: resp.ok ? 'found' : 'not_found' });
    } catch {
      results.push({ service: svc.name, url: svc.url, status: 'unknown' });
    }
  }
  return results;
}

async function getWhoisInfo(domain) {
  try {
    // Simple WHOIS via API (free)
    const resp = await fetch(`https://rdap.verisign.com/com/v1/domain/${domain}`, { signal: AbortSignal.timeout(3000) });
    if (resp.ok) {
      const data = await resp.json();
      return { registrar: data.registrar?.name || 'Unknown', created: data.events?.find(e => e.eventAction === 'registration')?.eventDate || 'Unknown' };
    }
  } catch {}
  return { registrar: 'Unknown', created: 'Unknown' };
}

exports.handler = async (event) => {
  if (event.httpMethod === 'OPTIONS') {
    return { statusCode: 200, headers: corsHeaders(), body: '' };
  }

  try {
    const { email } = JSON.parse(event.body || '{}');
    if (!email || !email.includes('@')) {
      return { statusCode: 400, headers: corsHeaders(), body: JSON.stringify({ detail: 'Valid email required' }) };
    }

    const domain = email.split('@')[1];
    const isDisposable = DISPOSABLE_DOMAINS.includes(domain);
    const isFreeProvider = FREE_PROVIDERS.includes(domain);

    const mxRecords = await getMxRecords(domain);
    const smtp = mxRecords.length > 0 ? await smtpVerify(mxRecords[0], email) : { steps: [{ step: 'MX Records', result: 'No MX found', valid: false }], final_status: 'no_mx', smtp: [] };

    const [googleProfile, connections, whois] = await Promise.all([
      getGoogleProfile(email),
      checkServiceConnections(email),
      getWhoisInfo(domain),
    ]);

    // Risk calculation
    let risk = 0;
    if (smtp.final_status === 'valid') risk += 20;
    if (isDisposable) risk += 30;
    if (mxRecords.length === 0) risk += 20;
    if (connections.filter(c => c.status === 'found').length > 0) risk += 10;
    risk = Math.min(risk, 100);

    return {
      statusCode: 200,
      headers: { ...corsHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email, domain, is_disposable: isDisposable, is_free_provider: isFreeProvider,
        smtp: { ...smtp, mx_records: mxRecords },
        google: googleProfile,
        connections,
        whois,
        risk_score: risk,
        analysis_timestamp: new Date().toISOString(),
      }),
    };
  } catch (e) {
    return { statusCode: 500, headers: corsHeaders(), body: JSON.stringify({ detail: 'Analysis error: ' + e.message }) };
  }
};
