(function () {
  var ROOT = document.currentScript.dataset.root;
  var ASSET_VERSION = document.currentScript.src.split('?')[1] || '';

  // ---------- 数学公式 ----------
  if (window.renderMathInElement) {
    renderMathInElement(document.querySelector('.doc'), { // 包括目录里的公式
      delimiters: [
        { left: '\\(', right: '\\)', display: false },
        { left: '\\[', right: '\\]', display: true }
      ],
      throwOnError: false
    });
  }

  // ---------- 目录：高亮当前章节 ----------
  var tocLinks = document.querySelectorAll('.toc-side a');
  if (tocLinks.length) {
    var targets = Array.prototype.map.call(tocLinks, function (a) {
      return document.getElementById(decodeURIComponent(a.hash.slice(1)));
    });
    var pinned = -1; // 刚点击的章节，一滚动就失效
    var pinnedY = 0;
    var updateToc = function () {
      if (window.scrollY !== pinnedY) pinned = -1;
      var current = 0;
      targets.forEach(function (target, i) {
        if (target && target.getBoundingClientRect().top <= 100) current = i;
      });
      // 滚到底时靠后的标题到不了顶部：优先高亮刚点击的章节，否则高亮最后一节
      var atBottom = window.scrollY > 0 && window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 2;
      if (atBottom) current = pinned !== -1 ? pinned : targets.length - 1;
      tocLinks.forEach(function (a, i) { a.classList.toggle('active', i === current); });
    };
    window.addEventListener('scroll', updateToc, { passive: true });
    tocLinks.forEach(function (a, i) {
      a.addEventListener('click', function () {
        setTimeout(function () { // 等浏览器跳转到锚点后再记录位置
          pinned = i;
          pinnedY = window.scrollY;
          updateToc();
        }, 0);
      });
    });
    window.addEventListener('resize', updateToc);
    updateToc();
  }

  // ---------- 实验页：路径栏对齐 iframe 里的正文 ----------
  var frame = document.querySelector('.frame');
  if (frame) {
    var frameBar = document.querySelector('.frame-bar');
    var alignFrameBar = function () {
      var content;
      try {
        content = frame.contentDocument.querySelector('main') || frame.contentDocument.querySelector('h1');
      } catch (err) {
        return; // 读不到 iframe 内容（比如直接双击打开网页）时保持默认边距
      }
      if (!content) return;
      var rect = content.getBoundingClientRect();
      frameBar.style.paddingLeft = Math.max(rect.left, 20) + 'px';
      frameBar.style.paddingRight = Math.max(window.innerWidth - rect.right, 20) + 'px';
    };
    frame.addEventListener('load', alignFrameBar);
    window.addEventListener('resize', alignFrameBar);
    alignFrameBar(); // iframe 可能在脚本运行前就加载好了
  }

  // ---------- 标签筛选（文章页，#tag=xxx） ----------
  var chips = document.querySelectorAll('.chip');
  if (chips.length) {
    var posts = document.querySelectorAll('.post');
    var applyTag = function () {
      var match = location.hash.match(/^#tag=(.+)$/);
      var tag = match ? decodeURIComponent(match[1]) : '';
      chips.forEach(function (chip) {
        chip.classList.toggle('active', chip.dataset.tag === tag);
      });
      posts.forEach(function (post) {
        post.hidden = tag !== '' && JSON.parse(post.dataset.tags).indexOf(tag) === -1;
      });
    };
    window.addEventListener('hashchange', applyTag);
    applyTag();
  }

  // ---------- 搜索 ----------
  var input = document.getElementById('search-input');
  var box = document.getElementById('search-results');
  var MAX_RESULTS = 20;
  var docs = null;
  var loading = false;

  function loadIndex() {
    if (docs || loading) return;
    loading = true;
    var script = document.createElement('script');
    script.src = ROOT + '_assets/search-index.js?' + ASSET_VERSION;
    script.onload = function () {
      docs = window.SEARCH_INDEX.map(function (d) {
        d.lt = d.t.toLowerCase();
        d.lp = d.p.toLowerCase();
        d.lg = d.g.join(' ').toLowerCase();
        d.lx = d.x.toLowerCase();
        return d;
      });
      runSearch();
    };
    document.head.appendChild(script);
  }

  function score(doc, terms) {
    var total = 0;
    for (var i = 0; i < terms.length; i++) {
      var term = terms[i];
      var hit = 0;
      if (doc.lt.indexOf(term) !== -1) hit += 10;
      if (doc.lg.indexOf(term) !== -1) hit += 5;
      if (doc.lp.indexOf(term) !== -1) hit += 2;
      if (doc.lx.indexOf(term) !== -1) hit += 1;
      if (!hit) return 0; // 每个词都要命中
      total += hit;
    }
    return doc.k === 'folder' ? total + 1 : total;
  }

  // 用 textContent 拼接，避免把内容当 HTML 解析
  function appendHighlighted(parent, text, terms) {
    var pattern = new RegExp('(' + terms.map(function (t) {
      return t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }).join('|') + ')', 'ig');
    text.split(pattern).forEach(function (part, i) {
      if (!part) return;
      if (i % 2) {
        var mark = document.createElement('mark');
        mark.textContent = part;
        parent.appendChild(mark);
      } else {
        parent.appendChild(document.createTextNode(part));
      }
    });
  }

  function snippet(doc, terms) {
    var at = -1;
    for (var i = 0; i < terms.length && at === -1; i++) at = doc.lx.indexOf(terms[i]);
    if (at === -1) return doc.x.slice(0, 80);
    var start = Math.max(0, at - 24);
    return (start ? '…' : '') + doc.x.slice(start, at + 72) + (at + 72 < doc.x.length ? '…' : '');
  }

  function span(className) {
    var el = document.createElement('span');
    el.className = className;
    return el;
  }

  function runSearch() {
    var query = input.value.trim().toLowerCase();
    box.textContent = '';
    if (!query) { box.hidden = true; return; }
    box.hidden = false;
    if (!docs) return;
    var terms = query.split(/\s+/);
    var results = docs
      .map(function (doc) { return { doc: doc, score: score(doc, terms) }; })
      .filter(function (r) { return r.score > 0; })
      .sort(function (a, b) { return b.score - a.score; })
      .slice(0, MAX_RESULTS);

    if (!results.length) {
      var empty = document.createElement('div');
      empty.className = 'search-empty';
      empty.textContent = '没有找到相关内容';
      box.appendChild(empty);
      return;
    }
    results.forEach(function (r) {
      var doc = r.doc;
      var a = document.createElement('a');
      a.href = ROOT + encodeURI(doc.u);
      var title = span('result-title');
      appendHighlighted(title, doc.t, terms);
      a.appendChild(title);
      if (doc.p) {
        var path = span('result-path');
        path.textContent = doc.p;
        a.appendChild(path);
      }
      if (doc.x) {
        var snip = span('result-snippet');
        appendHighlighted(snip, snippet(doc, terms), terms);
        a.appendChild(snip);
      }
      box.appendChild(a);
    });
  }

  input.addEventListener('focus', function () { loadIndex(); runSearch(); });
  input.addEventListener('input', function () { loadIndex(); runSearch(); });
  input.addEventListener('keydown', function (event) {
    if (event.key === 'Enter') {
      var first = box.querySelector('a');
      if (first) location.href = first.href;
    } else if (event.key === 'Escape') {
      box.hidden = true;
      input.blur();
    }
  });
  document.addEventListener('click', function (event) {
    if (!event.target.closest('.search')) box.hidden = true;
  });
})();
