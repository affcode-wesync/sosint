// Shared keys storage - bundled with functions
// In production, edit keys.json in repo and redeploy
const fs = require('fs');
const path = require('path');

const KEYS_FILE = path.join(__dirname, '..', '..', 'backend', 'keys.json');

let keysData = null;

function loadKeys() {
  if (keysData) return keysData;
  try {
    keysData = JSON.parse(fs.readFileSync(KEYS_FILE, 'utf8'));
  } catch (e) {
    keysData = { admin_key: '67zovpokoyo', keys: [] };
  }
  return keysData;
}

function saveKeys(data) {
  keysData = data;
  try {
    fs.writeFileSync(KEYS_FILE, JSON.stringify(data, null, 2));
  } catch (e) {
    // In production (Netlify), filesystem is read-only
    // Keys are stored in memory only - lost on cold start
    // For persistent storage, use Netlify KV or external DB
  }
}

function checkAdmin(adminKey) {
  const data = loadKeys();
  return data.admin_key === adminKey;
}

function corsHeaders() {
  return {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  };
}

module.exports = { loadKeys, saveKeys, checkAdmin, corsHeaders };
