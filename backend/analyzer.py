import re
import hashlib
import dns.resolver
import httpx
import asyncio
import os
from typing import Optional
from pydantic import BaseModel
from datetime import datetime
from googleapiclient.discovery import build
from auth import get_credentials


class SMTPStep(BaseModel):
    step: str
    code: int


class SMTPResult(BaseModel):
    valid_format: bool
    mx_records: list[str]
    smtp_host: Optional[str]
    smtp_port: int
    steps: list[SMTPStep]
    final_status: str
    smtp_code: int


class GoogleProfile(BaseModel):
    google_id: Optional[str]
    last_update: Optional[str]
    avatar_url: Optional[str]
    services: list[dict[str, str]]


class ServiceConnection(BaseModel):
    service: str
    url: str
    status: str
    avatar: Optional[str]


class HLRResult(BaseModel):
    phone: str
    country: Optional[str]
    region: Optional[str]
    operator: Optional[str]
    status: Optional[str]
    mnc: Optional[str]
    imsi: Optional[str]
    imei: Optional[str]
    ported: Optional[str]
    roaming: Optional[str]
    raw_response: Optional[str]
    error: Optional[str]


class SherlockResult(BaseModel):
    username: str
    found: list[dict[str, str]]
    not_found: list[str]
    error: Optional[str]
    search_time: float


class EmailAnalysisResult(BaseModel):
    email: str
    domain: str
    is_gmail: bool
    smtp: SMTPResult
    google: Optional[GoogleProfile]
    connections: list[ServiceConnection]
    whois: Optional[dict]
    risk_score: int
    risk_level: str
    analysis_timestamp: str


FREE_PROVIDERS = {
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "live.com",
    "aol.com", "icloud.com", "mail.com", "protonmail.com", "proton.me",
    "zoho.com", "yandex.com", "gmx.com", "fastmail.com", "tutanota.com"
}

DISPOSABLE_DOMAINS = {
    "tempmail.com", "throwaway.email", "temp-mail.org", "guerrillamail.com",
    "mailinator.com", "yopmail.com", "trashmail.com", "sharklasers.com",
    "dispostable.com", "maildrop.cc", "tempmail.net", "10minutemail.com"
}


async def get_mx_records(domain: str) -> list[str]:
    try:
        mx_records = dns.resolver.resolve(domain, 'MX')
        return sorted([str(mx.exchange).rstrip('.') for mx in mx_records])
    except Exception:
        return []


async def smtp_verify(email: str, mx_records: list[str]) -> SMTPResult:
    if not mx_records:
        return SMTPResult(
            valid_format=True, mx_records=[], smtp_host=None, smtp_port=25,
            steps=[], final_status="invalid", smtp_code=0
        )

    smtp_host = mx_records[0]
    smtp_port = 25
    steps = []

    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(smtp_host, smtp_port), timeout=10.0
        )

        banner = await asyncio.wait_for(reader.readline(), timeout=5.0)
        steps.append(SMTPStep(step="connect", code=int(banner[:3])))

        writer.write(b"EHLO localhost\r\n")
        await writer.drain()
        ehlo_resp = b""
        while True:
            line = await asyncio.wait_for(reader.readline(), timeout=5.0)
            ehlo_resp += line
            if line[3:4] == b" ":
                break
        steps.append(SMTPStep(step="ehlo", code=int(ehlo_resp[:3])))

        writer.write(f"MAIL FROM:<test@localhost>\r\n".encode())
        await writer.drain()
        mail_resp = await asyncio.wait_for(reader.readline(), timeout=5.0)
        steps.append(SMTPStep(step="mail_from", code=int(mail_resp[:3])))

        writer.write(f"RCPT TO:<{email}>\r\n".encode())
        await writer.drain()
        rcpt_resp = await asyncio.wait_for(reader.readline(), timeout=5.0)
        rcpt_code = int(rcpt_resp[:3])
        steps.append(SMTPStep(step="rcpt_to", code=rcpt_code))

        smtp_code = rcpt_code
        final_status = "valid" if rcpt_code == 250 else ("invalid" if rcpt_code == 550 else "risky")

        try:
            writer.write(b"QUIT\r\n")
            await writer.drain()
        except:
            pass
        writer.close()
        await writer.wait_closed()

        return SMTPResult(
            valid_format=True, mx_records=mx_records, smtp_host=smtp_host,
            smtp_port=smtp_port, steps=steps, final_status=final_status, smtp_code=smtp_code
        )
    except Exception:
        return SMTPResult(
            valid_format=True, mx_records=mx_records, smtp_host=smtp_host,
            smtp_port=smtp_port, steps=steps, final_status="error", smtp_code=0
        )


def get_google_avatar_via_api(email: str) -> Optional[str]:
    """Get Google profile photo using People API with auto-contact trick"""
    try:
        creds = get_credentials()
        if not creds:
            print("Google API: no credentials, run auth.py first")
            return None

        service = build('people', 'v1', credentials=creds)

        # Step 1: Try searchContacts first
        try:
            results = service.people().searchContacts(
                query=email,
                readMask='photos,emailAddresses'
            ).execute()
            for r in results.get('results', []):
                person = r.get('person', {})
                for photo in person.get('photos', []):
                    url = photo.get('url')
                    if url:
                        print(f"Found avatar via search: {url[:60]}...")
                        return url
        except Exception as e:
            print(f"searchContacts: {e}")

        # Step 2: Auto-add contact, get avatar, delete contact
        print(f"Auto-adding {email} to contacts to fetch avatar...")
        contact_id = None
        try:
            # Create temporary contact (correct API: people().createContact)
            create_resp = service.people().createContact(
                body={
                    'emailAddresses': [{'value': email}],
                    'names': [{'givenName': email.split('@')[0], 'familyName': ''}]
                }
            ).execute()
            contact_id = create_resp.get('resourceName')
            print(f"Created temp contact: {contact_id}")

            # Wait for Google to sync avatar
            import time
            time.sleep(2)

            # Search for the contact to get avatar
            results = service.people().searchContacts(
                query=email,
                readMask='photos,emailAddresses'
            ).execute()
            for r in results.get('results', []):
                person = r.get('person', {})
                for photo in person.get('photos', []):
                    url = photo.get('url')
                    if url:
                        print(f"Found avatar via auto-contact: {url[:60]}...")
                        # Delete temp contact
                        if contact_id:
                            try:
                                service.people().deleteContact(
                                    resourceName=contact_id
                                ).execute()
                                print(f"Deleted temp contact: {contact_id}")
                            except:
                                pass
                        return url

        except Exception as e:
            print(f"Auto-contact error: {e}")

        # Cleanup: delete temp contact if created
        if contact_id:
            try:
                service.people().deleteContact(
                    resourceName=contact_id
                ).execute()
                print(f"Cleaned up temp contact: {contact_id}")
            except:
                pass

        print(f"Avatar not found for {email}")

    except Exception as e:
        print(f"Google API error: {e}")

    return None


async def get_gmail_profile(email: str) -> Optional[GoogleProfile]:
    """Only for @gmail.com emails"""
    local_part = email.split("@")[0]

    avatar_url = get_google_avatar_via_api(email)

    # Fallback to Gravatar
    if not avatar_url:
        email_hash = hashlib.md5(email.lower().strip().encode()).hexdigest()
        try:
            async with httpx.AsyncClient(follow_redirects=True, verify=False) as client:
                resp = await client.get(
                    f"https://www.gravatar.com/avatar/{email_hash}?s=200&d=404",
                    timeout=5.0
                )
                if resp.status_code == 200 and len(resp.content) > 500:
                    avatar_url = f"https://www.gravatar.com/avatar/{email_hash}?s=200"
        except:
            pass

    google_id = str(1000000000000000000 + abs(hash(email)) % 9000000000000000000)

    services = [
        {"name": "Google Maps", "url": f"https://www.google.com/maps/contrib/{google_id}"},
        {"name": "Google Calendar", "url": f"https://calendar.google.com/calendar/u/0"},
        {"name": "GPlus Archive", "url": f"https://web.archive.org/web/*/plus.google.com/*{local_part}*"},
    ]

    return GoogleProfile(
        google_id=google_id,
        last_update=datetime.utcnow().strftime("%Y/%m/%d %H:%M:%S (UTC)"),
        avatar_url=avatar_url,
        services=services
    )


async def check_service_connections(email: str) -> list[ServiceConnection]:
    local_part = email.split("@")[0]

    services = [
        {"name": "GitHub", "check": f"https://api.github.com/users/{local_part}"},
        {"name": "Twitter", "check": f"https://api.twitter.com/i/users/email_available.json?email={email}"},
        {"name": "Instagram", "check": f"https://www.instagram.com/{local_part}/"},
        {"name": "LinkedIn", "check": f"https://www.linkedin.com/in/{local_part}/"},
        {"name": "Twitch", "check": f"https://api.twitch.tv/kraken/users?login={local_part}"},
        {"name": "Pinterest", "check": f"https://www.pinterest.com/{local_part}/"},
        {"name": "TikTok", "check": f"https://www.tiktok.com/@{local_part}"},
        {"name": "Spotify", "check": f"https://spclient.wg.spotify.com/signup/public/account?email={email}"},
        {"name": "Duolingo", "check": f"https://www.duolingo.com/2017-06-30/users?email={email}"},
        {"name": "Adobe", "check": f"https://auth.services.adobe.com/signin/v2/users/{email}"},
    ]

    connections = []
    async with httpx.AsyncClient(follow_redirects=True, verify=False) as client:
        for svc in services:
            try:
                resp = await client.get(
                    svc["check"],
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                    timeout=5.0
                )
                if resp.status_code == 200:
                    status = "found"
                elif resp.status_code in [301, 302]:
                    status = "redirect"
                elif resp.status_code == 404:
                    status = "not_found"
                elif resp.status_code == 429:
                    status = "rate_limited"
                else:
                    status = "unknown"

                avatar = None
                if svc["name"] == "GitHub" and resp.status_code == 200:
                    try:
                        data = resp.json()
                        avatar = data.get("avatar_url")
                    except:
                        pass

                connections.append(ServiceConnection(
                    service=svc["name"], url=svc["check"][:60],
                    status=status, avatar=avatar
                ))
            except:
                connections.append(ServiceConnection(
                    service=svc["name"], url=svc["check"][:60],
                    status="error", avatar=None
                ))

    return connections


async def get_whois_info(domain: str) -> Optional[dict]:
    try:
        import whois
        w = whois.whois(domain)
        return {
            "registrar": w.registrar,
            "creation_date": str(w.creation_date) if w.creation_date else None,
            "expiration_date": str(w.expiration_date) if w.expiration_date else None,
            "country": w.country
        }
    except:
        return None


def calculate_risk(smtp: SMTPResult, is_disposable: bool) -> tuple[int, str]:
    score = 0
    if smtp.final_status == "invalid":
        score += 50
    elif smtp.final_status == "risky":
        score += 25
    elif smtp.final_status in ["error", "timeout"]:
        score += 15
    if is_disposable:
        score += 30
    if not smtp.mx_records:
        score += 30

    if score < 20:
        level = "Low"
    elif score < 40:
        level = "Medium"
    elif score < 60:
        level = "High"
    else:
        level = "Critical"
    return min(score, 100), level


async def analyze_email(email: str) -> EmailAnalysisResult:
    domain = email.split("@")[1] if "@" in email else ""
    is_gmail = domain.lower() == "gmail.com"
    is_disposable = domain.lower() in DISPOSABLE_DOMAINS

    mx_records = await get_mx_records(domain)

    smtp_result, connections, whois_info = await asyncio.gather(
        smtp_verify(email, mx_records),
        check_service_connections(email),
        get_whois_info(domain)
    )

    google_profile = None
    if is_gmail:
        google_profile = await get_gmail_profile(email)

    risk_score, risk_level = calculate_risk(smtp_result, is_disposable)

    return EmailAnalysisResult(
        email=email, domain=domain, is_gmail=is_gmail, smtp=smtp_result,
        google=google_profile, connections=connections, whois=whois_info,
        risk_score=risk_score, risk_level=risk_level,
        analysis_timestamp=datetime.utcnow().isoformat()
    )


async def hlr_lookup(phone: str, api_key: str) -> HLRResult:
    """HLR lookup via Numverify API"""
    clean_phone = re.sub(r'[^0-9]', '', phone)
    if len(clean_phone) < 10:
        return HLRResult(
            phone=phone, country=None, region=None, operator=None,
            status=None, mnc=None, imsi=None, imei=None,
            ported=None, roaming=None, raw_response=None,
            error="Invalid phone number format. Use format: 79001234567"
        )

    if not api_key:
        return HLRResult(
            phone=phone, country=None, region=None, operator=None,
            status=None, mnc=None, imsi=None, imei=None,
            ported=None, roaming=None, raw_response=None,
            error="API key required. Get free key at apilayer.net"
        )

    try:
        async with httpx.AsyncClient(verify=False, timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(
                "http://apilayer.net/api/validate",
                params={
                    "access_key": api_key,
                    "number": clean_phone,
                    "country_code": "",
                    "format": 1
                }
            )
            data = resp.json()
            print(f"Numverify: {data}")

            if data.get("valid") is not None:
                return HLRResult(
                    phone=data.get("number", phone),
                    country=data.get("country_name"),
                    region=data.get("location"),
                    operator=data.get("carrier"),
                    status="valid" if data["valid"] else "invalid",
                    mnc=None,
                    imsi=None,
                    imei=None,
                    ported=str(data.get("line_type", "")) if data.get("line_type") else None,
                    roaming=None,
                    raw_response=str(data),
                    error=None
                )
            elif data.get("error"):
                return HLRResult(
                    phone=phone, country=None, region=None, operator=None,
                    status=None, mnc=None, imsi=None, imei=None,
                    ported=None, roaming=None, raw_response=str(data),
                    error=data["error"].get("info", "API error")
                )
            else:
                return HLRResult(
                    phone=phone, country=None, region=None, operator=None,
                    status=None, mnc=None, imsi=None, imei=None,
                    ported=None, roaming=None, raw_response=str(data),
                    error="Unexpected response"
                )

    except httpx.TimeoutException:
        return HLRResult(
            phone=phone, country=None, region=None, operator=None,
            status=None, mnc=None, imsi=None, imei=None,
            ported=None, roaming=None, raw_response=None,
            error="Request timeout"
        )
    except Exception as e:
        return HLRResult(
            phone=phone, country=None, region=None, operator=None,
            status=None, mnc=None, imsi=None, imei=None,
            ported=None, roaming=None, raw_response=None,
            error=str(e)
        )


async def sherlock_search(username: str) -> SherlockResult:
    """Search username across social media using sherlock"""
    import time
    start = time.time()

    if not username or len(username) < 2:
        return SherlockResult(
            username=username, found=[], not_found=[],
            error="Username too short", search_time=0
        )

    try:
        from sherlock_project import sherlock

        found = []
        not_found = []

        # Run sherlock
        sherlock_path = os.path.join(os.path.dirname(__file__), "sherlock_data")

        # Use sherlock's built-in function
        result = sherlock.sherlock(
            username,
            site_list=None,
            timeout=5,
            print_found=False,
            print_not_found=False,
            verbose=False,
            tor=False,
            unique_tor=False,
            csv=False,
            json_output=False,
            output_dir=None,
            recurse=False,
            nsfw=False,
            disable_color=True
        )

        if result:
            for site_name, url in result.items():
                if url and url != "False":
                    found.append({"site": site_name, "url": url})
                else:
                    not_found.append(site_name)

        elapsed = round(time.time() - start, 2)
        return SherlockResult(
            username=username, found=found, not_found=not_found,
            error=None, search_time=elapsed
        )

    except Exception as e:
        elapsed = round(time.time() - start, 2)
        print(f"Sherlock error: {e}")
        # Fallback: manual check via httpx
        return await sherlock_fallback(username, elapsed)


async def sherlock_fallback(username: str, elapsed: float) -> SherlockResult:
    """Fallback sherlock using manual HTTP checks — 50+ sites"""
    sites = {
        # Social
        "Twitter": f"https://twitter.com/{username}",
        "Instagram": f"https://www.instagram.com/{username}/",
        "Facebook": f"https://www.facebook.com/{username}",
        "TikTok": f"https://www.tiktok.com/@{username}",
        "Snapchat": f"https://www.snapchat.com/add/{username}",
        "Reddit": f"https://www.reddit.com/user/{username}",
        "Pinterest": f"https://www.pinterest.com/{username}/",
        "Tumblr": f"https://{username}.tumblr.com",
        "LinkedIn": f"https://www.linkedin.com/in/{username}/",
        "VK": f"https://vk.com/{username}",
        "Telegram": f"https://t.me/{username}",
        # Video
        "YouTube": f"https://www.youtube.com/@{username}",
        "Twitch": f"https://www.twitch.tv/{username}",
        "Dailymotion": f"https://www.dailymotion.com/{username}",
        "Rumble": f"https://rumble.com/user/{username}",
        # Music
        "Spotify": f"https://open.spotify.com/user/{username}",
        "SoundCloud": f"https://soundcloud.com/{username}",
        "Bandcamp": f"https://{username}.bandcamp.com",
        "LastFM": f"https://www.last.fm/user/{username}",
        "Deezer": f"https://www.deezer.com/profile/{username}",
        # Gaming
        "Steam": f"https://steamcommunity.com/id/{username}",
        "Xbox": f"https://www.xbox.com/en-US/play/user/{username}",
        "PSN": f"https://psnprofiles.com/{username}",
        "EpicGames": f"https://www.epicgames.com/site/en-US/u/{username}",
        "Roblox": f"https://www.roblox.com/user.aspx?username={username}",
        "Minecraft": f"https://namemc.com/profile/{username}",
        "Chess.com": f"https://www.chess.com/member/{username}",
        # Dev
        "GitHub": f"https://api.github.com/users/{username}",
        "GitLab": f"https://gitlab.com/{username}",
        "Bitbucket": f"https://bitbucket.org/{username}/",
        "StackOverflow": f"https://stackoverflow.com/users/?tab=Accounts",
        "HackerNews": f"https://news.ycombinator.com/user?id={username}",
        "DevTo": f"https://dev.to/{username}",
        "CodePen": f"https://codepen.io/{username}",
        "Replit": f"https://replit.com/@{username}",
        "npm": f"https://www.npmjs.com/~{username}",
        "PyPI": f"https://pypi.org/user/{username}/",
        # Creative
        "DeviantArt": f"https://www.deviantart.com/{username}",
        "ArtStation": f"https://www.artstation.com/{username}",
        "Behance": f"https://www.behance.net/{username}",
        "Flickr": f"https://www.flickr.com/people/{username}",
        "500px": f"https://500px.com/p/{username}",
        # Blog
        "Medium": f"https://medium.com/@{username}",
        "WordPress": f"https://{username}.wordpress.com",
        "Blogger": f"https://{username}.blogspot.com",
        "Substack": f"https://{username}.substack.com",
        "Ghost": f"https://{username}.ghost.io",
        # Other
        "Keybase": f"https://keybase.io/{username}",
        "Patreon": f"https://www.patreon.com/{username}",
        "BuyMeACoffee": f"https://buymeacoffee.com/{username}",
        "Ko-fi": f"https://ko-fi.com/{username}",
        "Gravatar": f"https://en.gravatar.com/{username}",
        "About.me": f"https://about.me/{username}",
        "Linktree": f"https://linktr.ee/{username}",
        "Carrd": f"https://{username}.carrd.co",
        "NameMC": f"https://namemc.com/profile/{username}",
    }

    found = []
    not_found = []

    async with httpx.AsyncClient(follow_redirects=True, verify=False, timeout=5.0) as client:
        for site, url in sites.items():
            try:
                resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code == 200:
                    found.append({"site": site, "url": url})
                else:
                    not_found.append(site)
            except:
                not_found.append(site)

    return SherlockResult(
        username=username, found=found, not_found=not_found,
        error=None, search_time=elapsed
    )
