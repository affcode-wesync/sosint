import httpx
import re
import json
import uuid
import os
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
    error: str = ""


def _extract_social_links(text: str) -> list[FaceSearchResult]:
    """Extract VK and OK profile links from HTML/JSON text."""
    results = []
    seen = set()

    # VK patterns
    vk_patterns = [
        r'https?://(?:vk\.com|vk\.ru)/[a-zA-Z0-9_.]+',
        r'https?://(?:m\.vk\.com)/[a-zA-Z0-9_.]+',
    ]

    # OK patterns
    ok_patterns = [
        r'https?://(?:odnoklassniki\.ru|ok\.ru)/[a-zA-Z0-9_/]+',
    ]

    for pattern in vk_patterns + ok_patterns:
        for match in re.finditer(pattern, text):
            url = match.group(0).rstrip('/')
            # Skip generic VK/OK URLs (not profiles)
            if any(skip in url for skip in ['/search', '/feed', '/friends', '/groups',
                                             '/games', '/market', '/video', '/doc',
                                             '/poll', '/note', '/product']):
                continue
            # Skip if just vk.com or ok.ru without profile path
            path = url.split('/', 3)[-1] if '/' in url.split('://')[1] else ''
            if not path or path in ['feed', 'search']:
                continue

            if url not in seen:
                seen.add(url)
                source = 'VK' if 'vk' in url else 'OK'
                results.append(FaceSearchResult(url=url, source=source))

    return results


async def face_search_yandex(image_bytes: bytes, filename: str = "photo.jpg") -> FaceSearchResponse:
    """Search for faces via Yandex reverse image search."""
    response = FaceSearchResponse(query_id=str(uuid.uuid4())[:8])

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=20,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
            }
        ) as client:
            # Step 1: Upload image to Yandex
            upload_resp = await client.post(
                "https://yandex.ru/images/search",
                params={
                    "rpt": "imageview",
                    "format": "json",
                    "request": '{"blocks":[{"block":"cbir-collections__get-cbir-id"}]}',
                },
                files={"upfile": (filename, image_bytes, "image/jpeg")},
            )

            if upload_resp.status_code != 200:
                response.error = f"Yandex upload failed: HTTP {upload_resp.status_code}"
                return response

            try:
                data = upload_resp.json()
            except Exception:
                response.error = "Failed to parse Yandex response"
                return response

            # Extract CBIR ID from response
            cbir_id = None
            try:
                blocks = data.get("images_found", {}).get("blocks", [])
                for block in blocks:
                    if block.get("block") == "cbir-collections__get-cbir-id":
                        cbir_id = block.get("data", {}).get("cbir_id")
                        break
            except Exception:
                pass

            if not cbir_id:
                # Try alternative response structure
                cbir_id = data.get("images_found", {}).get("cbir_id")
                if not cbir_id:
                    # Try to get it from text response
                    text = upload_resp.text
                    match = re.search(r'"cbir_id"\s*:\s*"([^"]+)"', text)
                    if match:
                        cbir_id = match.group(1)

            if not cbir_id:
                response.error = "Could not extract search ID from Yandex"
                # Try to find any social links in the raw response
                links = _extract_social_links(upload_resp.text)
                for link in links:
                    if link.source == 'VK':
                        response.vk_profiles.append(link)
                    else:
                        response.ok_profiles.append(link)
                response.results = links
                response.total_found = len(links)
                return response

            response.query_id = cbir_id

            # Step 2: Get search results using CBIR ID
            results_resp = await client.get(
                "https://yandex.ru/images/search",
                params={
                    "rpt": "imageview",
                    "cbir_id": cbir_id,
                    "format": "json",
                    "request": json.dumps({
                        "blocks": [
                            {"block": "b-page_type_search-by-image__link"},
                            {"block": "b-page_type_search-by-image__serp-list"},
                        ]
                    }),
                },
            )

            # Parse results
            all_text = results_resp.text

            # Also try to get more results pages
            try:
                rdata = results_resp.json()
                # Extract all URLs from JSON
                all_text += json.dumps(rdata)
            except Exception:
                pass

            # Extract all links from the response
            all_links = _extract_social_links(all_text)

            # Also extract image thumbnails from Yandex results
            thumb_pattern = r'"url"\s*:\s*"(https?://avatars\.mdsrcdn\.net[^"]+)"'
            thumbnails = re.findall(thumb_pattern, all_text)

            # Categorize results
            for link in all_links:
                if link.source == 'VK':
                    response.vk_profiles.append(link)
                else:
                    response.ok_profiles.append(link)

            response.results = all_links
            response.other_results = [
                r for r in all_links if r.source not in ('VK', 'OK')
            ]
            response.total_found = len(all_links)

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
            timeout=20,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            }
        ) as client:
            # Search by URL
            search_resp = await client.get(
                "https://yandex.ru/images/search",
                params={
                    "rpt": "imageview",
                    "url": image_url,
                    "format": "json",
                    "request": json.dumps({
                        "blocks": [
                            {"block": "b-page_type_search-by-image__link"},
                        ]
                    }),
                },
            )

            all_text = search_resp.text

            # Extract CBIR ID for potential follow-up
            match = re.search(r'"cbir_id"\s*:\s*"([^"]+)"', all_text)
            if match:
                response.query_id = match.group(1)

            # Extract social links
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
