#!/usr/bin/env python3
"""读取内容文件夹，生成整个网站到 _site/。用法：python build.py

约定：
- 根目录下每个第一级文件夹就是导航栏的一项（以 . 或 _ 开头的文件夹除外）。
- BLOG_SECTION 那个文件夹显示为博客列表（带标签筛选），其余显示为文件夹卡片。
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
from html import escape as e
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

# ---------- 配置 ----------
SITE_TITLE = "yu"
SITE_DESCRIPTION = "致力于折腾好玩的东西"
BLOG_SECTION = "articles"  # 这个第一级文件夹按博客方式显示
RECENT_POSTS = 10  # 主页显示几篇最近的文章
SUMMARY_LENGTH = 120  # 自动摘要（第一段）超过多少字就截断并加 ...
LABELS = {  # 文件夹的显示名；没写的会由文件夹名自动生成（signal processing → Signal Processing）
    "articles": "文章",
    "courses": "课程",
    "notes": "笔记",
    "experiments": "实验",
}
GISCUS = {  # 评论和表情回应，存在 GitHub Discussions 里。开通方法见 README；两个 ID 没填时不显示评论区
    "repo": "yxysjtu/yxysjtu.github.io",
    "repo_id": "R_kgDOVkSN5A",
    "category": "Announcements",
    "category_id": "DIC_kwDOVkSN5M4DKd4o",
}
# --------------------------

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
    summary: str = ""
    html: str = ""
    text: str = ""
    sort_name: str = ""


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
    return text[:SUMMARY_LENGTH] + "..." if len(text) > SUMMARY_LENGTH else text


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
    return Doc(
        src=rel,
        url=str(Path(rel).with_suffix(".html").as_posix()),
        kind="md",
        title=str(meta.get("title") or (heading and plain_text(heading.group(1))) or prettify(path.stem)),
        date=doc_date(path, meta.get("date")),
        tags=parse_tags(meta.get("tags")),
        summary=str(meta.get("summary") or excerpt(html)),
        html=html,
        text=plain_text(html),
        sort_name=path.name,
    )


def load_html(path, rel):
    source = read_text(path)
    title = re.search(r"<title[^>]*>(.*?)</title>", source, re.S | re.I)
    text = plain_text(source)
    return Doc(
        src=rel,
        url=str(Path(rel).with_name(path.stem + ".view.html").as_posix()),
        kind="html",
        title=re.sub(r"\s+", " ", title.group(1)).strip() if title and title.group(1).strip() else prettify(path.stem),
        date=doc_date(path),
        summary=truncate(text),
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
        dirnames[:] = [d for d in dirnames if not d.startswith((".", "_"))]
        for filename in filenames:
            src = Path(dirpath) / filename
            if ignored(src) or src.suffix.lower() in (".md", ".markdown"):
                continue
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
<html lang="zh-CN">
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
    <nav class="nav" aria-label="主导航">{nav}</nav>
    <div class="search" role="search">
      <input id="search-input" type="search" placeholder="搜索全部内容" aria-label="搜索全部内容" autocomplete="off">
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
    return f'<nav class="crumbs" aria-label="路径">{"<span class=sep>/</span>".join(parts)}</nav>'


def tag_links(root, tags):
    return "".join(f'<a class="tag" href="{root}{quote(BLOG_SECTION)}/index.html#tag={quote(t)}">{e(t)}</a>' for t in tags)


def post_list(root, posts):
    items = []
    for post in posts:
        tags = f'<div class="tags">{tag_links(root, post.tags)}</div>' if post.tags else ""
        summary = f"<p>{e(post.summary)}</p>" if post.summary else ""
        items.append(
            f'<article class="post" data-tags="{e(json.dumps(post.tags, ensure_ascii=False))}">'
            f'<time datetime="{e(post.date)}">{e(post.date)}</time>'
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
    return (
        f'<aside class="toc toc-side" aria-label="目录"><div class="toc-sticky"><div class="toc-title">目录</div>{links}</div></aside>'
        f'<details class="toc toc-inline"><summary>目录</summary>{links}</details>'
    )


def comments_html():
    if not (GISCUS["repo_id"] and GISCUS["category_id"]):
        return ""
    return (
        '<section class="comments" aria-label="Comments"><h2>Comments</h2>'
        f'<script src="https://giscus.app/client.js" data-repo="{e(GISCUS["repo"])}" data-repo-id="{e(GISCUS["repo_id"])}" '
        f'data-category="{e(GISCUS["category"])}" data-category-id="{e(GISCUS["category_id"])}" '
        'data-mapping="pathname" data-strict="1" data-reactions-enabled="1" data-emit-metadata="0" '
        'data-input-position="bottom" data-theme="light" data-lang="en" '
        'crossorigin="anonymous" async></script></section>'
    )


def render_doc(doc, crumbs, active, sections):
    root = "../" * doc.url.count("/")
    trail = crumbs_html(root, crumbs, doc.title)
    if doc.kind == "html":
        raw = quote(Path(doc.src).name)
        body = (
            f'<div class="frame-bar">{trail}<a class="frame-open" href="{raw}" target="_blank" rel="noopener">在新标签页打开</a></div>'
            f'<iframe class="frame" src="{raw}" title="{e(doc.title)}"></iframe>'
        )
        emit(doc.url, doc.title, body, sections, active, body_class="frame-page")
        return
    tags = f'<div class="tags">{tag_links(root, doc.tags)}</div>' if doc.tags else ""
    comments = comments_html() if doc.src.startswith(f"{BLOG_SECTION}/") else ""  # 只有文章有评论，课程内容没有
    body = (
        f'<main class="container">{trail}<article class="doc"><header class="doc-head"><h1>{e(doc.title)}</h1>'
        f'<div class="doc-meta"><time datetime="{e(doc.date)}">{e(doc.date)}</time>{tags}</div></header>'
        f'{toc_html(doc.html)}<div class="prose">{doc.html}</div></article>{comments}</main>'
    )
    emit(doc.url, doc.title, body, sections, active, math='class="math' in doc.html)


def card(root, url, icon, title, meta):
    return (
        f'<a class="card" href="{link(root, url)}">{icon}'
        f'<span class="card-body"><span class="card-title">{e(title)}</span>'
        f'<span class="card-meta">{e(meta)}</span></span></a>'
    )


def render_folder(folder, crumbs, active, sections, index):
    root = "../" * folder.url.count("/")
    child_crumbs = crumbs + [(folder.name, folder.url)]
    folders = []  # (排序名, 卡片 HTML)
    docs = []
    for sub in folder.subfolders:
        if sub.collapsed:
            doc = sub.docs[0]
            docs.append((Path(sub.rel).name, card(root, doc.url, ICON_DOC, doc.title, doc.date)))
            render_doc(doc, child_crumbs, active, sections)
            index_doc(index, doc, child_crumbs)
        else:
            folders.append((Path(sub.rel).name, card(root, sub.url, ICON_FOLDER, sub.name, f"{sub.count} 项")))
            render_folder(sub, child_crumbs, active, sections, index)
    for doc in folder.docs:
        docs.append((doc.sort_name, card(root, doc.url, ICON_DOC, doc.title, doc.date)))
        render_doc(doc, child_crumbs, active, sections)
        index_doc(index, doc, child_crumbs)
    cards = [c for _, c in sorted(folders, key=lambda x: natural_key(x[0]))]
    cards += [c for _, c in sorted(docs, key=lambda x: natural_key(x[0]))]
    grid = f'<div class="card-grid">{"".join(cards)}</div>' if cards else '<p class="empty">这里还没有内容。</p>'
    trail = crumbs_html(root, crumbs, folder.name) if crumbs else ""
    emit(folder.url, folder.name, f'<main class="container">{trail}<h1 class="page-title">{e(folder.name)}</h1>{grid}</main>',
         sections, active)
    index.append({"t": folder.name, "u": folder.url, "p": " / ".join(n for n, _ in crumbs), "g": [], "x": "", "k": "folder"})


def index_doc(index, doc, crumbs):
    index.append({"t": doc.title, "u": doc.url, "p": " / ".join(n for n, _ in crumbs), "g": doc.tags,
                  "x": doc.text, "k": "doc"})


def render_blog(section, sections, index):
    posts = sorted(section.all_docs(), key=lambda d: (d.date, d.title), reverse=True)
    root = "../" * section.url.count("/")
    crumbs = [(section.name, section.url)]
    for post in posts:
        render_doc(post, crumbs, section.rel, sections)
        index_doc(index, post, crumbs)

    counts = {}
    for post in posts:
        for tag in post.tags:
            counts[tag] = counts.get(tag, 0) + 1
    chips = "".join(
        f'<a class="chip" href="#tag={quote(tag)}" data-tag="{e(tag)}">{e(tag)}<span>{n}</span></a>'
        for tag, n in sorted(counts.items(), key=lambda x: (-x[1], x[0]))
    )
    if chips:
        chips = f'<a class="chip" href="#" data-tag="">全部<span>{len(posts)}</span></a>{chips}'

    # 日期选项：每年一项，后面跟这一年有文章的月份，都是新的在前
    date_counts = {}
    for post in posts:
        for period in (post.date[:4], post.date[:7]):
            date_counts[period] = date_counts.get(period, 0) + 1
    options = "".join(
        f'<option value="{e(period)}">{e(period)}（{n}）</option>'
        for period, n in sorted(date_counts.items(), key=lambda x: (x[0][:4], x[0] if len(x[0]) > 4 else "~"), reverse=True)
    )
    filters = (
        f'<div class="filters">{chips}<select id="date-filter" aria-label="按日期筛选">'
        f'<option value="">全部日期</option>{options}</select></div>'
        if posts else ""
    )
    if posts:
        content = post_list(root, posts) + '<p id="no-match" class="empty" hidden>没有符合条件的文章。</p>'
    else:
        content = '<p class="empty">还没有文章。</p>'
    emit(section.url, section.name,
         f'<main class="container"><h1 class="page-title">{e(section.name)}</h1>{filters}{content}</main>',
         sections, section.rel)
    return posts


def render_home(posts, blog, sections):
    recent = post_list("", posts[:RECENT_POSTS]) if posts else '<p class="empty">还没有文章。</p>'
    more = f'<p class="more"><a href="{link("", blog.url)}">全部{e(blog.name)} →</a></p>' if blog and len(posts) > RECENT_POSTS else ""
    body = (
        f'<main class="container"><div class="intro"><h1>{e(SITE_TITLE)}</h1><p>{e(SITE_DESCRIPTION)}</p></div>'
        f'<h2 class="section-title">最近的文章</h2>{recent}{more}</main>'
    )
    emit("index.html", SITE_TITLE, body, sections)


# ---------- 入口 ----------
def build():
    # 只清空内容、不删目录本身：Windows 上如果有终端或预览服务停在 _site 里，删目录会失败
    SITE.mkdir(exist_ok=True)
    for child in SITE.iterdir():
        shutil.rmtree(child) if child.is_dir() else child.unlink()
    (SITE / "_assets").mkdir()
    shutil.copy2(THEME / "site.js", SITE / "_assets" / "site.js")
    code_css = HtmlFormatter(style="default").get_style_defs("pre")
    (SITE / "_assets" / "style.css").write_text(read_text(THEME / "style.css") + "\n" + code_css, encoding="utf-8")

    dirs = sorted((p for p in ROOT.iterdir() if p.is_dir() and not ignored(p)), key=lambda p: natural_key(p.name))
    sections = [scan(p) for p in dirs]
    index = []
    posts, blog = [], None
    for section in sections:
        copy_files(section.rel)
        if section.rel == BLOG_SECTION:
            blog = section
            posts = render_blog(section, sections, index)
        else:
            render_folder(section, [], section.rel, sections, index)
    render_home(posts, blog, sections)

    data = json.dumps(index, ensure_ascii=False, separators=(",", ":"))
    (SITE / "_assets" / "search-index.js").write_text(f"window.SEARCH_INDEX={data};", encoding="utf-8")
    pages = sum(s.count for s in sections)
    print(f"完成：{len(sections)} 个栏目，{pages} 篇内容，输出到 {SITE}")


if __name__ == "__main__":
    build()
