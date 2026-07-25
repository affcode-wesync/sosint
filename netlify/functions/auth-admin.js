const { loadKeys, saveKeys, checkAdmin, corsHeaders } = require('./keys-store');

exports.handler = async (event) => {
  if (event.httpMethod === 'OPTIONS') {
    return { statusCode: 200, headers: corsHeaders(), body: '' };
  }

  const url = new URL(event.path, 'http://localhost');
  const adminKey = url.searchParams.get('key') || event.queryStringParameters?.key;

  if (!adminKey || !checkAdmin(adminKey)) {
    return { statusCode: 403, headers: corsHeaders(), body: JSON.stringify({ detail: 'Admin access required' }) };
  }

  try {
    const data = loadKeys();
    const body = event.body ? JSON.parse(event.body) : {};

    // Handle different admin actions based on path
    if (event.path.includes('/keys/create') && event.httpMethod === 'POST') {
      const key = 'sk_' + Math.random().toString(36).substring(2, 14);
      const newKey = {
        key, username: body.username || '', comment: body.comment || '',
        status: 'active', created: new Date().toISOString().replace('T', ' ').substring(0, 19),
        last_login: null, login_count: 0,
      };
      data.keys.push(newKey);
      saveKeys(data);
      return {
        statusCode: 200, headers: { ...corsHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'ok', key }),
      };
    }

    if (event.path.includes('/keys/manage') && event.httpMethod === 'POST') {
      const target = data.keys.find(k => k.key === body.key);
      if (!target) return { statusCode: 404, headers: corsHeaders(), body: JSON.stringify({ detail: 'Key not found' }) };
      if (body.action === 'block') target.status = 'blocked';
      else if (body.action === 'unblock') target.status = 'active';
      else if (body.action === 'delete') data.keys = data.keys.filter(k => k.key !== body.key);
      saveKeys(data);
      return { statusCode: 200, headers: { ...corsHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify({ status: 'ok' }) };
    }

    if (event.path.includes('/keys') && event.httpMethod === 'GET') {
      return {
        statusCode: 200, headers: { ...corsHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'ok', keys: data.keys }),
      };
    }

    if (event.path.includes('/check')) {
      return { statusCode: 200, headers: { ...corsHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify({ status: 'ok', is_admin: true }) };
    }

    if (event.path.includes('/change_password') && event.httpMethod === 'POST') {
      if (body.new_password) { data.admin_key = body.new_password; saveKeys(data); }
      return { statusCode: 200, headers: { ...corsHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify({ status: 'ok' }) };
    }

    return { statusCode: 404, headers: corsHeaders(), body: JSON.stringify({ detail: 'Not found' }) };
  } catch (e) {
    return { statusCode: 500, headers: corsHeaders(), body: JSON.stringify({ detail: e.message }) };
  }
};
