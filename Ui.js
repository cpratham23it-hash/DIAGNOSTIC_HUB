// @ts-nocheck
/**
 * Diagnos — shared UI layer (theme toggle, floating dock, realistic effects).
 * Loaded at the end of <body> on every page by apply_ui.py.
 */
(function () {
  'use strict';
  var R = document.documentElement;

  function ls(k, v) {
    try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) {}
    return null;
  }
  function mk(tag, cls, html) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html) e.innerHTML = html;
    return e;
  }
  function ico(inner, cls) {
    return '<svg class="' + (cls || '') + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' + inner + '</svg>';
  }

  var ICON = {
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    moon: '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5Z"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    chat: '<path d="M21 12a8 8 0 0 1-11.6 7.1L3 21l1.9-5.4A8 8 0 1 1 21 12Z"/>',
    pulse: '<path d="M3 12h4l2-6 4 12 2-6h6"/>',
    spark: '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3Z"/>',
    up: '<path d="M6 14l6-6 6 6"/>'
  };

  /* ── effects on/off (defaults to off if OS prefers reduced motion) ── */
  var fx = ls('diagnos_fx') ? ls('diagnos_fx') === 'on' : !matchMedia('(prefers-reduced-motion: reduce)').matches;
  function applyFx() { R.classList.toggle('ui-nofx', !fx); }
  applyFx();

  /* ── toast ── */
  var toastEl = mk('div', 'ui-toast'), toastT;
  function toast(msg) {
    toastEl.textContent = msg;
    toastEl.classList.add('show');
    clearTimeout(toastT);
    toastT = setTimeout(function () { toastEl.classList.remove('show'); }, 1800);
  }

  /* ── theme (circular reveal via View Transitions when available) ── */
  function currentTheme() { return R.getAttribute('data-theme') === 'light' ? 'light' : 'dark'; }
  function setTheme(t, x, y) {
    function apply() { R.setAttribute('data-theme', t); ls('diagnos_theme', t); }
    if (!document.startViewTransition || !fx) { apply(); return; }
    var r = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y));
    var vt = document.startViewTransition(apply);
    vt.ready.then(function () {
      R.animate(
        { clipPath: ['circle(0px at ' + x + 'px ' + y + 'px)', 'circle(' + r + 'px at ' + x + 'px ' + y + 'px)'] },
        { duration: 650, easing: 'cubic-bezier(.4,0,.2,1)', pseudoElement: '::view-transition-new(root)' }
      );
    }).catch(function () {});
  }
  function toggleTheme(x, y) {
    var next = currentTheme() === 'light' ? 'dark' : 'light';
    setTheme(next, x == null ? innerWidth - 40 : x, y == null ? innerHeight - 40 : y);
    toast(next === 'light' ? 'Light mode' : 'Dark mode');
  }

  /* ── build background layers + dock ── */
  var aurora = mk('div', 'ui-aurora', '<div class="ui-blob"></div><div class="ui-blob"></div><div class="ui-blob"></div>');
  var spot = mk('div', 'ui-spot');
  var prog = mk('div', 'ui-progress');

  var dock = mk('div', 'ui-dock');
  var items = mk('div', 'ui-items');
  function fab(tag, tip, icon, extra) {
    var e = mk(tag, 'ui-fab', ico(icon));
    e.setAttribute('data-tip', tip);
    e.setAttribute('aria-label', tip);
    if (tag === 'button') e.type = 'button';
    if (extra && extra.href) e.href = extra.href;
    return e;
  }
  var bDash = fab('a', 'Dashboard', ICON.grid, { href: 'dashboard.html' });
  var bSym = fab('a', 'Symptom checker', ICON.chat, { href: 'symptom-checker.html' });
  var bDiag = fab('a', 'New diagnosis', ICON.pulse, { href: 'diagnosis.html' });
  var bFx = fab('button', 'Toggle effects', ICON.spark);
  var bTop = fab('button', 'Back to top', ICON.up);
  [bDash, bSym, bDiag, bFx, bTop].forEach(function (b) { items.appendChild(b); });

  var bTheme = mk('button', 'ui-fab', ico(ICON.sun, 'ui-ico-sun') + ico(ICON.moon, 'ui-ico-moon'));
  bTheme.type = 'button';
  bTheme.setAttribute('data-tip', 'Switch theme  (T)');
  bTheme.setAttribute('aria-label', 'Switch theme');
  var bMain = mk('button', 'ui-fab ui-main', ico(ICON.plus));
  bMain.type = 'button';
  bMain.setAttribute('aria-label', 'Quick actions');
  bMain.setAttribute('aria-expanded', 'false');

  dock.appendChild(items);
  dock.appendChild(bTheme);
  dock.appendChild(bMain);

  function syncFxBtn() { bFx.classList.toggle('off', !fx); }
  syncFxBtn();

  bMain.addEventListener('click', function () {
    var open = dock.classList.toggle('open');
    bMain.setAttribute('aria-expanded', open ? 'true' : 'false');
  });
  bTheme.addEventListener('click', function (e) {
    var r = bTheme.getBoundingClientRect();
    toggleTheme(r.left + r.width / 2, r.top + r.height / 2);
  });
  bFx.addEventListener('click', function () {
    fx = !fx; ls('diagnos_fx', fx ? 'on' : 'off'); applyFx(); syncFxBtn();
    toast(fx ? 'Effects on' : 'Effects off');
  });
  bTop.addEventListener('click', function () { scrollTo({ top: 0, behavior: 'smooth' }); });
  document.addEventListener('click', function (e) {
    if (!dock.contains(e.target)) { dock.classList.remove('open'); bMain.setAttribute('aria-expanded', 'false'); }
  });
  document.addEventListener('keydown', function (e) {
    var t = e.target, typing = t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName));
    if (typing || e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === 't' || e.key === 'T') toggleTheme();
    if (e.key === 'Escape') dock.classList.remove('open');
  });

  document.body.appendChild(aurora);
  document.body.appendChild(spot);
  document.body.appendChild(prog);
  document.body.appendChild(dock);
  document.body.appendChild(toastEl);

  /* ── scroll progress ── */
  function onScroll() {
    var max = R.scrollHeight - innerHeight;
    prog.style.setProperty('--p', max > 0 ? Math.min(1, scrollY / max) : 0);
  }
  addEventListener('scroll', onScroll, { passive: true });
  addEventListener('resize', onScroll);
  onScroll();

  /* ── pointer effects: spotlight, card tilt + glare, magnetic buttons ── */
  var TILT = '.app-card,.app-pick,.mod-card,.plan,.testi,.tech-card,.appliance-card,.stat-card';
  var lastCard = null, lastBtn = null, raf = 0;

  document.addEventListener('mousemove', function (e) {
    if (!fx || raf) return;
    raf = requestAnimationFrame(function () {
      raf = 0;
      spot.style.transform = 'translate3d(' + e.clientX + 'px,' + e.clientY + 'px,0)';

      var tgt = e.target && e.target.closest ? e.target : null;
      var card = tgt ? tgt.closest(TILT) : null;
      if (lastCard && lastCard !== card) lastCard.style.transform = '';
      if (card) {
        card.classList.add('ui-tilt');
        var b = card.getBoundingClientRect();
        var x = (e.clientX - b.left) / b.width, y = (e.clientY - b.top) / b.height;
        card.style.setProperty('--mx', (x * 100) + '%');
        card.style.setProperty('--my', (y * 100) + '%');
        card.style.transform = 'perspective(900px) rotateX(' + ((0.5 - y) * 6) + 'deg) rotateY(' + ((x - 0.5) * 8) + 'deg) translateY(-3px)';
      }
      lastCard = card;

      var btn = tgt ? tgt.closest('.btn-primary:not(:disabled)') : null;
      if (lastBtn && lastBtn !== btn) lastBtn.style.transform = '';
      if (btn) {
        var r = btn.getBoundingClientRect();
        btn.style.transform = 'translate(' + ((e.clientX - r.left - r.width / 2) * 0.18) + 'px,' + ((e.clientY - r.top - r.height / 2) * 0.28 - 1) + 'px)';
      }
      lastBtn = btn;
    });
  }, { passive: true });

  document.addEventListener('mouseleave', function () {
    if (lastCard) lastCard.style.transform = '';
    if (lastBtn) lastBtn.style.transform = '';
  });

  /* ── click ripple ── */
  document.addEventListener('click', function (e) {
    if (!fx || !e.target.closest) return;
    var t = e.target.closest('.btn,.option-btn,.slot-btn,.filter-chip,.app-pick');
    if (!t) return;
    var b = t.getBoundingClientRect(), s = Math.max(b.width, b.height) * 2, r = mk('span', 'ui-ripple');
    r.style.cssText = 'width:' + s + 'px;height:' + s + 'px;left:' + (e.clientX - b.left - s / 2) + 'px;top:' + (e.clientY - b.top - s / 2) + 'px';
    t.appendChild(r);
    setTimeout(function () { r.remove(); }, 650);
  });

  window.DiagnosUI = { toast: toast, setTheme: setTheme, toggleTheme: toggleTheme };
})();