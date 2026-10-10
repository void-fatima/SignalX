"""Fixed-host public APIs. No arbitrary page fetching, model calls or fallback."""
import base64
import hashlib
import ipaddress
import json
import os
import re
from contextlib import nullcontext
from html import unescape
from html.parser import HTMLParser
from typing import Protocol
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode, unquote
import httpx
from app.discovery.schemas import DiscoveryResult, SearchInput, SourceStatus

MAX_BODY_BYTES = 2_000_000

class DiscoveryError(Exception):
    def __init__(self, code, message, status=502, request_count=0):
        super().__init__(message)
        self.code, self.status, self.request_count = code, status, request_count

def validate_no_credentials(value):
    """Reject credential echoes before retention, including common encoded forms.

    Inspect keys as well as values; never interpolate source data into errors.
    Decoding is bounded and does not execute or fetch source content.
    """
    secrets = [os.getenv(name, "").strip() for name in
        ("BRAVE_SEARCH_API_KEY", "GOOGLE_PLACES_API_KEY")]
    needles = set()
    for secret in filter(None, secrets):
        needles.add(secret)
        raw = secret.encode("utf-8")
        for encoded in (base64.b64encode(raw).decode(), base64.urlsafe_b64encode(raw).decode()):
            needles.update((encoded, encoded.rstrip("=")))
        needles.update((raw.hex(), raw.hex().upper()))
    if not needles:
        return
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            pending.extend(item.keys()); pending.extend(item.values())
        elif isinstance(item, (list, tuple)):
            pending.extend(item)
        elif isinstance(item, str):
            for _ in range(5):
                if any(needle in item for needle in needles):
                    raise DiscoveryError("source_invalid_output", "Source response contains unsafe data.", 502, 1)
                decoded = re.sub(r"\\(?:u([0-9a-fA-F]{4})|x([0-9a-fA-F]{2}))",
                    lambda match: chr(int(match.group(1) or match.group(2), 16)), unescape(unquote(item)))
                if decoded == item:
                    break
                item = decoded
            else:
                # Reject further encoded layers rather than letting an unchecked value escape.
                raise DiscoveryError("source_invalid_output", "Source response contains excessive encoding.", 502, 1)


class DiscoveryProvider(Protocol):
    def search(self, inputs: SearchInput) -> list[DiscoveryResult]: ...

class _PlainText(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[]; self.hidden=0
    def handle_starttag(self, tag, attrs):
        if tag in {"script","style"}: self.hidden+=1
    def handle_endtag(self, tag):
        if tag in {"script","style"}: self.hidden=max(0,self.hidden-1)
    def handle_data(self, data):
        if not self.hidden: self.parts.append(data)

def plain(value, limit=800):
    if not isinstance(value,str): return ""
    parser=_PlainText(); parser.feed(unescape(value[:20000]))
    return " ".join(" ".join(parser.parts).split())[:limit]

def public_url(value):
    """Links only, never fetched. Fixed API hosts prevent DNS/rebinding SSRF."""
    if not isinstance(value,str) or len(value)>2000 or "\\" in value or any(ord(c)<33 for c in value):
        raise ValueError("Unsafe source URL")
    parts=urlsplit(value)
    host=(parts.hostname or "").lower().rstrip(".")
    if parts.scheme != "https" or parts.username or parts.password or parts.port not in (None,443):
        raise ValueError("Unsafe source URL")
    if not host or "." not in host or host.endswith((".localhost",".local",".internal",".test",".invalid")) or host in {"localhost","metadata.google.internal"}:
        raise ValueError("Unsafe source host")
    try: ipaddress.ip_address(host)
    except ValueError: pass
    else: raise ValueError("IP source links are not supported")
    if not re.fullmatch(r"[a-z0-9.-]+",host) or any(not part or part.startswith("-") or part.endswith("-") for part in host.split(".")):
        raise ValueError("Unsafe source host")
    query=[(k,v) for k,v in parse_qsl(parts.query,keep_blank_values=True) if not k.lower().startswith("utm_") and k.lower() not in {"gclid","fbclid"}]
    return urlunsplit(("https",host,parts.path or "/",urlencode(query),""))

def source_status(source):
    if source == "brave":
        configured=bool(os.getenv("BRAVE_SEARCH_API_KEY","").strip()) and os.getenv("DISCOVERY_BRAVE_STORAGE_ALLOWED","").lower() == "true"
        message="Brave web search; configure BRAVE_SEARCH_API_KEY and a plan permitting result storage (DISCOVERY_BRAVE_STORAGE_ALLOWED=true)."
    elif source == "places":
        configured=bool(os.getenv("GOOGLE_PLACES_API_KEY","").strip()) and os.getenv("DISCOVERY_PLACES_ENABLED","").lower() == "true"
        message="Optional billed Google Places ID-only search; configure GOOGLE_PLACES_API_KEY and DISCOVERY_PLACES_ENABLED=true after reviewing applicable terms. Only place IDs are retained."
    else:
        configured=True; message="Public company-specific job API; supply one known board slug. No universal company search."
    return SourceStatus(source=source,configured=configured,message=message)

class PublicAPIProvider:
    def __init__(self, source, *, client: httpx.Client | None = None):
        self.source, self.client=source,client

    def _request(self, client, method, url, **kwargs):
        try:
            with client.stream(method,url,timeout=12,follow_redirects=False,**kwargs) as response:
                if not response.is_success:
                    code={400:"invalid_search",401:"source_auth",403:"source_permission",404:"board_or_endpoint_missing",429:"source_rate_limit"}.get(response.status_code,"source_unavailable")
                    raise DiscoveryError(code,"Discovery source rejected the request; check configuration or quota.",502,1)
                data=bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data)>MAX_BODY_BYTES: raise DiscoveryError("source_response_too_large","Source response exceeds the 2 MB search budget. Try a smaller job board or a more specific search; no retry was made.",502,1)
                body = json.loads(data)
                validate_no_credentials(data.decode("utf-8", errors="replace"))
                validate_no_credentials(body)
                return body
        except DiscoveryError: raise
        except httpx.TimeoutException:
            raise DiscoveryError("source_timeout","Discovery source timed out. No automatic retry was made.",504,1) from None
        except (httpx.HTTPError,RuntimeError):
            raise DiscoveryError("source_transport","Discovery source could not be reached. No automatic retry was made.",502,1) from None
        except (ValueError,RecursionError):
            raise DiscoveryError("source_invalid_output","Discovery source returned invalid data.",502,1) from None

    def search(self, inputs):
        status=source_status(self.source)
        if not status.configured:
            raise DiscoveryError("configuration_required",status.message,503,0)
        manager=nullcontext(self.client) if self.client else httpx.Client(timeout=12,follow_redirects=False,trust_env=False)
        with manager as client:
            if self.source == "brave":
                key=os.getenv("BRAVE_SEARCH_API_KEY","").strip()
                params={"q":" ".join(filter(None,[inputs.keywords,inputs.industry,inputs.location])),"count":inputs.limit,"safesearch":"strict"}
                if inputs.country: params["country"]=inputs.country
                body=self._request(client,"GET","https://api.search.brave.com/res/v1/web/search",headers={"X-Subscription-Token":key,"Accept":"application/json"},params=params)
                if not isinstance(body,dict) or ("web" in body and not isinstance(body["web"],dict)) or ("web" not in body and body.get("type") != "search"):
                    raise DiscoveryError("source_invalid_output","Web result envelope is invalid.",502,1)
                items=body.get("web",{}).get("results",[])
            elif self.source == "greenhouse":
                body=self._request(client,"GET",f"https://boards-api.greenhouse.io/v1/boards/{inputs.board_slug}/jobs",params={"content":"false"})
                items=body.get("jobs") if isinstance(body,dict) else None
            elif self.source == "lever":
                items=self._request(client,"GET",f"https://api.lever.co/v0/postings/{inputs.board_slug}",params={"mode":"json","limit":20,"skip":0},headers={"Accept":"application/json"})
            elif self.source == "places":
                body=self._request(client,"POST","https://places.googleapis.com/v1/places:searchText",headers={"X-Goog-Api-Key":os.getenv("GOOGLE_PLACES_API_KEY","").strip(),"X-Goog-FieldMask":"places.id"},json={"textQuery":" ".join(filter(None,[inputs.keywords,inputs.industry,inputs.location,inputs.country])),"pageSize":inputs.limit})
                items=body.get("places",[]) if isinstance(body,dict) else None
            else: raise DiscoveryError("unsupported_source","Unsupported discovery source.",422,0)
        if not isinstance(items,list): raise DiscoveryError("source_invalid_output","Source result list is invalid.",502,1)
        results=[]; seen=set()
        for item in items:
            if not isinstance(item,dict): continue
            if self.source == "places":
                source_id=item.get("id")
                if not isinstance(source_id,str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}",source_id): continue
                url="https://www.google.com/maps/search/?"+urlencode({"api":"1","query":"place","query_place_id":source_id})
                # Do not retain names, addresses, excerpts or other Places content.
                title="Place ID: "+source_id; excerpt="Place ID returned by Google Places. Open the original Maps listing to review the business."; location=""
            elif self.source == "brave":
                url=item.get("url"); title=plain(item.get("title"),240); excerpt=plain(item.get("description")); location=""
                source_id=""
            else:
                source_id=str(item.get("id", "")); title=plain(item.get("title") if self.source == "greenhouse" else item.get("text"),200)
                title=f"{inputs.board_slug}: {title}"
                url=item.get("absolute_url") if self.source == "greenhouse" else item.get("hostedUrl")
                # Greenhouse listings deliberately omit full descriptions. Retain
                # actual listing evidence, not invented description text.
                excerpt=plain(item.get("title") if self.source == "greenhouse" else item.get("descriptionPlain"))
                loc=item.get("location") if self.source == "greenhouse" else item.get("categories")
                location=plain(loc.get("name" if self.source == "greenhouse" else "location"),200) if isinstance(loc,dict) else ""
                searchable=(title+" "+excerpt).casefold()
                if not all(word in searchable for word in inputs.keywords.casefold().split()): continue
                if inputs.location and inputs.location.casefold() not in location.casefold(): continue
            try: url=public_url(url)
            except (ValueError,TypeError): continue
            if not source_id: source_id=hashlib.sha256(url.encode()).hexdigest()
            if not title or not source_id or len(source_id)>200 or url in seen: continue
            seen.add(url)
            results.append(DiscoveryResult(source=self.source,source_id=source_id,title=title[:240],url=url,excerpt=excerpt,location=location,
                explanation="Hiring activity is a possible business signal, not evidence of buying intent." if self.source in {"greenhouse","lever"} else "Source match only; product fit and buying intent have not been verified."))
            if len(results)>=inputs.limit: break
        validate_no_credentials([result.model_dump() for result in results])
        return results

def get_discovery_provider(source):
    return PublicAPIProvider(source)
