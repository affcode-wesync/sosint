const { loadKeys, corsHeaders } = require('./keys-store');

exports.handler = async (event) => {
  if (event.httpMethod === 'OPTIONS') {
    return { statusCode: 200, headers: corsHeaders(), body: '' };
  }

  try {
    const { key } = JSON.parse(event.body || '{}');
    if (!key) {
      return { statusCode: 400, headers: corsHeaders(), body: JSON.stringify({ detail: 'Key required' }) };
    }

    const data = loadKeys();

    // Admin key
    if (key === data.admin_key) {
      return {
        statusCode: 200,
        headers: { ...corsHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'ok', role: 'admin', username: 'admin' }),
      };
    }

    // User keys
    const userKey = data.keys.find(k => k.key === key);
    if (!userKey) {
      return {
        statusCode: 401,
        headers: { ...corsHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'error', detail: 'Invalid key' }),
      };
    }

    if (userKey.status === 'blocked') {
      return {
        statusCode: 403,
        headers: { ...corsHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'error', detail: 'Key is blocked' }),
      };
    }

    userKey.last_login = new Date().toISOString().replace('T', ' ').substring(0, 19);
    userKey.login_count = (userKey.login_count || 0) + 1;

    return {
      statusCode: 200,
      headers: { ...corsHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: 'ok', role: 'user', username: userKey.username || 'user' }),
    };
  } catch (e) {
    return {
      statusCode: 500,
      headers: { ...corsHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ detail: 'Server error: ' + e.message }),
    };
  }
};
