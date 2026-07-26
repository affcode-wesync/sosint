import os
import json
from datetime import datetime

# Supabase config - set these in environment variables
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

_client = None

def get_client():
    global _client
    if _client is None and SUPABASE_URL and SUPABASE_KEY:
        from supabase import create_client
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


def init_db():
    """Create tables if they don't exist (run on first start)"""
    client = get_client()
    if not client:
        print("[DB] Supabase not configured, using JSON fallback")
        return False
    print("[DB] Connected to Supabase")
    return True


# ===== KEYS =====

def load_keys():
    client = get_client()
    if not client:
        return _load_keys_json()

    try:
        # Get admin key
        res = client.table("settings").select("*").eq("key", "admin_key").execute()
        admin_key = res.data[0]["value"] if res.data else "67zovpokoyo"

        # Get all user keys
        res = client.table("keys").select("*").order("created", desc=True).execute()
        return {"admin_key": admin_key, "keys": res.data}
    except Exception as e:
        print(f"[DB] Error loading keys: {e}")
        return _load_keys_json()


def save_keys(data):
    client = get_client()
    if not client:
        return _save_keys_json(data)

    try:
        # Save admin key
        client.table("settings").upsert({
            "key": "admin_key",
            "value": data.get("admin_key", "67zovpokoyo")
        }).execute()

        # Sync user keys
        existing = client.table("keys").select("key").execute()
        existing_keys = {k["key"] for k in existing.data}
        new_keys = {k["key"] for k in data.get("keys", [])}

        # Delete removed keys
        for k in existing_keys - new_keys:
            client.table("keys").delete().eq("key", k).execute()

        # Upsert all keys
        for k in data.get("keys", []):
            client.table("keys").upsert({
                "key": k["key"],
                "username": k.get("username", ""),
                "comment": k.get("comment", ""),
                "status": k.get("status", "active"),
                "created": k.get("created", ""),
                "last_login": k.get("last_login"),
                "login_count": k.get("login_count", 0)
            }).execute()
    except Exception as e:
        print(f"[DB] Error saving keys: {e}")
        _save_keys_json(data)


def create_key(key_data):
    client = get_client()
    if not client:
        data = _load_keys_json()
        data["keys"].append(key_data)
        _save_keys_json(data)
        return

    try:
        client.table("keys").insert({
            "key": key_data["key"],
            "username": key_data.get("username", ""),
            "comment": key_data.get("comment", ""),
            "status": "active",
            "created": key_data.get("created", ""),
            "last_login": None,
            "login_count": 0
        }).execute()
    except Exception as e:
        print(f"[DB] Error creating key: {e}")


def delete_key(key_value):
    client = get_client()
    if not client:
        data = _load_keys_json()
        data["keys"] = [k for k in data["keys"] if k["key"] != key_value]
        _save_keys_json(data)
        return

    try:
        client.table("keys").delete().eq("key", key_value).execute()
    except Exception as e:
        print(f"[DB] Error deleting key: {e}")


def update_key(key_value, updates):
    client = get_client()
    if not client:
        data = _load_keys_json()
        for k in data["keys"]:
            if k["key"] == key_value:
                k.update(updates)
        _save_keys_json(data)
        return

    try:
        client.table("keys").update(updates).eq("key", key_value).execute()
    except Exception as e:
        print(f"[DB] Error updating key: {e}")


# ===== STATISTICS =====

def log_action(action, details=None):
    client = get_client()
    if not client:
        return
    try:
        client.table("activity_log").insert({
            "action": action,
            "details": json.dumps(details) if details else None,
            "created_at": datetime.now().isoformat()
        }).execute()
    except Exception as e:
        print(f"[DB] Error logging action: {e}")


def get_stats():
    client = get_client()
    if not client:
        return {"total_keys": 0, "active_keys": 0, "total_logins": 0}
    try:
        keys = client.table("keys").select("*").execute()
        total = len(keys.data)
        active = len([k for k in keys.data if k.get("status") == "active"])
        logins = sum(k.get("login_count", 0) for k in keys.data)
        return {"total_keys": total, "active_keys": active, "total_logins": logins}
    except Exception as e:
        return {"total_keys": 0, "active_keys": 0, "total_logins": 0}


# ===== JSON FALLBACK =====

KEYS_FILE = os.path.join(os.path.dirname(__file__), "keys.json")

def _load_keys_json():
    if not os.path.exists(KEYS_FILE):
        return {"admin_key": "67zovpokoyo", "keys": []}
    with open(KEYS_FILE, "r") as f:
        return json.load(f)

def _save_keys_json(data):
    with open(KEYS_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
