"""URL canonicalisation and site identity.

Rules imported from:
  * adbar/courlan + adbar/trafilatura  — tracking-parameter stripping, path cleanup,
    same-site comparison via registrable domain
  * searxng/searxng                     — scheme/host folding, default-document removal
  * scrapy/scrapy (utils.url, w3lib)    — fragment and userinfo handling
  * clearurls / link-cleaner tradition  — campaign parameter blocklist

Everything is deterministic and testable in isolation.
"""
from __future__ import annotations

import re
import urllib.parse
from functools import lru_cache

try:  # optional, but installed by requirements
    import tldextract

    _TLD = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)
except Exception:  # pragma: no cover
    _TLD = None

# Campaign / analytics / session parameters that never change the resource.
TRACKING_PARAMS: frozenset[str] = frozenset("""
utm_source utm_medium utm_campaign utm_term utm_content utm_id utm_name utm_cid
utm_reader utm_referrer utm_social utm_social-type utm_brand
gclid gclsrc dclid gbraid wbraid fbclid fb_action_ids fb_action_types fb_source
msclkid mc_cid mc_eid mkt_tok igshid twclid ttclid li_fat_id s_cid vero_id yclid
_yclid _ga _gl _hsenc _hsmi hsa_cam hsa_grp hsa_mt hsa_src hsa_ad hsa_acc hsa_net
hsa_kw hsa_tgt hsa_ver hsCtaTracking ref ref_src ref_url referrer referer source
src spm scm sc_cid icid scid campaign campaignid ncid sr_share share share_id
trk tracking_id trackingid track_uid piwik_campaign piwik_kwd pk_campaign pk_kwd
pk_source pk_medium pk_content pk_cid mtm_campaign mtm_source mtm_medium
mtm_content mtm_keyword blatantcounty
""".split())

SESSION_PARAMS: frozenset[str] = frozenset("""
phpsessid jsessionid sessionid session_id aspsessionid cfid cftoken sid
__cf_bm _csrf csrftoken xsid lbc cookie _session request_id
""".split())

DEFAULT_DOCS = frozenset("""
index.html index.htm index.php index.asp index.aspx default.asp default.aspx
default.htm home.html main.html
""".split())

UNRESERVED = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")


def _strip_percent(path: str) -> str:
    """Decode percent-escapes that represent unreserved characters (RFC 3986 §6.2.2.2)."""
    def repl(match: re.Match[str]) -> str:
        char = chr(int(match.group(1), 16))
        return char if char in UNRESERVED else match.group(0).upper()

    return re.sub(r"%([0-9a-fA-F]{2})", repl, path)


def _normalise_path(path: str) -> str:
    if not path:
        return "/"
    path = _strip_percent(path)
    path = re.sub(r"/{2,}", "/", path)
    segments: list[str] = []
    for segment in path.split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            if segments:
                segments.pop()
            continue
        segments.append(segment)
    trailing = path.endswith("/")
    out = "/" + "/".join(segments)
    if trailing and len(out) > 1:
        out += "/"
    return out


@lru_cache(maxsize=8192)
def canonicalize(url: str, base: str | None = None) -> str:
    """Return a stable dedupe key for a URL. Never raises."""
    raw = (url or "").strip()
    if not raw:
        return ""
    if base:
        try:
            raw = urllib.parse.urljoin(base, raw)
        except ValueError:
            return raw
    try:
        parts = urllib.parse.urlsplit(raw)
    except ValueError:
        return _courlan_fallback(raw)
    if not parts.scheme:
        parts = urllib.parse.urlsplit("https://" + raw.lstrip("/"))

    scheme = (parts.scheme or "https").lower()
    if scheme not in ("http", "https", "ftp"):
        scheme = "https"
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    try:
        host = host.encode("idna").decode("ascii")
    except (UnicodeError, ValueError):
        pass
    port = parts.port
    netloc = host
    if port and port not in (80, 443):
        netloc = f"{host}:{port}"

    path = _normalise_path(parts.path)
    last = path.rsplit("/", 1)[-1].lower()
    if last in DEFAULT_DOCS:
        path = path.rsplit("/", 1)[0] or "/"
        if not path.endswith("/"):
            path += "/"

    kept: list[tuple[str, str]] = []
    dropped_session = False
    for key, value in urllib.parse.parse_qsl(parts.query, keep_blank_values=False):
        low = key.lower()
        if low in TRACKING_PARAMS:
            continue
        if low in SESSION_PARAMS:
            dropped_session = True
            continue
        kept.append((key, value))
    kept.sort()
    query = urllib.parse.urlencode(kept, doseq=True) if kept else ""

    return urllib.parse.urlunsplit((scheme, netloc, path, query, ""))


def registrable(url: str) -> str:
    """Registrable domain ('blog.example.co.za' → 'example.co.za')."""
    host = urllib.parse.urlsplit(url if "//" in url else "//" + url).hostname or ""
    host = host.lower().removeprefix("www.")
    if _TLD is not None:
        try:
            ext = _TLD(host)
            if ext.domain and ext.suffix:
                return f"{ext.domain}.{ext.suffix}"
        except Exception:
            pass
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) > 2 else host


def same_site(a: str, b: str) -> bool:
    return bool(a and b and registrable(a) == registrable(b))


def has_session_token(url: str) -> bool:
    try:
        keys = {k.lower() for k, _ in urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query)}
    except ValueError:
        return False
    return bool(keys & SESSION_PARAMS)


def looks_like_file(url: str) -> bool:
    path = urllib.parse.urlsplit(url).path
    last = path.rsplit("/", 1)[-1]
    if "." not in last:
        return False
    ext = last.rsplit(".", 1)[-1].lower()
    return 1 <= len(ext) <= 6 and ext.isalnum() and ext not in {"html", "htm", "php", "asp", "aspx", "jsp"}
