/* ============================================================
   Alternate Clues Variant — deck logic and screen plumbing.

   The whole app is one shuffled array of image paths plus a cursor.
   `pos` is the card on screen; -1 means nothing drawn yet and the deck is
   sitting face down. `seen` is the furthest the cursor has ever reached, which
   is what tells a fresh draw (worth a flip) from stepping back through cards
   you have already read (no flip, they are not news).
   ============================================================ */

(function () {
  'use strict';

  var STORE_KEY = 'ah-clues-variant/v1';

  var state = {
    manifest: null,
    selected: [],   // expansion ids in play
    deck: [],       // shuffled list of image paths
    pos: -1,
    seen: -1
  };

  var el = {};
  var overlay = null;   // 'rules' | 'credits' | null
  var baseScreen = 'setup';

  /* ── helpers ─────────────────────────────────────────────── */

  function $(id) { return document.getElementById(id); }

  function cacheDom() {
    ['setup', 'game', 'rules', 'credits', 'expansion-list', 'deck-total-count',
     'begin', 'resume', 'resume-pos', 'resume-total', 'to-setup', 'counter-pos',
     'counter-total', 'stage', 'card-frame', 'flipper', 'face-back', 'face-front',
     'tap-to-draw', 'exhausted', 'exhausted-count', 'reshuffle', 'prev', 'next'
    ].forEach(function (id) {
      el[id] = $(id);
    });
  }

  /* Fisher-Yates. crypto gives a better shuffle than Math.random and every
     browser that can run this app has it. */
  function shuffle(arr) {
    var rand = window.crypto && window.crypto.getRandomValues
      ? function (n) {
          var buf = new Uint32Array(1);
          var limit = Math.floor(0xFFFFFFFF / n) * n;
          var v;
          do { window.crypto.getRandomValues(buf); v = buf[0]; } while (v >= limit);
          return v % n;
        }
      : function (n) { return Math.floor(Math.random() * n); };

    for (var i = arr.length - 1; i > 0; i--) {
      var j = rand(i + 1);
      var t = arr[i]; arr[i] = arr[j]; arr[j] = t;
    }
    return arr;
  }

  /* ── persistence ─────────────────────────────────────────── */

  function save() {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify({
        selected: state.selected,
        deck: state.deck,
        pos: state.pos,
        seen: state.seen
      }));
    } catch (e) { /* private mode, quota — the app still plays, just forgetfully */ }
  }

  function load() {
    try {
      var raw = localStorage.getItem(STORE_KEY);
      if (!raw) return null;
      var d = JSON.parse(raw);
      if (!d || !Array.isArray(d.deck) || !d.deck.length) return null;
      return d;
    } catch (e) { return null; }
  }

  function clearSaved() {
    try { localStorage.removeItem(STORE_KEY); } catch (e) {}
  }

  /* ── screens ─────────────────────────────────────────────── */

  function render() {
    ['setup', 'game'].forEach(function (id) {
      el[id].classList.toggle('is-active', id === baseScreen);
    });
    ['rules', 'credits'].forEach(function (id) {
      el[id].classList.toggle('is-active', id === overlay);
    });
  }

  function openOverlay(name) { overlay = name; render(); }
  function closeOverlay() { overlay = null; render(); }

  function goto(screen) {
    baseScreen = screen;
    overlay = null;
    if (screen === 'setup') refreshResume();
    render();
  }

  /* A game in progress is offered, never forced. Landing straight in a deck you
     half-finished last week is disorienting; the menu stays the front door. */
  function refreshResume() {
    var can = state.deck.length > 0 && state.pos >= 0 && state.pos < state.deck.length;
    el.resume.hidden = !can;
    if (can) {
      el['resume-pos'].textContent = state.pos + 1;
      el['resume-total'].textContent = state.deck.length;
    }
    // Whichever action is the likely one wears the solid treatment.
    el.begin.classList.toggle('btn-primary', !can);
    el.begin.classList.toggle('btn-ghost', can);
  }

  /* ── setup screen ────────────────────────────────────────── */

  function buildExpansionList() {
    el['expansion-list'].innerHTML = '';

    state.manifest.expansions.forEach(function (exp) {
      var li = document.createElement('li');

      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'exp-row';
      btn.dataset.exp = exp.id;
      btn.setAttribute('aria-pressed', exp.always ? 'true' : 'false');
      if (exp.always) btn.disabled = true;

      var mark = document.createElement('span');
      mark.className = 'exp-mark';

      var text = document.createElement('span');
      text.className = 'exp-text';

      var name = document.createElement('span');
      name.className = 'exp-name';
      name.textContent = exp.name;

      text.appendChild(name);

      // The only thing worth saying under a name is why the base game can't be
      // switched off; per-expansion counts just repeat the deck total below.
      if (exp.always) {
        var meta = document.createElement('span');
        meta.className = 'exp-meta';
        meta.textContent = 'Always included';
        text.appendChild(meta);
      }

      btn.appendChild(mark);
      btn.appendChild(text);
      li.appendChild(btn);
      el['expansion-list'].appendChild(li);

      if (exp.always) return;
      btn.addEventListener('click', function () {
        btn.setAttribute('aria-pressed', btn.getAttribute('aria-pressed') === 'true' ? 'false' : 'true');
        updateDeckTotal();
      });
    });
  }

  function chosenExpansions() {
    var rows = el['expansion-list'].querySelectorAll('.exp-row');
    var ids = [];
    Array.prototype.forEach.call(rows, function (r) {
      if (r.getAttribute('aria-pressed') === 'true') ids.push(r.dataset.exp);
    });
    return ids;
  }

  function applySelectionToUi(ids) {
    var rows = el['expansion-list'].querySelectorAll('.exp-row');
    Array.prototype.forEach.call(rows, function (r) {
      var on = r.disabled || ids.indexOf(r.dataset.exp) !== -1;
      r.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    updateDeckTotal();
  }

  function updateDeckTotal() {
    var ids = chosenExpansions();
    var total = 0;
    state.manifest.expansions.forEach(function (exp) {
      if (ids.indexOf(exp.id) !== -1) total += exp.count;
    });
    el['deck-total-count'].textContent = total;
  }

  /* ── deck ────────────────────────────────────────────────── */

  function buildDeck(ids) {
    var paths = [];
    state.manifest.expansions.forEach(function (exp) {
      if (ids.indexOf(exp.id) === -1) return;
      exp.cards.forEach(function (card) {
        paths.push(exp.dir + '/' + card + '.webp');
      });
    });
    return shuffle(paths);
  }

  function startGame(ids) {
    state.selected = ids;
    state.deck = buildDeck(ids);
    state.pos = -1;
    state.seen = -1;
    save();
    resetCard();
    updateGameUi();
    goto('game');
    preload(0);
  }

  function resetCard() {
    el.flipper.classList.remove('is-face-up');
    el['face-front'].removeAttribute('src');
    el['face-front'].alt = '';
    el.exhausted.hidden = true;
  }

  /* ── drawing ─────────────────────────────────────────────── */

  var busy = false;

  function preload(index) {
    if (index < 0 || index >= state.deck.length) return;
    var img = new Image();
    img.src = state.deck[index];
  }

  function cardLabel(index) {
    // "base_017" → "Alternate Clues card 17 of the base game"
    var file = state.deck[index].split('/').pop().replace('.webp', '');
    return 'Alternate Clues card: ' + file.replace(/_/g, ' ');
  }

  /* Swap the front face and hand back a promise that settles once the image is
     actually decoded, so the flip never reveals a blank rectangle. */
  function setFront(index) {
    var img = el['face-front'];
    img.alt = cardLabel(index);
    img.src = state.deck[index];
    if (img.decode) {
      return img.decode().catch(function () {});
    }
    if (img.complete) return Promise.resolve();
    return new Promise(function (res) {
      img.addEventListener('load',  res, { once: true });
      img.addEventListener('error', res, { once: true });
    });
  }

  function next() {
    if (busy) return;
    if (state.pos >= state.deck.length) return;

    var target = state.pos + 1;

    if (target >= state.deck.length) {   // ran off the end of the deck
      state.pos = target;
      save();
      updateGameUi();
      return;
    }

    var isNewDraw = target > state.seen;
    busy = true;

    setFront(target).then(function () {
      state.pos = target;
      if (target > state.seen) state.seen = target;
      el.exhausted.hidden = true;

      if (isNewDraw && !el.flipper.classList.contains('is-face-up')) {
        // Coming off the face-down deck: let the flip play.
        requestAnimationFrame(function () {
          el.flipper.classList.add('is-face-up');
        });
      } else {
        el.flipper.classList.add('is-face-up');
      }

      save();
      updateGameUi();
      preload(target + 1);
      busy = false;
    });
  }

  function prev() {
    if (busy || state.pos < 0) return;

    var target = state.pos - 1;

    if (target < 0) {                    // back to the undrawn deck
      state.pos = -1;
      el.exhausted.hidden = true;
      el.flipper.classList.remove('is-face-up');
      save();
      updateGameUi();
      return;
    }

    busy = true;
    setFront(target).then(function () {
      state.pos = target;
      el.exhausted.hidden = true;
      el.flipper.classList.add('is-face-up');
      save();
      updateGameUi();
      busy = false;
    });
  }

  function updateGameUi() {
    var total = state.deck.length;
    var done = state.pos >= total;

    el['counter-total'].textContent = total;
    el['counter-pos'].textContent = state.pos < 0 ? '—' : Math.min(state.pos + 1, total);

    el['tap-to-draw'].hidden = state.pos !== -1;
    el.exhausted.hidden = !done;
    el['exhausted-count'].textContent = total;

    el.prev.disabled = state.pos < 0;
    el.next.disabled = done;
    el.next.querySelector('span').textContent =
      state.pos < state.seen ? 'Next' : 'Draw';
  }

  /* ── input ───────────────────────────────────────────────── */

  function wireSwipe() {
    var x0 = 0, y0 = 0, t0 = 0, tracking = false;

    el.stage.addEventListener('touchstart', function (e) {
      if (e.touches.length !== 1) { tracking = false; return; }
      x0 = e.touches[0].clientX;
      y0 = e.touches[0].clientY;
      t0 = Date.now();
      tracking = true;
    }, { passive: true });

    el.stage.addEventListener('touchend', function (e) {
      if (!tracking) return;
      tracking = false;
      var t = e.changedTouches[0];
      var dx = t.clientX - x0;
      var dy = t.clientY - y0;
      // Horizontal, decisive, and not a slow drag.
      if (Math.abs(dx) < 45 || Math.abs(dx) < Math.abs(dy) * 1.6) return;
      if (Date.now() - t0 > 700) return;
      if (dx < 0) next(); else prev();
    }, { passive: true });
  }

  function wire() {
    el.begin.addEventListener('click', function () {
      startGame(chosenExpansions());
    });

    el['to-setup'].addEventListener('click', function () {
      goto('setup');
    });

    el.resume.addEventListener('click', function () {
      goto('game');
    });

    el['tap-to-draw'].addEventListener('click', next);
    el.next.addEventListener('click', next);
    el.prev.addEventListener('click', prev);

    el.reshuffle.addEventListener('click', function () {
      startGame(state.selected);
    });

    // Tapping a face-up card draws the next one — the obvious phone gesture.
    el['card-frame'].addEventListener('click', function (e) {
      if (e.target === el['tap-to-draw'] || el['tap-to-draw'].contains(e.target)) return;
      if (state.pos < 0 || state.pos >= state.deck.length) return;
      next();
    });

    document.querySelectorAll('[data-open]').forEach(function (b) {
      b.addEventListener('click', function () { openOverlay(b.dataset.open); });
    });
    document.querySelectorAll('[data-close]').forEach(function (b) {
      b.addEventListener('click', closeOverlay);
    });

    document.addEventListener('keydown', function (e) {
      if (overlay) {
        if (e.key === 'Escape') closeOverlay();
        return;
      }
      if (baseScreen !== 'game') return;
      if (e.key === 'ArrowRight' || e.key === ' ' || e.key === 'Enter') { e.preventDefault(); next(); }
      if (e.key === 'ArrowLeft') { e.preventDefault(); prev(); }
    });

    wireSwipe();
  }

  /* ── boot ────────────────────────────────────────────────── */

  function restore(saved) {
    // Only trust a saved game whose cards still exist in the current manifest.
    var known = {};
    state.manifest.expansions.forEach(function (exp) {
      exp.cards.forEach(function (c) { known[exp.dir + '/' + c + '.webp'] = true; });
    });
    if (!saved.deck.every(function (p) { return known[p]; })) return false;

    state.selected = saved.selected || ['base'];
    state.deck = saved.deck;
    state.seen = typeof saved.seen === 'number' ? saved.seen : -1;
    state.pos = typeof saved.pos === 'number' ? saved.pos : -1;

    applySelectionToUi(state.selected);
    resetCard();

    if (state.pos >= 0 && state.pos < state.deck.length) {
      el.flipper.classList.add('no-anim');
      setFront(state.pos).then(function () {
        el.flipper.classList.add('is-face-up');
        // Drop the freeze a frame later, once the face-up transform has landed.
        requestAnimationFrame(function () {
          requestAnimationFrame(function () {
            el.flipper.classList.remove('no-anim');
          });
        });
        updateGameUi();
      });
    }
    updateGameUi();
    preload(state.pos + 1);
    return true;
  }

  function boot() {
    cacheDom();
    wire();

    fetch('cards/manifest.json', { cache: 'no-cache' })
      .then(function (r) {
        if (!r.ok) throw new Error('manifest ' + r.status);
        return r.json();
      })
      .then(function (m) {
        state.manifest = m;
        buildExpansionList();
        updateDeckTotal();

        var saved = load();
        if (saved && !restore(saved)) {
          clearSaved();
          applySelectionToUi(['base']);
        }
        refreshResume();
      })
      .catch(function (err) {
        el['expansion-list'].innerHTML =
          '<li class="exp-meta">The deck could not be loaded. ' +
          'Check your connection and reload.</li>';
        el.begin.disabled = true;
        // eslint-disable-next-line no-console
        console.error(err);
      });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
