"""Self-hosted files: the hosts people actually put APKs, archives and dumps on.

The 119 engines are indexes of *documents* — grants, papers, datasets, portals.
None of them look inside MediaFire, and none of them ask APKPure or archive.org's
software collection anything, so "apk" used to come back as a paper about water
that happened to contain the letters. These adapters query the file hosts
themselves, in their own vocabulary, and report a file with its real extension.

Every one of them is best-effort: a host that renames a form, throws up a
challenge or blocks a datacenter IP returns nothing and says so in the status
line. Nothing here filters, ranks down or hides anything — the ordering is the
engine's job, done once, at the end.
"""
from __future__ import annotations

import asyncio
import re
from typing import Any
from urllib.parse import quote, unquote

from .base import HuntContext, Provider, RawHit

DEFAULT_TYPES = ("apk", "xapk", "zip", "7z", "rar", "pdf", "iso", "exe", "dmg", "epub")


def _wanted(ctx: HuntContext) -> list[str]:
    """The extensions this hunt asked for, or a sensible file default."""
    types = [t.lower().lstrip(".") for t in (ctx.file_types or []) if t]
    return types or list(DEFAULT_TYPES)


def _text(ctx: HuntContext) -> str:
    """What to search a host with: the words, minus the type words."""
    terms = (ctx.plan.terms or ctx.plan.query or "").strip()
    if terms:
        return terms
    # "apk" on its own is a browse, not a search
    return " ".join(_wanted(ctx)[:2])


def _rows(payload: Any) -> list[Any]:
    if isinstance(payload, dict):
        for key in ("response", "docs", "results", "data", "items"):
            value = payload.get(key)
            if isinstance(value, dict):
                nested = value.get("docs") or value.get("results")
                if isinstance(nested, list):
                    return nested
            if isinstance(value, list):
                return value
        return []
    return payload if isinstance(payload, list) else []


class MediaFire(Provider):
    id, name, family, layer = "mediafire", "MediaFire", "filehost", "remote"
    description = "MediaFire's own file search — direct download pages, filenames intact."
    lenses = ("files", "all")
    homepage = "https://www.mediafire.com/"
    weight = 3.2

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        text = _text(ctx)
        out: list[RawHit] = []
        for endpoint in (f"https://www.mediafire.com/?q={quote(text)}",
                         f"https://www.mediafire.com/search/?q={quote(text)}"):
            try:
                resp = await ctx.client.get(endpoint, headers={"Accept": "text/html"})
                if resp.status_code >= 400:
                    continue
            except Exception:
                continue
            html = resp.text or ""
            seen: set[str] = set()
            for match in re.finditer(
                    r'href="(https?://(?:www\.)?mediafire\.com/file/[^"]+)"', html):
                url = match.group(1)
                if url in seen:
                    continue
                seen.add(url)
                name = unquote(url.rstrip("/").split("/")[-1])
                out.append(RawHit(
                    url=url, title=name or "MediaFire file",
                    snippet=f"MediaFire · {name}", kind="file",
                    tags=("filehost", "mediafire"),
                    meta={"host": "mediafire", "filename": name},
                ))
                if len(out) >= max(8, ctx.limit):
                    break
            if out:
                break
        return out


class APKPure(Provider):
    id, name, family, layer = "apkpure", "APKPure", "filehost", "remote"
    description = "Android packages by name — APK, XAPK and OBB, with versions."
    lenses = ("files", "all")
    homepage = "https://apkpure.com/"
    weight = 3.0

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        text = _text(ctx)
        out: list[RawHit] = []
        try:
            resp = await ctx.client.get(f"https://apkpure.com/search?q={quote(text)}",
                                        headers={"Accept": "text/html"})
        except Exception:
            return []
        if resp.status_code >= 400:
            return []
        seen: set[str] = set()
        for match in re.finditer(
                r'href="(?:https?://apkpure\.com)?(/([a-z0-9][a-z0-9.\-]*)/'
                r'([a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+))"', resp.text or "", re.I):
            path, title, package = match.group(1), match.group(2), match.group(3)
            url = f"https://apkpure.com{path}"
            if url in seen:
                continue
            seen.add(url)
            out.append(RawHit(
                url=url, title=title.replace("-", " ").strip() or package,
                snippet=f"APK · {package}", kind="file",
                tags=("filehost", "apk", "apkpure"),
                meta={"host": "apkpure", "package": package, "ext_hint": "apk"},
            ))
            if len(out) >= max(8, ctx.limit):
                break
        return out


class APKMirror(Provider):
    id, name, family, layer = "apkmirror", "APKMirror", "filehost", "remote"
    description = "Versioned APK uploads with signatures and architectures."
    lenses = ("files", "all")
    homepage = "https://www.apkmirror.com/"
    weight = 2.8

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        text = _text(ctx)
        try:
            resp = await ctx.client.get(
                f"https://www.apkmirror.com/?post_type=app_release&searchtype=apk"
                f"&s={quote(text)}", headers={"Accept": "text/html"})
        except Exception:
            return []
        if resp.status_code >= 400:
            return []
        out: list[RawHit] = []
        seen: set[str] = set()
        for match in re.finditer(r'href="(/apk/[^"]+/)"', resp.text or ""):
            url = "https://www.apkmirror.com" + match.group(1)
            if url in seen:
                continue
            seen.add(url)
            name = [part for part in match.group(1).split("/") if part and part != "apk"]
            out.append(RawHit(
                url=url, title=(name[-1].replace("-", " ") if name else "APK"),
                snippet="APK · APKMirror", kind="file",
                tags=("filehost", "apk", "apkmirror"),
                meta={"host": "apkmirror", "ext_hint": "apk"},
            ))
            if len(out) >= max(8, ctx.limit):
                break
        return out


class Fdroid(Provider):
    id, name, family, layer = "fdroid", "F-Droid", "filehost", "remote"
    description = "Free-software Android packages, no login, direct APK links."
    lenses = ("files", "all")
    homepage = "https://f-droid.org/"
    weight = 2.6

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        text = _text(ctx)
        try:
            resp = await ctx.client.get(f"https://search.f-droid.org/?q={quote(text)}&lang=en",
                                        headers={"Accept": "text/html"})
        except Exception:
            return []
        if resp.status_code >= 400:
            return []
        out: list[RawHit] = []
        seen: set[str] = set()
        for match in re.finditer(r'href="(?:https?://f-droid\.org)?(/[a-z]{2}/packages/([^"/]+)/)"',
                                 resp.text or ""):
            package = match.group(2)
            url = f"https://f-droid.org/en/packages/{package}/"
            if url in seen:
                continue
            seen.add(url)
            out.append(RawHit(
                url=url, title=package, snippet=f"APK · {package}", kind="file",
                tags=("filehost", "apk", "fdroid"),
                meta={"host": "f-droid.org", "package": package, "ext_hint": "apk"},
            ))
            if len(out) >= max(8, ctx.limit):
                break
        return out


def _one(value: Any) -> str:
    """archive.org returns a string *or a list of strings* for the same field."""
    if isinstance(value, list):
        return str(value[0]) if value else ""
    return "" if value is None else str(value)


def archive_candidates(payload: Any, wanted: set[str], text: str) -> list[dict]:
    """The items worth opening, best first.

    Two things matter for a book (or any document) search and neither is
    "uploaded most recently": the item should *be* the thing that was asked for,
    and it should actually contain a file of the type that was asked for. The
    advancedsearch response already says both (title, format), so most of the
    work happens before a single item is opened.
    """
    rows = _rows(payload)
    words = [w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(w) > 2]

    def title_of(row: Any) -> str:
        return _one(row.get("title")) if isinstance(row, dict) else ""

    def has_wanted(row: Any) -> bool:
        if not wanted:
            return True
        formats = row.get("format") if isinstance(row, dict) else None
        if not formats:
            return True                      # the response did not say; open it and see
        if isinstance(formats, str):
            formats = [formats]
        hay = " ".join(str(f).lower() for f in formats)
        return any(ext in hay or (ext == "pdf" and "pdf" in hay) for ext in wanted)

    def score(row: Any) -> tuple:
        title = title_of(row).lower()
        matched = sum(1 for word in words if word in title)
        downloads = 0
        if isinstance(row, dict):
            try:
                downloads = int(row.get("downloads") or 0)
            except (TypeError, ValueError):
                downloads = 0
        return (matched, downloads)

    usable = [row for row in rows if isinstance(row, dict) and row.get("identifier") and has_wanted(row)]
    usable.sort(key=score, reverse=True)
    return usable[:5]


def archive_files(payload: Any, wanted: set[str], default_title: str = "") -> list[dict]:
    """The files inside one archive.org item, documents first.

    Returns plain dicts so this can be tested without a network or a client.
    """
    metadata = (payload or {}).get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    title = _one(metadata.get("title")) or default_title
    published = (_one(metadata.get("publicdate")) or _one(metadata.get("date"))
                 or _one((payload or {}).get("publicdate")))
    server = (payload or {}).get("server") or "archive.org"
    directory = (payload or {}).get("dir") or ""
    order = ["pdf", "epub", "djvu.txt", "txt"]
    files = []
    for entry in (payload or {}).get("files") or []:
        if not isinstance(entry, dict):
            continue
        name = _one(entry.get("name"))
        if not name or name.endswith("_meta.xml") or name.endswith("_files.xml"):
            continue
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if wanted and ext not in wanted:
            continue
        if not wanted and ext not in ("pdf", "epub"):
            continue
        files.append({
            "name": name, "ext": ext, "size": _one(entry.get("size")),
            "url": f"https://{server}{directory}/{quote(name)}",
            "title": title, "published": published,
            "rank": order.index(ext) if ext in order else len(order),
        })
    files.sort(key=lambda item: item["rank"])
    return files[:6]


class ArchiveFiles(Provider):
    id, name, family, layer = "archivefiles", "Internet Archive (files)", "filehost", "archive"
    description = "archive.org items resolved to the actual files inside them."
    lenses = ("files", "datasets", "all")
    homepage = "https://archive.org/"
    weight = 3.1

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        text = _text(ctx)
        wanted = set(_wanted(ctx))
        mediatypes = ("texts" if wanted & {"pdf", "epub", "doc", "docx", "djvu"}
                      else "software OR data OR texts OR audio OR movies")
        params: list[tuple[str, Any]] = [
            ("q", f"({text}) AND mediatype:({mediatypes})"),
            ("rows", "16"), ("page", "1"), ("output", "json"),
            # a title is answered by the item people actually read, not by
            # whatever was uploaded this morning
            ("sort[]", "downloads desc"),
            ("fl[]", "identifier"), ("fl[]", "title"), ("fl[]", "date"),
            ("fl[]", "publicdate"), ("fl[]", "format"), ("fl[]", "downloads"),
        ]
        try:
            resp = await ctx.client.get("https://archive.org/advancedsearch.php", params=params)
            if resp.status_code >= 400:
                return []
            candidates = archive_candidates(resp.json(), wanted, text)
        except Exception:
            return []
        if not candidates:
            return []

        async def one(item: dict) -> list[RawHit]:
            identifier = _one(item.get("identifier"))
            try:
                meta = await asyncio.wait_for(
                    ctx.client.get(f"https://archive.org/metadata/{identifier}"), timeout=3.0)
                if meta.status_code >= 400:
                    return []
                files = archive_files(meta.json(), wanted, _one(item.get("title")))
            except Exception:
                return []
            return [RawHit(
                url=file["url"],
                title=f"{file['title']} · {file['name']}",
                snippet=f"archive.org · {file['name']}" + (f" · {file['size']} bytes" if file["size"] else ""),
                kind="file", published=file["published"] or _one(item.get("publicdate")) or None,
                archive=True,
                tags=("filehost", "archive.org", f"ext-{file['ext']}"),
                meta={"host": "archive.org", "identifier": identifier,
                      "filename": file["name"], "size": file["size"]},
            ) for file in files]

        batches = await asyncio.gather(*(one(item) for item in candidates), return_exceptions=True)
        out: list[RawHit] = []
        for batch in batches:
            if isinstance(batch, list):
                out.extend(batch)
        return out


class SourceForgeFiles(Provider):
    id, name, family, layer = "sourceforge", "SourceForge", "filehost", "remote"
    description = "Project file releases — old software, drivers, datasets that never moved."
    lenses = ("files", "all")
    homepage = "https://sourceforge.net/"
    weight = 2.2

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        text = _text(ctx)
        try:
            resp = await ctx.client.get(
                f"https://sourceforge.net/directory/?q={quote(text)}",
                headers={"Accept": "text/html"})
        except Exception:
            return []
        if resp.status_code >= 400:
            return []
        out: list[RawHit] = []
        seen: set[str] = set()
        for match in re.finditer(r'href="(/projects/([^"/]+)/(?:files/)?[^"]*)"', resp.text or ""):
            url = "https://sourceforge.net" + match.group(1)
            if url in seen or not match.group(2):
                continue
            seen.add(url)
            out.append(RawHit(
                url=url, title=match.group(2).replace("-", " "),
                snippet="SourceForge files", kind="repo",
                tags=("filehost", "sourceforge"),
                meta={"host": "sourceforge.net"},
            ))
            if len(out) >= max(8, ctx.limit):
                break
        return out


FILE_HOSTS: tuple[type[Provider], ...] = (
    MediaFire, APKPure, APKMirror, Fdroid, ArchiveFiles, SourceForgeFiles,
)
