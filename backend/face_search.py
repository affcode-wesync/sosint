import httpx
import re
import json
import uuid
import html as html_module
from typing import Optional
from pydantic import BaseModel


class FaceSearchResult(BaseModel):
    url: str
    title: str = ""
    source: str = ""
    thumbnail: str = ""


class FaceSearchResponse(BaseModel):
    query_id: str = ""
    results: list[FaceSearchResult] = []
    vk_profiles: list[FaceSearchResult] = []
    ok_profiles: list[FaceSearchResult] = []
    other_results: list[FaceSearchResult] = []
    total_found: int = 0
    search_url: str = ""
    error: str = ""


def _extract_social_links(text: str) -> list[FaceSearchResult]:
    """Extract VK and OK profile links from text."""
    results = []
    seen = set()

    patterns = [
        (r'https?://(?:vk\.com|vk\.ru)/[a-zA-Z0-9_.]+', 'VK'),
        (r'https?://m\.vk\.com/[a-zA-Z0-9_.]+', 'VK'),
        (r'https?://(?:odnoklassniki\.ru|ok\.ru)/[a-zA-Z0-9_/]+', 'OK'),
    ]

    skip_words = ['/search', '/feed', '/friends', '/groups', '/games', '/market',
                  '/video', '/doc', '/poll', '/note', '/product', '/im',
                  '/photo', '/club', '/apps', '/al', '/e-', '/login',
                  'vk.com/audio', 'vk.com/video', 'vk.com/write']

    for pattern, source in patterns:
        for match in re.finditer(pattern, text):
            url = match.group(0).rstrip('/')
            if any(skip in url for skip in skip_words):
                continue
            path = url.split('/', 3)[-1] if '/' in url.split('://')[1] else ''
            if not path or len(path) < 2:
                continue
            if url not in seen:
                seen.add(url)
                results.append(FaceSearchResult(url=url, source=source))

    return results


def _extract_state_data(html_text: str) -> dict:
    """Extract embedded JavaScript state data from Yandex HTML."""
    # Look for window.__INIT_STATE__ or similar embedded state
    state_patterns = [
        r'window\.__INIT_STATE__\s*=\s*({.*?});',
        r'data-state="([^"]+)"',
        r'"serpList"\s*:\s*({[^}]+})',
    ]

    all_data = {}

    for pattern in state_patterns:
        matches = re.findall(pattern, html_text, re.DOTALL)
        for match in matches:
            try:
                if match.startswith('{'):
                    data = json.loads(match)
                    all_data.update(data)
                else:
                    # HTML-encoded JSON
                    decoded = html_module.unescape(match)
                    data = json.loads(decoded)
                    all_data.update(data)
            except (json.JSONDecodeError, ValueError):
                pass

    return all_data


async def face_search_yandex(image_bytes: bytes, filename: str = "photo.jpg") -> FaceSearchResponse:
    """Search for faces via Yandex reverse image search."""
    response = FaceSearchResponse(query_id=str(uuid.uuid4())[:8])

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=25,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
            }
        ) as client:
            # Step 1: Upload image to Yandex
            upload_resp = await client.post(
                "https://yandex.ru/images/search",
                params={"rpt": "imageview"},
                files={"upfile": (filename, image_bytes, "image/jpeg")},
            )

            if upload_resp.status_code != 200:
                response.error = f"Yandex upload failed: HTTP {upload_resp.status_code}"
                return response

            html_text = upload_resp.text

            # Extract serp-id
            serp_ids = re.findall(r'serp[_-]?id["\s:=]+["\']([^"\']+)', html_text)
            if serp_ids:
                response.query_id = serp_ids[0]

            # Build search URL for user
            response.search_url = str(upload_resp.url)

            # Extract cbir-id from embedded state
            cbir_match = re.search(r'"cbirId"\s*:\s*"([^"]+)"', html_text)
            cbir_id = cbir_match.group(1) if cbir_match else ""

            # Try to extract image search results from embedded state
            # Look for cbirSites, cbirSimilar, etc. in the HTML
            all_text = html_text

            # Extract from embedded JSON state blocks
            state_data = _extract_state_data(html_text)
            if state_data:
                # Look for sites/references in state data
                all_text += json.dumps(state_data)

            # If we have a cbir-id, try the apphost API for more results
            if cbir_id:
                try:
                    apphost_resp = await client.get(
                        "https://yandex.ru/images/search",
                        params={
                            "rpt": "imageview",
                            "cbir_id": cbir_id,
                        },
                        headers={"Referer": upload_resp.url},
                    )
                    all_text += apphost_resp.text
                except Exception:
                    pass

            # Extract all social links
            all_links = _extract_social_links(all_text)

            for link in all_links:
                if link.source == 'VK':
                    response.vk_profiles.append(link)
                else:
                    response.ok_profiles.append(link)

            response.results = all_links
            response.other_results = [r for r in all_links if r.source not in ('VK', 'OK')]
            response.total_found = len(all_links)

            if response.total_found == 0:
                # No social links found in HTML — results are loaded via JS in browser
                # Return the search URL so frontend can redirect or show message
                response.error = ""
                response.search_url = f"https://yandex.ru/images/search?rpt=imageview"

    except httpx.TimeoutException:
        response.error = "Search timed out. Please try again."
    except Exception as e:
        response.error = f"Search error: {str(e)}"

    return response


async def face_search_url(image_url: str) -> FaceSearchResponse:
    """Search for faces using a URL image."""
    response = FaceSearchResponse(query_id=str(uuid.uuid4())[:8])

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=25,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ru-RU,ru;q=0.9",
            }
        ) as client:
            search_resp = await client.get(
                "https://yandex.ru/images/search",
                params={"rpt": "imageview", "url": image_url},
            )

            html_text = search_resp.text
            response.search_url = str(search_resp.url)

            serp_ids = re.findall(r'serp[_-]?id["\s:=]+["\']([^"\']+)', html_text)
            if serp_ids:
                response.query_id = serp_ids[0]

            all_text = html_text
            state_data = _extract_state_data(html_text)
            if state_data:
                all_text += json.dumps(state_data)

            all_links = _extract_social_links(all_text)

            for link in all_links:
                if link.source == 'VK':
                    response.vk_profiles.append(link)
                else:
                    response.ok_profiles.append(link)

            response.results = all_links
            response.total_found = len(all_links)

    except httpx.TimeoutException:
        response.error = "Search timed out"
    except Exception as e:
        response.error = f"Search error: {str(e)}"

    return response
