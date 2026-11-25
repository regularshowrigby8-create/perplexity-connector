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


class ArchiveFiles(Provider):
    id, name, family, layer = "archivefiles", "Internet Archive (files)", "filehost", "archive"
    description = "archive.org items resolved to the actual files inside them."
    lenses = ("files", "datasets", "all")
    homepage = "https://archive.org/"
    weight = 3.1

    async def hunt(self, ctx: HuntContext) -> list[RawHit]:
        text = _text(ctx)
        wanted = set(_wanted(ctx))
        query = f"({text}) AND mediatype:(software OR data OR texts OR audio OR movies)"
        params: list[tuple[str, Any]] = [
            ("q", query), ("rows", "18"), ("page", "1"), ("output", "json"),
            ("sort[]", "publicdate desc"),
            ("fl[]", "identifier"),
        ]
        try:
            resp = await ctx.client.get("https://archive.org/advancedsearch.php", params=params)
            if resp.status_code >= 400:
                return []
            docs = _rows(resp.json())
        except Exception:
            return []
        identifiers = [str(row.get("identifier") or "") for row in docs if row.get("identifier")][:8]
        if not identifiers:
            return []

        async def files_for(identifier: str) -> list[RawHit]:
            try:
                meta = await ctx.client.get(f"https://archive.org/metadata/{identifier}")
                if meta.status_code >= 400:
                    return []
                payload = meta.json() or {}
            except Exception:
                return []
            server = payload.get("server") or "archive.org"
            directory = payload.get("dir") or f"/{identifier}"
            made: list[RawHit] = []
            for entry in payload.get("files") or []:
                name = str(entry.get("name") or "")
                ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
                if not ext or (wanted and ext not in wanted):
                    continue
                url = f"https://{server}{directory}/{quote(name)}"
                made.append(RawHit(
                    url=url, title=str(payload.get("metadata", {}).get("title") or name) + f" · {name}",
                    snippet=f"archive.org · {name} · {entry.get('size') or ''}".strip(" ·"),
                    kind="file", published=str(payload.get("metadata", {}).get("publicdate") or ""),
                    tags=("filehost", "archive.org", f"ext-{ext}"),
                    meta={"host": "archive.org", "identifier": identifier, "filename": name,
                          "size": entry.get("size")},
                ))
                if len(made) >= 6:
                    break
            return made

        batches = await asyncio.gather(*(files_for(i) for i in identifiers),
                                       return_exceptions=True)
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
