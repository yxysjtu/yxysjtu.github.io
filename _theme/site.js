(function () {
  var ROOT = document.currentScript.dataset.root;
  var ASSET_VERSION = document.currentScript.src.split('?')[1] || '';
  var TEXT = window.SITE_TEXT; // 界面文字，由 build.py 按 config.py 的语言写在这个文件开头

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

  // ---------- 标签和日期筛选（文章页，#tag=xxx&from=2026-11-01&to=2026-11-30） ----------
  var dateRange = document.getElementById('date-range');
  if (dateRange) {
    var chips = document.querySelectorAll('a.chip');
    var moreTags = document.querySelector('.chip-more');
    if (moreTags) {
      moreTags.addEventListener('click', function () {
        var open = moreTags.parentNode.classList.toggle('show-all');
        moreTags.setAttribute('aria-expanded', open);
        moreTags.textContent = open ? moreTags.dataset.less : moreTags.dataset.more;
      });
    }
    var posts = document.querySelectorAll('.post');
    var noMatch = document.getElementById('no-match');
    var fromInput = document.getElementById('date-from');
    var toInput = document.getElementById('date-to');
    var clearButton = document.getElementById('date-clear');
    var calendar = document.getElementById('date-calendar');

    var pad = function (n) { return (n < 10 ? '0' : '') + n; };
    var formatDate = function (y, m, d) { return y + '-' + pad(m + 1) + '-' + pad(d); };
    var parseDate = function (text) { // 接受 2026-1-5、2026/1/5、2026.1.5，不存在的日期返回 null
      var match = /^\s*(\d{4})[-\/.](\d{1,2})[-\/.](\d{1,2})\s*$/.exec(text || '');
      if (!match) return null;
      var y = +match[1], m = +match[2] - 1, d = +match[3];
      var date = new Date(y, m, d);
      return date.getMonth() === m && date.getDate() === d ? formatDate(y, m, d) : null;
    };
    var today = function () {
      var now = new Date();
      return formatDate(now.getFullYear(), now.getMonth(), now.getDate());
    };

    var postCounts = {}; // 每天有几篇文章，日历用它打点
    var latestPost = '';
    posts.forEach(function (post) {
      var date = post.querySelector('time').getAttribute('datetime');
      postCounts[date] = (postCounts[date] || 0) + 1;
      if (date > latestPost) latestPost = date;
    });

    var filterHash = function (tag, from, to) {
      var parts = [];
      if (tag) parts.push('tag=' + encodeURIComponent(tag));
      if (from) parts.push('from=' + from);
      if (to) parts.push('to=' + to);
      return '#' + parts.join('&');
    };
    var currentFilters = function () {
      var params = new URLSearchParams(location.hash.slice(1));
      var from = parseDate(params.get('from')) || '';
      var to = parseDate(params.get('to')) || '';
      if (from && to && from > to) { var swap = from; from = to; to = swap; }
      return { tag: params.get('tag') || '', from: from, to: to };
    };

    // ----- 日历 -----
    var activeField = 'from'; // 点日历时填哪个输入框
    var viewYear = 0;
    var viewMonth = 0;

    var navButton = function (label, text, years, months) {
      return '<button type="button" class="calendar-nav" aria-label="' + label + '" data-years="' + years +
        '" data-months="' + months + '">' + text + '</button>';
    };
    var renderCalendar = function () {
      var filters = currentFilters();
      var title = new Date(viewYear, viewMonth, 1).toLocaleDateString(document.documentElement.lang, { year: 'numeric', month: 'long' });
      var html = '<div class="calendar-head">' + navButton(TEXT.prev_year, '«', -1, 0) + navButton(TEXT.prev_month, '‹', 0, -1) +
        '<span class="calendar-title" aria-live="polite">' + title + '</span>' +
        navButton(TEXT.next_month, '›', 0, 1) + navButton(TEXT.next_year, '»', 1, 0) + '</div><div class="calendar-grid">';
      TEXT.weekdays.forEach(function (name) { html += '<span class="calendar-weekday">' + name + '</span>'; });
      var offset = (new Date(viewYear, viewMonth, 1).getDay() + 6) % 7; // 每周从周一开始
      for (var i = 0; i < offset; i++) html += '<span></span>';
      var days = new Date(viewYear, viewMonth + 1, 0).getDate();
      for (var d = 1; d <= days; d++) {
        var date = formatDate(viewYear, viewMonth, d);
        var count = postCounts[date] || 0;
        var isEdge = date === filters.from || date === filters.to;
        var inRange = filters.from && filters.to && date > filters.from && date < filters.to;
        var classes = 'calendar-day' + (count ? ' has-post' : '') + (isEdge ? ' is-edge' : '') +
          (inRange ? ' in-range' : '') + (date === today() ? ' is-today' : '');
        var label = count ? TEXT.day_posts[count === 1 ? 0 : 1].replace('{date}', date).replace('{n}', count) : date;
        html += '<button type="button" class="' + classes + '" data-date="' + date + '" aria-label="' + label +
          '" title="' + label + '"' + (isEdge ? ' aria-pressed="true"' : '') + '>' + d + '</button>';
      }
      calendar.innerHTML = html + '</div>';
    };
    var showMonthOf = function (date) {
      viewYear = +date.slice(0, 4);
      viewMonth = +date.slice(5, 7) - 1;
    };
    var openCalendar = function () {
      if (!calendar.hidden) return;
      var filters = currentFilters();
      showMonthOf((activeField === 'to' ? filters.to || filters.from : filters.from || filters.to) || latestPost || today());
      renderCalendar();
      calendar.hidden = false;
    };
    var closeCalendar = function () { calendar.hidden = true; };

    // ----- 筛选 -----
    var applyFilters = function () {
      var filters = currentFilters();
      fromInput.value = filters.from;
      toInput.value = filters.to;
      fromInput.classList.remove('invalid');
      toInput.classList.remove('invalid');
      clearButton.hidden = !(filters.from || filters.to);
      chips.forEach(function (chip) {
        chip.classList.toggle('active', chip.dataset.tag === filters.tag);
        chip.setAttribute('href', filterHash(chip.dataset.tag, filters.from, filters.to)); // 切换标签时保留日期
      });
      var visible = 0;
      posts.forEach(function (post) {
        var date = post.querySelector('time').getAttribute('datetime');
        var tagOk = !filters.tag || JSON.parse(post.dataset.tags).indexOf(filters.tag) !== -1;
        var dateOk = (!filters.from || date >= filters.from) && (!filters.to || date <= filters.to);
        post.hidden = !(tagOk && dateOk);
        if (!post.hidden) visible++;
      });
      noMatch.hidden = visible > 0;
      if (!calendar.hidden) renderCalendar();
    };
    var setDates = function (from, to) {
      location.hash = filterHash(currentFilters().tag, from, to);
      applyFilters();
    };
    var commitInput = function (input) { // 手动输入的日期：格式不对就标红，不改变筛选
      var filters = currentFilters();
      var text = input.value.trim();
      var date = parseDate(text);
      if (text && !date) {
        input.classList.add('invalid');
        return false;
      }
      var from = input === fromInput ? date || '' : filters.from;
      var to = input === toInput ? date || '' : filters.to;
      if (from && to && from > to) { var swap = from; from = to; to = swap; }
      setDates(from, to);
      if (date && !calendar.hidden) { showMonthOf(date); renderCalendar(); }
      return true;
    };

    [fromInput, toInput].forEach(function (input) {
      var field = input === fromInput ? 'from' : 'to';
      var activate = function () { activeField = field; openCalendar(); };
      input.addEventListener('focus', activate);
      input.addEventListener('click', activate);
      input.addEventListener('change', function () { commitInput(input); });
      input.addEventListener('input', function () { input.classList.remove('invalid'); });
      input.addEventListener('keydown', function (event) {
        if (event.key === 'Enter' && commitInput(input)) {
          closeCalendar();
          input.blur();
        }
      });
    });
    clearButton.addEventListener('click', function () {
      setDates('', '');
      closeCalendar();
    });
    // 点日历时不让输入框失去焦点，否则会触发 change 并打断选择
    calendar.addEventListener('mousedown', function (event) { event.preventDefault(); });
    calendar.addEventListener('click', function (event) {
      var button = event.target.closest('button');
      if (!button) return;
      if (button.classList.contains('calendar-nav')) {
        var month = new Date(viewYear + +button.dataset.years, viewMonth + +button.dataset.months, 1);
        viewYear = month.getFullYear();
        viewMonth = month.getMonth();
        renderCalendar();
        return;
      }
      var filters = currentFilters();
      var day = button.dataset.date;
      if (activeField === 'from') {
        setDates(day, filters.to && filters.to >= day ? filters.to : ''); // 新的开始日期晚于结束日期时，清空结束日期
        activeField = 'to';
        toInput.focus();
      } else {
        if (filters.from && day < filters.from) setDates(day, filters.from);
        else setDates(filters.from, day);
        closeCalendar();
        toInput.blur();
      }
    });
    document.addEventListener('click', function (event) {
      // 看点击路径而不是 event.target：日历重绘后，被点的按钮已经不在页面上了
      if (event.composedPath().indexOf(dateRange) === -1) closeCalendar();
    });
    document.addEventListener('focusin', function (event) {
      if (!event.target.closest('#date-range')) closeCalendar();
    });
    dateRange.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') {
        closeCalendar();
        document.activeElement.blur();
      }
    });
    window.addEventListener('hashchange', applyFilters);
    applyFilters();
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
      empty.textContent = TEXT.search_empty;
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
