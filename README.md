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
articles/                     博客列表，带标签筛选，最新的同时显示在主页
courses/                      文件夹卡片
  statistics/
    notes/01_xxx.md           Markdown 笔记
    experiments/
      01_xxx/report.html      导出的实验 HTML（标题取自 <title>）
```

- 根目录下每个文件夹都是导航栏的一项，新建文件夹就会多一项。
- 以 `.` 或 `_` 开头的文件夹和文件会被忽略。
- 文件名开头的数字用来排序，显示时会去掉（`01_data_description` → Data Description）。
- 图片等其他文件原样复制，用相对路径引用即可。
- git 不跟踪空文件夹，所以空的课程只在本地显示，放入内容后才会出现在线上。

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
summary: 摘要      # 默认取第一段，超过 120 字时截断并加 ...（字数在 build.py 开头改）
---
```

最后修改日期：已提交且没再改动的文件取最后一次提交的日期，还没提交的改动取文件修改时间。修改已发布的文章后，它的日期会更新，在列表里的位置也会靠前；不想这样的话，就手动写 `date`。

公式用 `$...$` 和 `$$...$$`。

文章页可以按标签和起止日期筛选，两者可以同时用。日期可以手动输入，也可以在日历上选，日历上打点的日子有文章。筛选状态保存在网址里，比如 `articles/index.html#tag=统计&from=2026-11-01&to=2026-11-30`。

文章和笔记有 2 个以上标题时，会用一到三级标题自动生成目录。

## 评论和表情回应

文章页底部可以显示 [giscus](https://giscus.app/zh-CN) 评论区，数据存在本仓库的 GitHub Discussions 里。开通步骤（仓库要先推送到 GitHub，并且是公开的）：

1. 在仓库的 Settings → General → Features 里勾选 Discussions。
2. 安装 [giscus app](https://github.com/apps/giscus)，授权给这个仓库。
3. 打开 <https://giscus.app/zh-CN>，填入 `yxysjtu/yxysjtu.github.io`，分类选 Announcements，在页面下方生成的代码里找到 `data-repo-id` 和 `data-category-id`。
4. 把这两个值填进 `build.py` 开头 `GISCUS` 的 `repo_id` 和 `category_id`，然后提交推送。

没填这两个 ID 时不显示评论区。评论和回应要登录 GitHub 才能发。评论按文件路径匹配，文件改名或移动后，页面会和原来的评论断开。

## 修改网站

- 网站标题、导航栏显示名：`build.py` 开头的配置
- 样式和脚本：`_theme/`
