#!/usr/bin/env python3
"""读取内容文件夹，生成整个网站到 _site/。用法：python build.py

本机构建包含所有页面。GitHub 上构建，或者运行 python build.py --public 时，不包含写了 visibility: private 的页面。

约定：
- 根目录下每个第一级文件夹就是导航栏的一项（以 . 或 _ 开头的文件夹除外）。
- 每个栏目用列表视图还是卡片视图，以及其他配置项，都在 config.py 里。
- .md 转成网页；.html 原样保留并嵌入带导航栏的页面；其他文件（图片等）原样复制。
"""
import json
import os
import re
import shutil
import posixpath
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import date
from html import escape as e, unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, unquote

import yaml
from pygments.formatters import HtmlFormatter

from config import GISCUS, LABELS, LANGUAGE, RECENT_POSTS, SECTIONS, SITE_DESCRIPTION, SITE_TITLE, SUMMARY_LENGTH
import config  # noqa: E402
SITE_URL = getattr(config, "SITE_URL", "")  # 旧的 config.py 没有这一项时不出错
VISIBLE_TAGS = getattr(config, "VISIBLE_TAGS", 10)  # 列表页标签栏默认显示几个标签
from i18n import LANGUAGES

if LANGUAGE not in LANGUAGES:
    raise SystemExit(f"config.py：LANGUAGE 只能是 {' 或 '.join(LANGUAGES)}")
TEXT = LANGUAGES[LANGUAGE]

SECTION_DEFAULTS = {"view": "cards", "comments": False, "home": False}
VIEWS = ("list", "cards")
VISIBILITIES = ("public", "private")
# GitHub Actions 会自动设置这个环境变量，所以不用改 deploy.yml，也不会忘记加参数
PUBLIC_BUILD = "--public" in sys.argv[1:] or os.environ.get("GITHUB_ACTIONS") == "true"

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "_site"
THEME = ROOT / "_theme"
KATEX = "https://cdn.jsdelivr.net/npm/katex@0.16.11/dist"
ASSET_VERSION = int(time.time())  # 加在样式和脚本的地址后面，避免重新构建后浏览器还用旧缓存

ICON_FOLDER = (
    '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6.5A1.5 1.5 0 0 1 4.5 5h4.6l2 2.5h8.4'
    'A1.5 1.5 0 0 1 21 9v9.5a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 18.5z"/><path d="M3 10.5h18"/></svg>'
)
ICON_DOC = (
    '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 3h8l5 5v11.5a1.5 1.5 0 0 1-1.5 1.5h-11'
    'A1.5 1.5 0 0 1 5 19.5v-15A1.5 1.5 0 0 1 6.5 3z"/><path d="M14 3v5h5M8.5 13h7M8.5 17h7"/></svg>'
)


# ---------- 数据结构 ----------
@dataclass
class Doc:
    src: str  # 相对根目录的源文件路径
    url: str  # 相对根目录的输出路径
    kind: str  # "md" 或 "html"
    title: str
    date: str
    cover: str = ""  # 列表里的缩略图：相对根目录的路径，或者 https:// 开头的网址
    updated: str = ""  # 最后修改日期，比 date 晚时在文章里显示“更新于”
    tags: list = field(default_factory=list)
    summary: str = ""  # 列表上显示：手写的，没写就自动生成
    written_summary: str = ""  # 卡片上显示：只有手写的，这样卡片可以不带描述
    html: str = ""
    text: str = ""
    sort_name: str = ""
    crumbs: list = field(default_factory=list)  # 从栏目到所在文件夹的路径 [(显示名, 网址), ...]
    private: bool = False  # visibility: private，只有本机构建时才有这个页面


@dataclass
class Folder:
    rel: str
    name: str
    subfolders: list = field(default_factory=list)
    docs: list = field(default_factory=list)

    @property
    def url(self):
        return f"{self.rel}/index.html"

    @property
    def count(self):
        return len(self.docs) + sum(sub.count for sub in self.subfolders)

    @property
    def collapsed(self):
        """只装了一个 HTML 的文件夹（每个实验一个文件夹），卡片直接指向它，少点一次。"""
        return not self.subfolders and len(self.docs) == 1 and self.docs[0].kind == "html"

    def all_docs(self):
        yield from self.docs
        for sub in self.subfolders:
            yield from sub.all_docs()


# ---------- 工具函数 ----------
def ignored(path):
    return path.name.startswith((".", "_"))


def section_option(section, key):
    return SECTIONS.get(section, {}).get(key, SECTION_DEFAULTS[key])


def section_of(doc):
    return doc.src.split("/", 1)[0]


def check_sections(dirs):
    """写错的配置不报错的话，只会悄悄用默认设置，很难发现。"""
    names = {p.name for p in dirs}
    for name, options in SECTIONS.items():
        unknown = set(options) - set(SECTION_DEFAULTS)
        if unknown:
            raise SystemExit(f"config.py：栏目 {name} 有不认识的设置 {sorted(unknown)}，可以写的是 {sorted(SECTION_DEFAULTS)}")
        if section_option(name, "view") not in VIEWS:
            raise SystemExit(f"config.py：栏目 {name} 的 view 只能是 {' 或 '.join(VIEWS)}")
        if name not in names:
            print(f"提醒：config.py 里写了栏目 {name}，但根目录下没有这个文件夹")


def natural_key(name):
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", name.lower())]


def prettify(name):
    if name in LABELS:
        return LABELS[name]
    name = re.sub(r"^\d{4}-\d{2}-\d{2}[-_ ]*", "", name)
    name = re.sub(r"^\d+[-_. ]+", "", name)
    words = re.split(r"[-_ ]+", name)
    return " ".join(w[:1].upper() + w[1:] for w in words if w) or name


def link(root, url):
    return root + quote(url)


def read_text(path):
    return path.read_text(encoding="utf-8-sig", errors="replace")


_git_cache = None


def git_history():
    """一次性读出整个仓库的 git 记录，不再每篇文章单独调用 git（几百次调用要好几秒）。
    返回 (最后一次提交的日期, 第一次提交的日期, 有没提交改动的文件, 已提交过的文件)，路径都是相对根目录的 posix 路径。
    没装 git 或者不是 git 仓库时返回空的，日期就退回文件时间。"""
    global _git_cache
    if _git_cache is not None:
        return _git_cache

    def git(*args):
        result = subprocess.run(["git", "-c", "core.quotePath=false", *args], cwd=ROOT, capture_output=True,
                                text=True, encoding="utf-8")
        if result.returncode:
            raise OSError(result.stderr.strip())
        return result.stdout

    last, first, dirty, tracked = {}, {}, set(), set()
    try:
        # 从新到旧：每个文件第一次出现是最后一次修改，最后一次出现（只看新增）是创建
        day = None
        for line in git("log", "--no-renames", "--name-only", "--format=@@%as").splitlines():
            if line.startswith("@@"):
                day = line[2:]
            elif line:
                last.setdefault(line, day)
        for line in git("log", "--diff-filter=A", "--name-only", "--format=@@%as").splitlines():
            if line.startswith("@@"):
                day = line[2:]
            elif line:
                first[line] = day
        # -z：文件名不转义；改名的条目后面多一个旧路径
        entries = git("status", "--porcelain", "-z", "--untracked-files=all").split("\0")
        index = 0
        while index < len(entries):
            entry = entries[index]
            if entry:
                dirty.add(entry[3:])
                if entry[0] in "RC":
                    index += 1
            index += 1
        tracked = set(git("ls-files", "-z").split("\0")) - {""}
    except OSError:  # 没有安装 git，或者不在 git 仓库里
        last, first, dirty, tracked = {}, {}, set(), set()
    _git_cache = (last, first, dirty, tracked)
    return _git_cache


def doc_date(path, declared=None):
    """日期取 frontmatter 的 date，没写就取创建日期，之后再修改也不会变。

    不能看文件本身的时间：GitHub 构建时文件是刚下载的，时间都是构建当天。
    所以提交过的文件用第一次提交它的日期（改名、移动也会追溯回去），
    还没提交过的新文件才用文件的创建时间。
    """
    if declared:
        # 统一补零，否则 2026-11-5 这样的写法会排错顺序
        match = re.match(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", str(declared))
        return "{}-{:0>2}-{:0>2}".format(*match.groups()) if match else str(declared)[:10]

    _, first, _, tracked = git_history()
    rel = path.relative_to(ROOT).as_posix()
    if rel in first:
        return first[rel]
    if rel in tracked:  # 提交过但没有新增记录：是改名或移动过来的，要单独追溯（很少见）
        try:
            added = subprocess.run(["git", "log", "--diff-filter=A", "--follow", "--format=%as", "--", str(path)],
                                   cwd=ROOT, capture_output=True, text=True, encoding="utf-8").stdout.strip()
            if added:
                return added.splitlines()[-1]  # 从新到旧排列，最后一行是第一次提交
        except OSError:
            pass
    stat = path.stat()
    # Windows 上 st_ctime 就是创建时间；别的系统没有创建时间时，退回修改时间
    created = getattr(stat, "st_birthtime", None) or (stat.st_ctime if os.name == "nt" else stat.st_mtime)
    return date.fromtimestamp(created).isoformat()


def modified_date(path):
    """最后修改日期：提交后没再改过的文件取最后一次提交的日期，有没提交的改动时取文件修改时间。"""
    last, _, dirty, _ = git_history()
    rel = path.relative_to(ROOT).as_posix()
    if rel not in dirty and rel in last:
        return last[rel]
    return date.fromtimestamp(path.stat().st_mtime).isoformat()


class TextExtractor(HTMLParser):
    """提取网页中可见的文字，用于搜索。"""
    SKIP = {"head", "script", "style", "svg", "noscript"}
    BLOCK = {"address", "article", "aside", "blockquote", "br", "dd", "details", "div", "dl", "dt", "figcaption",
             "figure", "footer", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "li", "main", "nav", "ol", "p",
             "pre", "section", "summary", "table", "td", "th", "tr", "ul"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.depth += 1
        elif tag in self.BLOCK:  # 只在块级元素之间加空格，粗体等行内元素不打断文字
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.depth:
            self.depth -= 1
        elif tag in self.BLOCK:
            self.parts.append(" ")

    def handle_data(self, data):
        if not self.depth:
            self.parts.append(data)


def plain_text(html):
    parser = TextExtractor()
    parser.feed(html)
    return re.sub(r"\s+", " ", "".join(parser.parts)).strip()


# ---------- Markdown ----------
# 渲染规则和 Markdown 编辑器共用，在编辑器仓库的 md_render.py 里，这样编辑器预览和网站显示一致。
# 博客仓库里放一份副本，GitHub 上构建时用它。
def sync_renderer():
    """本机构建时，编辑器那份 md_render.py 改过了就先复制过来，提交博客时副本就跟着更新。
    config.py 的 RENDERER_SOURCE 是编辑器那份的位置；找不到时（比如 GitHub 上）直接用副本。"""
    source = getattr(config, "RENDERER_SOURCE", "")
    if not source:
        return
    source = (ROOT / source).resolve()
    target = ROOT / "md_render.py"
    if source.is_file() and (not target.is_file() or source.read_bytes() != target.read_bytes()):
        shutil.copyfile(source, target)
        print(f"提醒：已从 {source} 更新 md_render.py，记得和博客一起提交")


sync_renderer()
from md_render import make_markdown  # noqa: E402  同步之后再导入，用的才是最新的

MD = make_markdown()


def parse_frontmatter(source, path):
    match = re.match(r"---[ \t]*\n(.*?)\n---[ \t]*(?:\n|$)", source, re.S)
    if not match:
        return {}, source
    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as err:
        raise SystemExit(f"{path}: 文件开头的 frontmatter 格式有误：\n{err}")
    return meta, source[match.end():]


def external_url(url):
    return re.match(r"(?:https?:)?//|data:image/", url, re.I)


def find_cover(meta, html, rel):
    """列表缩略图：frontmatter 的 cover，没写就取正文第一张图；cover: none 表示不要。"""
    declared = meta.get("cover")
    if declared is False or (declared is not None and str(declared).strip().lower() in ("none", "false", "no")):
        return ""
    if declared:
        src = str(declared).strip()
    else:
        first = re.search(r"""<img\b[^>]*?\bsrc\s*=\s*["']([^"']+)["']""", html, re.I)
        if not first:
            return ""
        src = unescape(first.group(1))
    if external_url(src):
        return src
    path = unquote(re.split(r"[#?]", src, maxsplit=1)[0])
    cover = posixpath.normpath(path.lstrip("/") if path.startswith("/") else posixpath.join(posixpath.dirname(rel), path))
    if not (ROOT / cover).is_file():
        print(f"提醒：{rel} 的缩略图 {src} 找不到，列表里不显示图片")
        return ""
    return cover


def parse_tags(value):
    if not value:
        return []
    if isinstance(value, str):
        value = re.split(r"[,，]", value)
    return [str(t).strip() for t in value if str(t).strip()]


def truncate(text):
    if len(text) <= SUMMARY_LENGTH:
        return text
    cut = text[:SUMMARY_LENGTH]
    if re.match(r"[A-Za-z0-9]{2}", text[SUMMARY_LENGTH - 1:]):  # 正好切在英文单词中间，退回到单词开头
        cut = re.sub(r"[A-Za-z0-9]+$", "", cut) or cut
    return cut.rstrip() + "..."


def excerpt(html):
    """摘要默认取第一段（跳过只有公式的段落），太长时截断。"""
    for paragraph in re.findall(r"<p>(.*?)</p>", html, re.S):
        text = plain_text(re.sub(r'<span class="math[^"]*">.*?</span>', "", paragraph, flags=re.S))
        if text:
            return truncate(text)
    return ""


def read_private(meta, rel):
    """写错时停止构建。如果当成默认的公开，一个拼写错误就会把不想发布的页面发布出去。"""
    value = str(meta.get("visibility", "public")).strip().lower()
    if value not in VISIBILITIES:
        raise SystemExit(f"{rel}: visibility 只能是 {' 或 '.join(VISIBILITIES)}，现在写的是 {meta['visibility']!r}")
    return value == "private"


def load_markdown(path, rel):
    meta, body = parse_frontmatter(read_text(path), rel)
    private = read_private(meta, rel)
    html = MD.render(body)
    heading = re.search(r"<h1\b[^>]*>(.*?)</h1>", html, re.S)
    if heading and not html[:heading.start()].strip():  # 页面已经显示标题，开头的一级标题不再重复
        html = html[heading.end():]
    # 笔记之间的 [链接](other.md) 指向生成后的网页
    html = re.sub(r'href="(?![a-z]+:|#)([^"]+?)\.(?:md|markdown)(#[^"]*)?"',
                  lambda m: f'href="{m.group(1)}.html{m.group(2) or ""}"', html)
    written_summary = str(meta.get("summary") or "")
    return Doc(
        src=rel,
        url=str(Path(rel).with_suffix(".html").as_posix()),
        kind="md",
        title=str(meta.get("title") or (heading and plain_text(heading.group(1))) or prettify(path.stem)),
        date=doc_date(path, meta.get("date")),
        updated=modified_date(path),
        cover=find_cover(meta, html, rel),
        tags=parse_tags(meta.get("tags")),
        summary=written_summary or excerpt(html),
        written_summary=written_summary,
        html=html,
        text=plain_text(html),
        sort_name=path.name,
        private=private,
    )


def meta_description(source):
    """HTML 文件没有 frontmatter，手写的摘要取 <meta name="description" content="...">。"""
    for tag in re.findall(r"<meta\b[^>]*>", source, re.I):
        if re.search(r"""\bname\s*=\s*["']?description\b""", tag, re.I):
            content = re.search(r"""\bcontent\s*=\s*(["'])(.*?)\1""", tag, re.I | re.S)
            return unescape(content.group(2)).strip() if content else ""
    return ""


def load_html(path, rel):
    source = read_text(path)
    title = re.search(r"<title[^>]*>(.*?)</title>", source, re.S | re.I)
    text = plain_text(source)
    written_summary = meta_description(source)
    return Doc(
        src=rel,
        url=str(Path(rel).with_name(path.stem + ".view.html").as_posix()),
        kind="html",
        title=re.sub(r"\s+", " ", title.group(1)).strip() if title and title.group(1).strip() else prettify(path.stem),
        date=doc_date(path),
        summary=written_summary or truncate(text),
        written_summary=written_summary,
        text=text,
        sort_name=path.name,
    )


# ---------- 扫描内容 ----------
def scan(path):
    rel = path.relative_to(ROOT).as_posix()
    folder = Folder(rel=rel, name=prettify(path.name))
    for child in sorted(path.iterdir(), key=lambda p: natural_key(p.name)):
        if ignored(child):
            continue
        child_rel = child.relative_to(ROOT).as_posix()
        if child.is_dir():
            if child.name.endswith("_files"):  # 导出 HTML 时附带的资源文件夹
                continue
            sub = scan(child)
            has_files = any(p.is_file() for p in child.rglob("*"))
            if sub.count or not has_files:  # 只放图片等资源的文件夹不显示
                folder.subfolders.append(sub)
        elif child.suffix.lower() in (".md", ".markdown"):
            folder.docs.append(load_markdown(child, child_rel))
        elif child.suffix.lower() in (".html", ".htm"):
            folder.docs.append(load_html(child, child_rel))
    return folder


def remove_private(folder):
    """把私有页面从文件夹里去掉，返回去掉的页面。只装着私有页面的文件夹也不显示。"""
    removed = [doc for doc in folder.docs if doc.private]
    folder.docs = [doc for doc in folder.docs if not doc.private]
    kept = []
    for sub in folder.subfolders:
        had_docs = sub.count > 0
        removed += remove_private(sub)
        if sub.count or not had_docs:
            kept.append(sub)
    folder.subfolders = kept
    return removed


def local_references(doc):
    """页面里用到的本地文件（图片、链接），是相对根目录的路径。"""
    source = doc.html if doc.kind == "md" else read_text(ROOT / doc.src)
    references = {doc.src} if doc.kind == "html" else set()  # HTML 页面要靠原文件显示，私有页面链接到它时也要留着
    for target in re.findall(r"""\b(?:src|href)\s*=\s*["']([^"']+)["']""", source, re.I):
        if re.match(r"[a-z][a-z0-9+.-]*:|#|/", target, re.I):
            continue
        path = unquote(re.split(r"[#?]", target, maxsplit=1)[0])
        if path:
            references.add(posixpath.normpath(posixpath.join(posixpath.dirname(doc.src), path)))
    if doc.cover and not external_url(doc.cover):
        references.add(doc.cover)  # frontmatter 里指定的缩略图不在正文里，也要算上
    return references


def copy_files(section, skip=frozenset()):
    """除 Markdown 外的文件原样复制（实验 HTML、图片等），保持相对路径不变。skip 里的文件不复制。"""
    for dirpath, dirnames, filenames in os.walk(ROOT / section):
        # 修改点 1：只过滤 . 开头的文件夹，允许 os.walk 进入 _ 开头的文件夹（如 _images）
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for filename in filenames:
            src = Path(dirpath) / filename
            
            # ======== 修改这里 ========
            # 修改前：if ignored(src) or src.suffix.lower() in (".md", ".markdown"):
            # 修改后：不再使用 ignored(src) 拦截，直接放行 _ 开头的文件，只拦截 . 开头的隐藏文件和 md 文件
            if src.name.startswith(".") or src.suffix.lower() in (".md", ".markdown"):
                continue
            # ==========================
            
            if src.relative_to(ROOT).as_posix() in skip:
                continue

            dst = SITE / src.relative_to(ROOT)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)


# ---------- 页面模板 ----------
def absolute_url(path):
    """分享卡片里的地址必须是完整网址。path 是相对根目录的路径，也可以本来就是网址。"""
    if external_url(path):
        return "https:" + path if path.startswith("//") else path
    return f"{SITE_URL.rstrip('/')}/{quote(path)}" if SITE_URL else ""


def share_meta(title, url, doc=None):
    """分享到社交平台时显示的标题、摘要和图片（Open Graph 和 Twitter 卡片）。"""
    description = (doc.summary if doc else "") or SITE_DESCRIPTION
    tags = [("name", "description", description), ("property", "og:site_name", SITE_TITLE),
            ("property", "og:title", title), ("property", "og:description", description),
            ("property", "og:type", "article" if doc else "website")]
    page = absolute_url(url)
    if page:
        tags.append(("property", "og:url", page))
    # 大多数平台不支持 SVG 当分享图
    image = absolute_url(doc.cover) if doc and doc.cover and not doc.cover.lower().endswith(".svg") else ""
    if image:
        tags += [("property", "og:image", image), ("property", "og:image:alt", title)]
    tags.append(("name", "twitter:card", "summary_large_image" if image else "summary"))
    if doc:
        tags.append(("property", "article:published_time", doc.date))
        if doc.updated > doc.date:
            tags.append(("property", "article:modified_time", doc.updated))
        tags += [("property", "article:tag", tag) for tag in doc.tags]
    head = "\n".join(f'<meta {kind}="{key}" content="{e(value)}">' for kind, key, value in tags)
    return head + (f'\n<link rel="canonical" href="{e(page)}">' if page else "")


def emit(url, title, body, sections, active=None, math=False, body_class="", doc=None):
    root = "../" * url.count("/")
    nav = "".join(
        f'<a href="{link(root, s.url)}"{" class=active aria-current=page" if s.rel == active else ""}>{e(s.name)}</a>'
        for s in sections
    )
    katex = (
        f'<link rel="stylesheet" href="{KATEX}/katex.min.css">'
        f'<script defer src="{KATEX}/katex.min.js"></script>'
        f'<script defer src="{KATEX}/contrib/auto-render.min.js"></script>'
    ) if math else ""
    page_title = f"{title} · {SITE_TITLE}" if title != SITE_TITLE else title
    html = f"""<!DOCTYPE html>
<html lang="{e(TEXT['html_lang'])}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(page_title)}</title>
{share_meta(title, url, doc)}
<link rel="stylesheet" href="{root}_assets/style.css?v={ASSET_VERSION}">
{katex}
<script defer src="{root}_assets/site.js?v={ASSET_VERSION}" data-root="{root}"></script>
</head>
<body class="{body_class}">
<header class="site-header">
  <div class="header-inner">
    <a class="brand" href="{root}index.html">{e(SITE_TITLE)}</a>
    <nav class="nav" aria-label="{e(TEXT['main_nav'])}">{nav}</nav>
    <div class="search" role="search">
      <input id="search-input" type="search" placeholder="{e(TEXT['search'])}" aria-label="{e(TEXT['search'])}" autocomplete="off">
      <div id="search-results" class="search-results" hidden></div>
    </div>
  </div>
</header>
{body}
</body>
</html>
"""
    out = SITE / url
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")


def crumbs_html(root, crumbs, current):
    parts = [f'<a href="{link(root, url)}">{e(name)}</a>' for name, url in crumbs]
    parts.append(f'<span aria-current="page">{e(current)}</span>')
    separator = "<span class=sep>/</span>"
    return f'<nav class="crumbs" aria-label="{e(TEXT["breadcrumb"])}">{separator.join(parts)}</nav>'


def tag_links(root, doc):
    """列表视图的栏目可以按标签筛选，标签链接到栏目页；卡片视图的栏目没有筛选，只显示文字。"""
    section = section_of(doc)
    if section_option(section, "view") != "list":
        return "".join(f'<span class="tag">{e(t)}</span>' for t in doc.tags)
    return "".join(f'<a class="tag" href="{root}{quote(section)}/index.html#tag={quote(t)}">{e(t)}</a>' for t in doc.tags)


def post_list(root, posts, depth):
    """depth 是当前页面所在的层数，文章的路径只显示比它更深的部分。"""
    items = []
    for post in posts:
        tags = f'<div class="tags">{tag_links(root, post)}</div>' if post.tags else ""
        summary = f"<p>{e(post.summary)}</p>" if post.summary else ""
        path = " / ".join(f'<a href="{link(root, url)}">{e(name)}</a>' for name, url in post.crumbs[depth:])
        path = f'<span class="post-path">{path}</span>' if path else ""
        cover = ""
        if post.cover:
            src = post.cover if external_url(post.cover) else link(root, post.cover)
            # 标题已经是链接，图片链接对读屏和键盘是重复的，所以不进 Tab 顺序
            cover = (f'<a class="post-cover" href="{link(root, post.url)}" tabindex="-1" aria-hidden="true">'
                     f'<img src="{e(src)}" alt="" loading="lazy" decoding="async"></a>')
        items.append(
            f'<article class="post{" has-cover" if cover else ""}" data-tags="{e(json.dumps(post.tags, ensure_ascii=False))}">'
            f'<div class="post-body"><div class="post-meta"><time datetime="{e(post.date)}">{e(post.date)}</time>{path}</div>'
            f'<h2><a href="{link(root, post.url)}">{e(post.title)}</a></h2>{summary}{tags}</div>{cover}</article>'
        )
    return f'<div class="post-list">{"".join(items)}</div>'


def folded_ranges(html):
    """默认折叠的 <details> 覆盖的范围。写了 open 的默认展开，不算；它在折叠的 <details> 里面时仍然看不到。
    没写结束标签时一直到文末。"""
    ranges = []
    stack = []  # 每一层 <details> 是不是默认折叠
    start = 0
    for tag in re.finditer(r"<(/?)details\b([^>]*)>", html, re.I):
        if not tag.group(1):
            folded = not re.search(r"\bopen\b", tag.group(2), re.I)
            if folded and not any(stack):
                start = tag.start()
            stack.append(folded)
        elif stack:
            if stack.pop() and not any(stack):
                ranges.append((start, tag.end()))
    if any(stack):
        ranges.append((start, len(html)))
    return ranges


def toc_html(html):
    """用正文的一到三级标题生成目录；标题少于 2 个时不显示。宽屏和窄屏各用一份，由 CSS 切换。
    折叠在 <details> 里的标题平时看不到，点了目录也跳不过去，所以不放进目录。"""
    folded = folded_ranges(html)
    headings = [match.groups() for match in re.finditer(r'<h([1-3]) id="([^"]+)">(.*?)</h\1>', html, re.S)
                if not any(start <= match.start() < end for start, end in folded)]
    if len(headings) < 2:
        return ""
    top = min(int(level) for level, _, _ in headings)
    items = []
    for level, anchor, inner in headings:
        inner = re.sub(r"<sup\b.*?</sup>|</?a\b[^>]*>", "", inner, flags=re.S)  # 去掉脚注和嵌套链接
        items.append(f'<li class="toc-l{int(level) - top}"><a href="#{anchor}">{inner}</a></li>')
    links = f'<ul>{"".join(items)}</ul>'
    title = e(TEXT["toc"])
    return (
        f'<aside class="toc toc-side" aria-label="{title}"><div class="toc-sticky"><div class="toc-title">{title}</div>{links}</div></aside>'
        f'<details class="toc toc-inline"><summary>{title}</summary>{links}</details>'
    )


def comments_html():
    if not (GISCUS["repo_id"] and GISCUS["category_id"]):
        return ""
    return (
        f'<section class="comments" aria-label="{e(TEXT["comments"])}"><h2>{e(TEXT["comments"])}</h2>'
        f'<script src="https://giscus.app/client.js" data-repo="{e(GISCUS["repo"])}" data-repo-id="{e(GISCUS["repo_id"])}" '
        f'data-category="{e(GISCUS["category"])}" data-category-id="{e(GISCUS["category_id"])}" '
        'data-mapping="pathname" data-strict="1" data-reactions-enabled="1" data-emit-metadata="0" '
        f'data-input-position="bottom" data-theme="light" data-lang="{e(GISCUS["lang"])}" '
        'crossorigin="anonymous" async></script></section>'
    )


def render_doc(doc, crumbs, active, sections):
    root = "../" * doc.url.count("/")
    trail = crumbs_html(root, crumbs, doc.title)
    if doc.kind == "html":
        raw = quote(Path(doc.src).name)
        body = (
            f'<div class="frame-bar">{trail}<a class="frame-open" href="{raw}" target="_blank" rel="noopener">{e(TEXT["open_new_tab"])}</a></div>'
            f'<iframe class="frame" src="{raw}" title="{e(doc.title)}"></iframe>'
        )
        emit(doc.url, doc.title, body, sections, active, body_class="frame-page")
        return
    tags = f'<div class="tags">{tag_links(root, doc)}</div>' if doc.tags else ""
    updated = ""
    if doc.updated > doc.date:  # 都是 YYYY-MM-DD，可以直接比较
        stamp = f'<time datetime="{e(doc.updated)}">{e(doc.updated)}</time>'
        updated = f'<span class="doc-updated">{TEXT["updated"].format(date=stamp)}</span>'
    comments = comments_html() if section_option(section_of(doc), "comments") else ""
    body = (
        f'<main class="container">{trail}<article class="doc"><header class="doc-head"><h1>{e(doc.title)}</h1>'
        f'<div class="doc-meta"><time datetime="{e(doc.date)}">{e(doc.date)}</time>{updated}{tags}</div></header>'
        f'{toc_html(doc.html)}<div class="prose">{doc.html}</div></article>{comments}</main>'
    )
    emit(doc.url, doc.title, body, sections, active, math='class="math' in doc.html, doc=doc)


def card(root, url, icon, title, meta, summary=""):
    summary = f'<span class="card-summary">{e(summary)}</span>' if summary else ""
    return (
        f'<a class="card" href="{link(root, url)}">{icon}'
        f'<span class="card-body"><span class="card-title">{e(title)}</span>{summary}'
        f'<span class="card-meta">{e(meta)}</span></span></a>'
    )


def publish_doc(doc, crumbs, active, sections, index):
    doc.crumbs = crumbs
    render_doc(doc, crumbs, active, sections)
    index.append({"t": doc.title, "u": doc.url, "p": " / ".join(n for n, _ in crumbs), "g": doc.tags,
                  "x": f"{doc.written_summary} {doc.text}".strip(), "k": "doc"})


def render_cards(folder, crumbs, active, sections, index):
    """卡片视图：子文件夹和文件都显示成卡片，一层层点进去。"""
    root = "../" * folder.url.count("/")
    child_crumbs = crumbs + [(folder.name, folder.url)]
    folders = []  # (排序名, 卡片 HTML)
    docs = []
    for sub in folder.subfolders:
        if sub.collapsed:
            doc = sub.docs[0]
            docs.append((Path(sub.rel).name, card(root, doc.url, ICON_DOC, doc.title, doc.date, doc.written_summary)))
            publish_doc(doc, child_crumbs, active, sections, index)
        else:
            count = TEXT["items"][0 if sub.count == 1 else 1].format(n=sub.count)
            folders.append((Path(sub.rel).name, card(root, sub.url, ICON_FOLDER, sub.name, count)))
            render_cards(sub, child_crumbs, active, sections, index)
    for doc in folder.docs:
        docs.append((doc.sort_name, card(root, doc.url, ICON_DOC, doc.title, doc.date, doc.written_summary)))
        publish_doc(doc, child_crumbs, active, sections, index)
    cards = [c for _, c in sorted(folders, key=lambda x: natural_key(x[0]))]
    cards += [c for _, c in sorted(docs, key=lambda x: natural_key(x[0]))]
    grid = f'<div class="card-grid">{"".join(cards)}</div>' if cards else f'<p class="empty">{e(TEXT["empty_folder"])}</p>'
    trail = crumbs_html(root, crumbs, folder.name) if crumbs else ""
    emit(folder.url, folder.name, f'<main class="container">{trail}<h1 class="page-title">{e(folder.name)}</h1>{grid}</main>',
         sections, active)
    index.append({"t": folder.name, "u": folder.url, "p": " / ".join(n for n, _ in crumbs), "g": [], "x": "", "k": "folder"})


def newest_first(docs):
    return sorted(docs, key=lambda d: (d.date, d.title), reverse=True)


def category_links(root, categories):
    links = "".join(
        f'<a class="category" href="{link(root, url)}">{ICON_FOLDER}{e(name)}<span>{count}</span></a>'
        for url, name, count in categories
    )
    return f'<nav class="categories" aria-label="{e(TEXT["categories"])}">{links}</nav>' if links else ""


def render_list(folder, crumbs, active, sections, index):
    """列表视图：每个文件夹一页，列出它里面所有层的文章，上方是子文件夹的入口。"""
    child_crumbs = crumbs + [(folder.name, folder.url)]
    subfolders = [sub for sub in folder.subfolders if not sub.collapsed]
    direct = folder.docs + [sub.docs[0] for sub in folder.subfolders if sub.collapsed]
    for sub in subfolders:  # 先生成子文件夹，这样下面列文章时路径已经有了
        render_list(sub, child_crumbs, active, sections, index)
    for doc in direct:
        publish_doc(doc, child_crumbs, active, sections, index)

    categories = [(sub.url, sub.name, sub.count) for sub in subfolders]
    if subfolders and direct:  # 没有分类的文章放进“其他”，这样也能单独看到它们
        other_url = f"{folder.rel}/_other/index.html"
        categories.append((other_url, TEXT["other"], len(direct)))
        render_list_page(other_url, TEXT["other"], child_crumbs, direct, [], active, sections)
    render_list_page(folder.url, folder.name, crumbs, folder.all_docs(), categories, active, sections)
    index.append({"t": folder.name, "u": folder.url, "p": " / ".join(n for n, _ in crumbs), "g": [], "x": "", "k": "folder"})


def render_list_page(url, name, crumbs, docs, categories, active, sections):
    root = "../" * url.count("/")
    posts = newest_first(docs)

    counts = {}
    for post in posts:
        for tag in post.tags:
            counts[tag] = counts.get(tag, 0) + 1
    # 标签按文章数从多到少排，只显示前 VISIBLE_TAGS 个，其余点“+N”展开；选中的标签总会显示
    ranked = sorted(counts.items(), key=lambda x: (-x[1], x[0]))
    chips = "".join(
        f'<a class="chip{" chip-extra" if i >= VISIBLE_TAGS else ""}" href="#tag={quote(tag)}" data-tag="{e(tag)}">{e(tag)}<span>{n}</span></a>'
        for i, (tag, n) in enumerate(ranked)
    )
    if len(ranked) > VISIBLE_TAGS:
        more = TEXT["more_tags"].format(n=len(ranked) - VISIBLE_TAGS)
        chips += (f'<button type="button" class="chip chip-more" aria-expanded="false" '
                  f'data-more="{e(more)}" data-less="{e(TEXT["fewer_tags"])}">{e(more)}</button>')
    if chips:
        chips = f'<a class="chip" href="#" data-tag="">{e(TEXT["all"])}<span>{len(posts)}</span></a>{chips}'

    # 起止日期和日历，日历由 site.js 根据页面上的文章日期生成
    date_range = (
        '<div class="date-range" id="date-range">'
        f'<input id="date-from" type="text" placeholder="{e(TEXT["date_from"])}" aria-label="{e(TEXT["date_from"])}" autocomplete="off">'
        '<span class="date-sep">–</span>'
        f'<input id="date-to" type="text" placeholder="{e(TEXT["date_to"])}" aria-label="{e(TEXT["date_to"])}" autocomplete="off">'
        f'<button type="button" id="date-clear" aria-label="{e(TEXT["date_clear"])}" hidden>×</button>'
        '<div class="calendar" id="date-calendar" hidden></div></div>'
    )
    filters = f'<div class="filters">{chips}{date_range}</div>' if posts else ""
    if posts:
        content = post_list(root, posts, len(crumbs) + 1) + f'<p id="no-match" class="empty" hidden>{e(TEXT["no_match"])}</p>'
    else:
        content = f'<p class="empty">{e(TEXT["no_posts"])}</p>'
    trail = crumbs_html(root, crumbs, name) if crumbs else ""
    emit(url, name,
         f'<main class="container">{trail}<h1 class="page-title">{e(name)}</h1>'
         f'{category_links(root, categories)}{filters}{content}</main>',
         sections, active)


def render_home(sections):
    intro = f'<div class="intro"><h1>{e(SITE_TITLE)}</h1><p>{e(SITE_DESCRIPTION)}</p></div>'
    home_sections = [s for s in sections if section_option(s.rel, "home")]
    recent = ""
    if home_sections:
        posts = newest_first(doc for s in home_sections for doc in s.all_docs())
        items = post_list("", posts[:RECENT_POSTS], 1) if posts else f'<p class="empty">{e(TEXT["no_posts"])}</p>'
        more = "".join(f'<p class="more"><a href="{link("", s.url)}">{e(TEXT["all_in"].format(name=s.name))}</a></p>'
                       for s in home_sections) if len(posts) > RECENT_POSTS else ""
        recent = f'<h2 class="section-title">{e(TEXT["recent"])}</h2>{items}{more}'
    emit("index.html", SITE_TITLE, f'<main class="container">{intro}{recent}</main>', sections)


# ---------- 入口 ----------
def build():
    # 只清空内容、不删目录本身：Windows 上如果有终端或预览服务停在 _site 里，删目录会失败
    SITE.mkdir(exist_ok=True)
    for child in SITE.iterdir():
        shutil.rmtree(child) if child.is_dir() else child.unlink()
    (SITE / "_assets").mkdir()
    text = json.dumps(TEXT, ensure_ascii=False)
    (SITE / "_assets" / "site.js").write_text(f"window.SITE_TEXT={text};\n" + read_text(THEME / "site.js"), encoding="utf-8")
    code_css = HtmlFormatter(style="default").get_style_defs("pre")
    (SITE / "_assets" / "style.css").write_text(read_text(THEME / "style.css") + "\n" + code_css, encoding="utf-8")

    dirs = [p for p in ROOT.iterdir() if p.is_dir() and not ignored(p)]
    check_sections(dirs)
    order = list(SECTIONS)  # 配置里写的栏目按写的顺序排在前面，其余的按文件夹名排在后面
    dirs.sort(key=lambda p: (order.index(p.name) if p.name in order else len(order), natural_key(p.name)))
    sections = [scan(p) for p in dirs]
    private_docs = []
    private_files = set()
    if PUBLIC_BUILD:
        private_docs = [doc for section in sections for doc in remove_private(section)]
        public_references = set().union(*(local_references(doc) for section in sections for doc in section.all_docs()))
        # 只有私有页面用到的图片也不能发布。公开页面也用到的要留着
        private_files = set().union(*(local_references(doc) for doc in private_docs)) - public_references
        for url in sorted(public_references & {doc.url for doc in private_docs}):
            print(f"提醒：有公开的页面链接到了私有页面 {url}，发布后这个链接会打不开")
    else:
        for doc in (doc for section in sections for doc in section.all_docs() if doc.private):
            print(f"私有页面，不会发布到 GitHub：{doc.src}")
    index = []
    for section in sections:
        copy_files(section.rel, private_files)
        render = render_list if section_option(section.rel, "view") == "list" else render_cards
        render(section, [], section.rel, sections, index)
    render_home(sections)

    data = json.dumps(index, ensure_ascii=False, separators=(",", ":"))
    (SITE / "_assets" / "search-index.js").write_text(f"window.SEARCH_INDEX={data};", encoding="utf-8")
    pages = sum(s.count for s in sections)
    skipped = f"，跳过 {len(private_docs)} 篇私有页面" if PUBLIC_BUILD else ""
    print(f"完成：{len(sections)} 个栏目，{pages} 篇内容{skipped}，输出到 {SITE}")


if __name__ == "__main__":
    build()
