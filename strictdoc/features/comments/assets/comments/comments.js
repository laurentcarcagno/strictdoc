// Comments in the margin, like Word: the balloons stand to the right of the node
// they are about, never overlap, and a thin line joins each balloon to the words
// that it is about (the text that was selected when the comment was added).
//
// - "Comment" in the node controls reads the current selection (before the click
//   removes it), opens the form of the node and remembers the words and which
//   occurrence of them it is (anchor, anchor_n).
// - A saved anchor is highlighted again at each render.
(function () {
  "use strict";

  var SKIP = "sdoc-node-controls, turbo-frame[id^='comments-'], script, style, [data-no-comment-anchor]";
  var MARK = "mark.sdoc-comment-anchor";
  var pendingSelection = null;
  var scheduled = false;
  var busy = false;

  function norm(s) { return s.replace(/\s+/g, " "); }

  // The text nodes of a node that a comment can be about, with their normalized text.
  function textNodes(root) {
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: function (n) {
        if (!n.nodeValue || !n.nodeValue.trim()) { return NodeFilter.FILTER_REJECT; }
        var p = n.parentElement;
        if (!p || p.closest(SKIP)) { return NodeFilter.FILTER_REJECT; }
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    var nodes = [];
    while (walker.nextNode()) { nodes.push(walker.currentNode); }
    return nodes;
  }

  // One string for the whole node, and for each character where it comes from.
  function flatten(root) {
    var text = "";
    var map = [];
    textNodes(root).forEach(function (node) {
      var raw = node.nodeValue;
      var prevSpace = text.length > 0 && text[text.length - 1] === " ";
      for (var i = 0; i < raw.length; i++) {
        var c = raw[i];
        if (/\s/.test(c)) {
          if (prevSpace) { continue; }
          text += " "; prevSpace = true;
        } else {
          text += c; prevSpace = false;
        }
        map.push({ node: node, offset: i });
      }
    });
    return { text: text, map: map };
  }

  function nodeOf(el) { return el.closest("sdoc-node"); }

  function unmark(root) {
    root.querySelectorAll(MARK).forEach(function (m) {
      var parent = m.parentNode;
      while (m.firstChild) { parent.insertBefore(m.firstChild, m); }
      parent.removeChild(m);
      parent.normalize();
    });
  }

  function wrap(node, from, to, cls, id) {
    // from/to are offsets in node.nodeValue.
    var range = document.createRange();
    range.setStart(node, from);
    range.setEnd(node, to);
    var mark = document.createElement("mark");
    mark.className = "sdoc-comment-anchor " + cls;
    if (id) { mark.setAttribute("data-comment-id", id); }
    range.surroundContents(mark);
    return mark;
  }

  // Highlights `anchor` (its n-th occurrence) in `root`. Returns the marks.
  function highlight(root, anchor, n, cls, id) {
    var flat = flatten(root);
    var needle = norm(anchor).trim();
    if (!needle) { return []; }
    var at = -1;
    for (var k = 0; k <= n; k++) {
      at = flat.text.indexOf(needle, at + 1);
      if (at < 0) { return []; }
    }
    // Group the characters of the match by text node, then wrap them (last node first,
    // so that offsets stay valid).
    var groups = [];
    for (var i = at; i < at + needle.length; i++) {
      var m = flat.map[i];
      if (!m) { continue; }
      var last = groups[groups.length - 1];
      if (last && last.node === m.node) { last.to = m.offset + 1; }
      else { groups.push({ node: m.node, from: m.offset, to: m.offset + 1 }); }
    }
    var marks = [];
    for (var g = groups.length - 1; g >= 0; g--) {
      marks.unshift(wrap(groups[g].node, groups[g].from, groups[g].to, cls, id));
    }
    return marks;
  }

  function frames() { return Array.prototype.slice.call(document.querySelectorAll("turbo-frame[id^='comments-']")); }

  function marginMode() { return window.matchMedia("(min-width: 1100px)").matches; }

  function content(frame) { return frame.closest("sdoc-node"); }

  function layout() {
    if (busy) { return; }
    busy = true;
    try {
      var main = document.querySelector(".main");
      if (!main) { return; }
      var nodesWithFrames = new Set();
      frames().forEach(function (f) { nodesWithFrames.add(content(f)); });
      nodesWithFrames.forEach(function (n) { if (n) { unmark(n); } });
      // Highlight the saved anchors.
      var marksOf = {};
      frames().forEach(function (frame) {
        var node = content(frame);
        if (!node) { return; }
        frame.querySelectorAll("sdoc-comment[data-anchor]").forEach(function (c) {
          var resolved = c.getAttribute("data-status") === "resolved";
          var marks = highlight(node, c.getAttribute("data-anchor"), parseInt(c.getAttribute("data-anchor-n") || "0", 10),
            resolved ? "sdoc-comment-anchor--resolved" : "", c.getAttribute("data-comment-id"));
          marksOf[frame.id + "/" + c.getAttribute("data-comment-id")] = marks;
        });
      });
      if (pendingSelection && pendingSelection.node && pendingSelection.node.isConnected) {
        highlight(pendingSelection.node, pendingSelection.text, pendingSelection.n, "sdoc-comment-anchor--pending", "");
      }
      // Stack the balloons so that they do not overlap. A balloon is placed
      // from the rectangle of its node, whatever element it sits in.
      var floor = -Infinity;
      var items = frames().filter(function (f) { return f.children.length > 0; });
      var margin = marginMode();
      items.forEach(function (f) {
        f.style.top = ""; f.style.left = ""; f.style.position = margin ? "absolute" : "";
      });
      if (margin) {
        var width = parseInt(getComputedStyle(document.documentElement).getPropertyValue("--sdoc-comment-width"), 10) || 320;
        items.forEach(function (f) { f.style.width = width + "px"; });
        items.sort(function (a, b) { return content(a).getBoundingClientRect().top - content(b).getBoundingClientRect().top; });
        items.forEach(function (f) {
          var node = content(f);
          var box = f.offsetParent ? f.offsetParent.getBoundingClientRect() : main.getBoundingClientRect();
          var nodeRect = node.getBoundingClientRect();
          // Level with the first highlighted words of the balloon, else with the node.
          var firstMark = node.querySelector(MARK + "[data-comment-id='" + ((f.querySelector("sdoc-comment[data-anchor]") || {getAttribute: function () { return ""; }}).getAttribute("data-comment-id")) + "']");
          var wantedY = firstMark ? firstMark.getBoundingClientRect().top : nodeRect.top;
          var y = Math.max(wantedY, floor);
          f.style.left = (nodeRect.right - box.left + 56) + "px";
          f.style.top = (y - box.top) + "px";
          floor = y + f.offsetHeight + 8;
        });
      }
      drawLines(main, marksOf);
    } finally {
      busy = false;
      // What this function changed is not a reason to run it again.
      observer.takeRecords();
    }
  }

  function drawLines(main, marksOf) {
    var svg = main.querySelector("svg.sdoc-comment-lines");
    if (!svg) {
      svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("class", "sdoc-comment-lines");
      main.appendChild(svg);
    }
    while (svg.firstChild) { svg.removeChild(svg.firstChild); }
    if (!marginMode()) { return; }
    var mainRect = main.getBoundingClientRect();
    svg.setAttribute("width", main.scrollWidth);
    svg.setAttribute("height", main.scrollHeight);
    function toMain(x, y) { return [x - mainRect.left + main.scrollLeft, y - mainRect.top + main.scrollTop]; }
    frames().forEach(function (frame) {
      frame.querySelectorAll("sdoc-comment[data-anchor]").forEach(function (c) {
        var marks = marksOf[frame.id + "/" + c.getAttribute("data-comment-id")] || [];
        if (!marks.length) { return; }
        var last = marks[marks.length - 1].getBoundingClientRect();
        var box = c.getBoundingClientRect();
        var a = toMain(last.right, last.top + last.height / 2);
        var b = toMain(box.left, box.top + Math.min(14, box.height / 2));
        var mid = toMain(box.left - 12, box.top);
        var path = document.createElementNS("http://www.w3.org/2000/svg", "path");
        path.setAttribute("d", "M" + a[0] + "," + a[1] + " L" + mid[0] + "," + a[1] + " L" + b[0] + "," + b[1]);
        path.setAttribute("class", "sdoc-comment-line" + (c.getAttribute("data-status") === "resolved" ? " sdoc-comment-line--resolved" : ""));
        path.setAttribute("data-comment-id", c.getAttribute("data-comment-id"));
        svg.appendChild(path);
      });
    });
  }

  function schedule() {
    if (scheduled) { return; }
    scheduled = true;
    window.requestAnimationFrame(function () { scheduled = false; layout(); });
  }

  // The selection inside a node, as the words and which occurrence of them it is.
  function readSelection(node) {
    var sel = window.getSelection();
    if (!sel || sel.rangeCount === 0 || sel.isCollapsed) { return null; }
    var range = sel.getRangeAt(0);
    if (!node.contains(range.commonAncestorContainer)) { return null; }
    var startEl = range.startContainer.nodeType === 1 ? range.startContainer : range.startContainer.parentElement;
    if (startEl && startEl.closest(SKIP)) { return null; }
    var text = norm(sel.toString()).trim();
    if (!text) { return null; }
    text = text.slice(0, 200);
    // Which occurrence: count the matches of the words that start before the selection.
    unmark(node);
    var flat = flatten(node);
    // Where the selection starts in the flat text of the node.
    var startIdx = flat.text.length;
    for (var s = 0; s < flat.map.length; s++) {
      var entry = flat.map[s];
      if (entry.node === range.startContainer && entry.offset >= range.startOffset) { startIdx = s; break; }
      if (range.startContainer.nodeType === 1 &&
          (range.startContainer.contains(entry.node) &&
           (range.startContainer.childNodes[range.startOffset] || {}) !== undefined)) {
        // The selection starts at an element boundary: first text node at or after it.
        var child = range.startContainer.childNodes[range.startOffset];
        if (!child || child === entry.node || child.contains(entry.node) ||
            (child.compareDocumentPosition(entry.node) & Node.DOCUMENT_POSITION_FOLLOWING)) { startIdx = s; break; }
      }
    }
    var n = 0, at = -1;
    while (true) {
      at = flat.text.indexOf(text, at + 1);
      if (at < 0 || at >= startIdx) { break; }
      n++;
    }
    return { node: node, text: text, n: n };
  }

  function openForm(mid, selection) {
    var frame = document.getElementById("comments-" + mid);
    if (!frame) { return; }
    var form = frame.querySelector("form.sdoc-comment-add");
    if (!form) { return; }
    pendingSelection = selection;
    form.hidden = false;
    form.querySelector("[data-comment-anchor-text]").value = selection ? selection.text : "";
    form.querySelector("[data-comment-anchor-n]").value = selection ? selection.n : 0;
    var quote = form.querySelector("[data-comment-quote]");
    quote.hidden = !selection;
    quote.textContent = selection ? "“" + selection.text + "”" : "";
    schedule();
    var area = form.querySelector("textarea");
    if (area) { area.focus(); }
  }

  // The button must read the selection before the click collapses it.
  document.addEventListener("mousedown", function (event) {
    var button = event.target.closest && event.target.closest("[data-comment-open]");
    if (!button) { return; }
    var node = nodeOf(button);
    var selection = node ? readSelection(node) : null;
    button.__selection = selection;
    event.preventDefault(); // keeps the selection while the form opens
  }, true);

  document.addEventListener("click", function (event) {
    var button = event.target.closest && event.target.closest("[data-comment-open]");
    if (button) {
      event.preventDefault();
      openForm(button.getAttribute("data-comment-open"), button.__selection || null);
      button.__selection = null;
      return;
    }
    var cancel = event.target.closest && event.target.closest("[data-comment-cancel]");
    if (cancel) {
      var form = cancel.closest("form");
      form.hidden = true;
      pendingSelection = null;
      form.reset();
      schedule();
      return;
    }
    var balloon = event.target.closest && event.target.closest("sdoc-comment");
    document.querySelectorAll("sdoc-comment.sdoc-comment--active, " + MARK + ".sdoc-comment-anchor--active, .sdoc-comment-line--active")
      .forEach(function (e) {
        e.classList.remove("sdoc-comment--active", "sdoc-comment-anchor--active", "sdoc-comment-line--active");
      });
    if (balloon) {
      var id = balloon.getAttribute("data-comment-id");
      balloon.classList.add("sdoc-comment--active");
      document.querySelectorAll(MARK + "[data-comment-id='" + id + "']").forEach(function (m) { m.classList.add("sdoc-comment-anchor--active"); });
      document.querySelectorAll(".sdoc-comment-lines path[data-comment-id='" + id + "']").forEach(function (p) { p.classList.add("sdoc-comment-line--active"); });
    }
  });

  // A submitted form leaves no pending selection.
  document.addEventListener("turbo:submit-end", function () { pendingSelection = null; schedule(); });
  ["turbo:load", "turbo:render", "turbo:frame-render", "load", "resize"].forEach(function (name) {
    window.addEventListener(name, schedule);
    document.addEventListener(name, schedule);
  });
  var observer = new MutationObserver(function (records) {
    if (busy) { return; }
    for (var i = 0; i < records.length; i++) {
      var t = records[i].target;
      var el = t.nodeType === 1 ? t : t.parentElement;
      if (el && el.closest && el.closest("svg.sdoc-comment-lines")) { continue; }
      if (records[i].addedNodes.length || records[i].removedNodes.length) { schedule(); return; }
    }
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });

  if (document.fonts && document.fonts.ready) { document.fonts.ready.then(schedule); }
  schedule();
})();
