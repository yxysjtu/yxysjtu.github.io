#!/usr/bin/env python3
"""读取内容文件夹，生成整个网站到 _site/。用法：python build.py

约定：
- 根目录下每个第一级文件夹就是导航栏的一项（以 . 或 _ 开头的文件夹除外）。
- 每个栏目用列表视图还是卡片视图，以及其他配置项，都在 config.py 里。
- .md 转成网页；.html 原样保留并嵌入带导航栏的页面；其他文件（图片等）原样复制。
"""
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from datetime import date
from html import escape as e, unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote

import yaml
from markdown_it import MarkdownIt
from mdit_py_plugins.anchors import anchors_plugin
from mdit_py_plugins.dollarmath import dollarmath_plugin
from mdit_py_plugins.footnote import footnote_plugin
from mdit_py_plugins.tasklists import tasklists_plugin
from pygments import highlight as pygments_highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

from config import GISCUS, LABELS, LANGUAGE, RECENT_POSTS, SECTIONS, SITE_DESCRIPTION, SITE_TITLE, SUMMARY_LENGTH
from i18n import LANGUAGES

if LANGUAGE not in LANGUAGES:
    raise SystemExit(f"config.py：LANGUAGE 只能是 {' 或 '.join(LANGUAGES)}")
TEXT = LANGUAGES[LANGUAGE]

SECTION_DEFAULTS = {"view": "cards", "comments": False, "home": False}
VIEWS = ("list", "cards")

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
    tags: list = field(default_factory=list)
    summary: str = ""  # 列表上显示：手写的，没写就自动生成
    written_summary: str = ""  # 卡片上显示：只有手写的，这样卡片可以不带描述
    html: str = ""
    text: str = ""
    sort_name: str = ""
    crumbs: list = field(default_factory=list)  # 从栏目到所在文件夹的路径 [(显示名, 网址), ...]


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


def doc_date(path, declared=None):
    """日期取 frontmatter 的 date，没写就取最后修改日期。

    不能只看文件修改时间：GitHub 构建时文件是刚下载的，修改时间都是构建当天。
    所以已提交且没再改动的文件用最后一次提交的日期，其余情况才用文件修改时间。
    """
    if declared:
        # 统一补零，否则 2026-11-5 这样的写法会排错顺序
        match = re.match(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", str(declared))
        return "{}-{:0>2}-{:0>2}".format(*match.groups()) if match else str(declared)[:10]

    def git(*args):
        return subprocess.run(["git", *args, "--", str(path)], cwd=ROOT, capture_output=True,
                              text=True, encoding="utf-8").stdout.strip()

    try:
        if not git("status", "--porcelain"):
            committed = git("log", "-1", "--format=%as")
            if committed:
                return committed
    except OSError:  # 没有安装 git
        pass
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
def highlight_code(code, lang, _attrs):
    try:
        lexer = get_lexer_by_name(lang)
    except ClassNotFound:
        return ""  # 交给 markdown-it 按普通代码块输出
    return pygments_highlight(code, lexer, HtmlFormatter(nowrap=True))


def render_math(content, opts):
    if opts.get("display_mode"):
        return f'<span class="math math-display">\\[{e(content)}\\]</span>'
    return f'<span class="math">\\({e(content)}\\)</span>'


def strip_quote_markers(state):
    """公式插件不会去掉引用里每行开头的 >，这里按引用层数去掉。"""
    depth = 0
    for token in state.tokens:
        if token.type == "blockquote_open":
            depth += 1
        elif token.type == "blockquote_close":
            depth -= 1
        elif token.type == "math_block" and depth:
            token.content = re.sub(rf"^[ \t]*(?:>[ \t]?){{1,{depth}}}", "", token.content, flags=re.M)


MD = (
    MarkdownIt("commonmark", {"html": True, "highlight": highlight_code})
    .enable(["table", "strikethrough"])
    .use(dollarmath_plugin, allow_digits=False, double_inline=True, renderer=render_math)
    .use(footnote_plugin)
    .use(tasklists_plugin)
    .use(anchors_plugin, max_level=4)
)
MD.core.ruler.push("strip_quote_markers", strip_quote_markers)


def parse_frontmatter(source, path):
    match = re.match(r"---[ \t]*\n(.*?)\n---[ \t]*(?:\n|$)", source, re.S)
    if not match:
        return {}, source
    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as err:
        raise SystemExit(f"{path}: 文件开头的 frontmatter 格式有误：\n{err}")
    return meta, source[match.end():]


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


def load_markdown(path, rel):
    meta, body = parse_frontmatter(read_text(path), rel)
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
        tags=parse_tags(meta.get("tags")),
        summary=written_summary or excerpt(html),
        written_summary=written_summary,
        html=html,
        text=plain_text(html),
        sort_name=path.name,
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


def copy_files(section):
    """除 Markdown 外的文件原样复制（实验 HTML、图片等），保持相对路径不变。"""
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
            
            dst = SITE / src.relative_to(ROOT)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)


# ---------- 页面模板 ----------
def emit(url, title, body, sections, active=None, math=False, body_class=""):
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
<meta name="description" content="{e(SITE_DESCRIPTION)}">
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
        items.append(
            f'<article class="post" data-tags="{e(json.dumps(post.tags, ensure_ascii=False))}">'
            f'<div class="post-meta"><time datetime="{e(post.date)}">{e(post.date)}</time>{path}</div>'
            f'<h2><a href="{link(root, post.url)}">{e(post.title)}</a></h2>{summary}{tags}</article>'
        )
    return f'<div class="post-list">{"".join(items)}</div>'


def toc_html(html):
    """用正文的一到三级标题生成目录；标题少于 2 个时不显示。宽屏和窄屏各用一份，由 CSS 切换。"""
    headings = re.findall(r'<h([1-3]) id="([^"]+)">(.*?)</h\1>', html, re.S)
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
    comments = comments_html() if section_option(section_of(doc), "comments") else ""
    body = (
        f'<main class="container">{trail}<article class="doc"><header class="doc-head"><h1>{e(doc.title)}</h1>'
        f'<div class="doc-meta"><time datetime="{e(doc.date)}">{e(doc.date)}</time>{tags}</div></header>'
        f'{toc_html(doc.html)}<div class="prose">{doc.html}</div></article>{comments}</main>'
    )
    emit(doc.url, doc.title, body, sections, active, math='class="math' in doc.html)


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
    chips = "".join(
        f'<a class="chip" href="#tag={quote(tag)}" data-tag="{e(tag)}">{e(tag)}<span>{n}</span></a>'
        for tag, n in sorted(counts.items(), key=lambda x: (-x[1], x[0]))
    )
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
    index = []
    for section in sections:
        copy_files(section.rel)
        render = render_list if section_option(section.rel, "view") == "list" else render_cards
        render(section, [], section.rel, sections, index)
    render_home(sections)

    data = json.dumps(index, ensure_ascii=False, separators=(",", ":"))
    (SITE / "_assets" / "search-index.js").write_text(f"window.SEARCH_INDEX={data};", encoding="utf-8")
    pages = sum(s.count for s in sections)
    print(f"完成：{len(sections)} 个栏目，{pages} 篇内容，输出到 {SITE}")


if __name__ == "__main__":
    build()
