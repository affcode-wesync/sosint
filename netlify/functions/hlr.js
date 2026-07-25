const { corsHeaders } = require('./keys-store');

exports.handler = async (event) => {
  if (event.httpMethod === 'OPTIONS') {
    return { statusCode: 200, headers: corsHeaders(), body: '' };
  }

  try {
    const { phone, api_key } = JSON.parse(event.body || '{}');
    if (!phone) {
      return { statusCode: 400, headers: corsHeaders(), body: JSON.stringify({ detail: 'Phone number required' }) };
    }

    if (!api_key) {
      return { statusCode: 400, headers: corsHeaders(), body: JSON.stringify({ detail: 'Numverify API key required' }) };
    }

    const cleanPhone = phone.replace(/[^0-9+]/g, '');
    const resp = await fetch(`http://apilayer.net/api/validate?access_key=${api_key}&number=${cleanPhone}`, { signal: AbortSignal.timeout(8000) });
    const data = await resp.json();

    if (!data.valid) {
      return {
        statusCode: 200,
        headers: { ...corsHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone: cleanPhone, valid: false, detail: 'Invalid number or API error' }),
      };
    }

    return {
      statusCode: 200,
      headers: { ...corsHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify({
        phone: cleanPhone, valid: true,
        country: data.country_name, country_code: data.country_code,
        carrier: data.carrier, line_type: data.line_type,
        location: data.location,
      }),
    };
  } catch (e) {
    return { statusCode: 500, headers: corsHeaders(), body: JSON.stringify({ detail: 'HLR error: ' + e.message }) };
  }
};
