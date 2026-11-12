"""网站配置。复用这个框架时，通常只需要改这个文件。改完重新运行 build.py 生效。"""

SITE_TITLE = "yu"
SITE_DESCRIPTION = "致力于折腾好玩的东西"
SITE_URL = "https://yxysjtu.github.io"  # 网站地址，分享卡片的链接和图片要用完整地址；留空就不加图片和链接
# Markdown 渲染规则和编辑器共用：本机构建时从这里复制最新的 md_render.py（相对博客文件夹）。
# 找不到这个文件时（比如 GitHub 上构建）直接用博客仓库里的副本；留空就不同步
RENDERER_SOURCE = "../markdown editor/md_render.py"
LANGUAGE = "en"  # 界面文字的语言："zh" 或 "en"，文字在 i18n.py 里

# 栏目：根目录下每个第一级文件夹都是导航栏的一项，导航栏按这里写的顺序排列。
# 没写在这里的文件夹也会显示，排在后面，并使用默认设置。可以写的设置：
#   view      "list" 列表视图：列出文件夹里所有文章，可以进入子文件夹，可以按标签和日期筛选
#             "cards" 卡片视图（默认）：把子文件夹和文件显示成卡片，一层层点进去
#   comments  True 表示这个栏目的文章有评论区（默认 False，还需要填好下面的 GISCUS）
#   home      True 表示这个栏目最新的文章显示在主页（默认 False）
#   folder_sort  文件夹的顺序："name" 按名字（默认）；"updated" 里面最近修改过的文件夹排前面
SECTIONS = {
    "articles": {"view": "list", "comments": True, "home": True},
    "courses": {"view": "cards", "folder_sort": "updated"},
    "projects": {"view": "cards", "comments": True},
    "life": {"view": "list"}
}

RECENT_POSTS = 10  # 主页显示几篇最近的文章
# 文章换了文件夹或改了名字后，旧网址跳转到新网址，以前分享出去的链接还能打开。
# 写生成后的网址（相对网站根目录，.md 换成 .html）
REDIRECTS = {
    "articles/wild_sea.html": "articles/reflections/wild_sea.html",
    "articles/the_frozen_road.html": "articles/reflections/the_frozen_road.html",
    "articles/winter_in_sweden.html": "articles/reflections/winter_in_sweden.html",
}
VISIBLE_TAGS = 10  # 列表页的标签栏默认显示文章最多的前几个标签，其余点“+N”展开
SUMMARY_LENGTH = 120  # 自动摘要（第一段）超过多少字就截断并加 ...

# 文件夹的显示名，任何一层的文件夹都可以写；没写的由文件夹名自动生成（signal processing → Signal Processing）
LABELS = {
    "articles": "文章",
    "courses": "课程",
    "projects": "项目",
    "notes": "笔记",
    "experiments": "实验",
    "life": "生活",
}

# 评论和表情回应，存在 GitHub Discussions 里。开通方法见 README；两个 ID 没填时不显示评论区
GISCUS = {
    "repo": "yxysjtu/yxysjtu.github.io",
    "repo_id": "R_kgDOVkSN5A",
    "category": "Announcements",
    "category_id": "DIC_kwDOVkSN5M4DKd4o",
    "lang": "en",  # 评论区的语言，和 LANGUAGE 分开设置
}
