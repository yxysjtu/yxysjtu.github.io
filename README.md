# yxysjtu.github.io

个人博客。`build.py` 读取文件夹，生成整个网站到 `_site/`（不提交到 git）。

## 更新网站

把文件放进对应文件夹，然后提交并推送。GitHub Actions 会自动构建和发布：

```bash
git add .
git commit -m "新增笔记"
git push
```

## 本地预览

首次使用先安装依赖：

```bash
pip install -r requirements.txt
```

之后运行下面的脚本（也可以在资源管理器里双击 `preview.sh`），它会重新构建网站并打开 <http://localhost:8000>：

```bash
bash preview.sh
```

按 Ctrl+C 停止预览。预览还开着时，改完内容再运行一次脚本即可，不会重复启动服务。

## 文件夹规则

```
articles/                     列表视图，最新的同时显示在主页
  hello-world.md              可以直接放文章
  技术/嵌入式/uart.md          也可以先分类，文件夹可以有很多层
courses/                      卡片视图
  statistics/
    notes/01_xxx.md           Markdown 笔记
    experiments/
      01_xxx/report.html      导出的实验 HTML（标题取自 <title>）
```

- 根目录下每个文件夹都是导航栏的一项，新建文件夹就会多一项。视图等设置在 `config.py` 里配置。
- 以 `.` 或 `_` 开头的文件夹和文件会被忽略。
- 文件名开头的数字用来排序，显示时会去掉（`01_data_description` → Data Description）。
- 图片等其他文件原样复制，用相对路径引用即可。
- git 不跟踪空文件夹，所以空的课程只在本地显示，放入内容后才会出现在线上。

## 配置

配置项都在 `config.py` 里，包括网站标题、界面语言、文件夹显示名、主页文章数量和评论区。

`LANGUAGE` 可以选 `"zh"` 或 `"en"`，界面文字在 `i18n.py` 里，要修改文字或增加语言都在这里改。文件夹显示名不跟着语言变，写在 `LABELS` 里。评论区的语言是 `GISCUS` 里单独的 `lang`。

每个栏目的设置写在 `SECTIONS` 里，导航栏也按这里的顺序排列：

```python
SECTIONS = {
    "articles": {"view": "list", "comments": True, "home": True},
    "courses": {"view": "cards"},
}
```

| 设置 | 含义 | 默认 |
| --- | --- | --- |
| `view` | `"list"` 列表视图，`"cards"` 卡片视图 | `"cards"` |
| `comments` | 这个栏目的文章是否有评论区 | `False` |
| `home` | 这个栏目最新的文章是否显示在主页 | `False` |

没写在 `SECTIONS` 里的文件夹也会显示，排在后面，使用默认设置。

两种视图的区别：

- **列表视图**：每个文件夹一页，列出它里面所有层的文章，上方是子文件夹的入口，点进去就只看这个分类。每页都可以按标签和日期筛选，标签只统计当前分类里的文章。点文章上的标签，会回到栏目首页按这个标签筛选全部文章。如果一个文件夹既有子文件夹，又直接放了文章，这些文章会多出一个“其他”入口，可以单独查看。
- **卡片视图**：子文件夹和文件都显示成卡片，一层层点进去，不能筛选。文章的标签只显示文字，不能点。

只放了一个 HTML 的文件夹不算一层，会直接显示这个 HTML。

复用这个框架时，复制 `build.py`、`config.py`、`i18n.py`、`_theme/`、`requirements.txt` 和 `.github/`，改好 `config.py`（`GISCUS` 要换成自己仓库的，或者把两个 ID 留空），再放入自己的内容文件夹。

## 文章开头的信息

通常只需要写标签，标题直接用一级标题：

```markdown
---
tags: [统计, 数学]
---

# 文章标题

正文……
```

其他几项也可以手动写，写了就优先用手写的：

```yaml
---
title: 标题        # 默认取第一个一级标题，没有就用文件名
date: 2026-11-05   # 默认取最后修改日期
summary: 摘要      # 见下面的说明
---
```

`summary` 在两种视图里的表现不同：列表视图没写时自动取第一段，超过 120 字时截断并加 ...（字数在 `config.py` 里改）；卡片视图只显示手写的，没写就不显示。HTML 文件没有这段开头信息，手写的摘要取 `<meta name="description" content="摘要">`。

最后修改日期：已提交且没再改动的文件取最后一次提交的日期，还没提交的改动取文件修改时间。修改已发布的文章后，它的日期会更新，在列表里的位置也会靠前；不想这样的话，就手动写 `date`。

公式用 `$...$` 和 `$$...$$`。

列表视图的页面可以按标签和起止日期筛选，两者可以同时用。日期可以手动输入，也可以在日历上选，日历上打点的日子有文章。筛选状态保存在网址里，比如 `articles/index.html#tag=统计&from=2026-11-01&to=2026-11-30`。

文章和笔记有 2 个以上标题时，会用一到三级标题自动生成目录。

## 评论和表情回应

文章页底部可以显示 [giscus](https://giscus.app/zh-CN) 评论区，数据存在本仓库的 GitHub Discussions 里。开通步骤（仓库要先推送到 GitHub，并且是公开的）：

1. 在仓库的 Settings → General → Features 里勾选 Discussions。
2. 安装 [giscus app](https://github.com/apps/giscus)，授权给这个仓库。
3. 打开 <https://giscus.app/zh-CN>，填入 `yxysjtu/yxysjtu.github.io`，分类选 Announcements，在页面下方生成的代码里找到 `data-repo-id` 和 `data-category-id`。
4. 把这两个值填进 `config.py` 里 `GISCUS` 的 `repo_id` 和 `category_id`，然后提交推送。

哪些栏目有评论区由 `SECTIONS` 的 `comments` 决定。没填这两个 ID 时不显示评论区。评论和回应要登录 GitHub 才能发。评论按文件路径匹配，文件改名或移动后，页面会和原来的评论断开。

## 修改网站

- 网站标题、导航栏显示名、栏目视图：`config.py`
- 样式和脚本：`_theme/`
