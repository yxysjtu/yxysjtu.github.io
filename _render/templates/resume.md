---
extends: none
css: ./resume.css
pdf-bookmarks: false  # 一页的简历用不着书签，日期也不会混进书签里
style:
  # 这几项在 resume.css 里写成 var(--名字)，用这个模板的文档可以改
  accent: "#000"  # 姓名、栏目标题和下面那条线的颜色
  font-size: 11pt
  body-font: Resume Serif, SimSun, Songti SC, Noto Serif CJK SC  # Libertinus，中文用宋体
  heading-font: Resume Sans, Microsoft YaHei, PingFang SC, Noto Sans CJK SC
  name-size: 15.4pt
  name-align: left
  section-size: 13.2pt

  # 页面选项，所有模板都能用
  paper: A4
  page-margin: 10mm 9mm
  page-numbers: false
---

# Your Name

::: contact
you@example.com | [github.com/you](https://github.com/you)
:::

## Education

### University Name [2021/09 – 2025/06]{.date}

B.Eng. in Something [City, Country]{.place}

- GPA: 3.9 / 4.0
- *Note: an italic line looks like this.*

## Experience

### Company Name [2025/07 – 2025/08]{.date}

Job Title [City, Country]{.place}

- **Project name**: what you did, with **key numbers in bold**.
  - A second-level point uses a small triangle.

## Skills

- **Languages**: Python, C/C++. 这个文件是简历模板，打开它就能看到效果；任何文件夹里的文件写 `template: resume` 就能用，例子见 `examples/resume/resume.md`。
