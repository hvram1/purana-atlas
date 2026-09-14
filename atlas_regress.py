#!/usr/bin/env python3
"""Drive the published pages in a real browser and check they still work.

    ./atlas_regress.py                 run every page, compare to the baseline
    ./atlas_regress.py --update        rewrite the baseline from this run
    ./atlas_regress.py --page kartika-atlas.html
    ./atlas_regress.py --keep          leave the instrumented copies for reading
    ./atlas_regress.py --repo ../smp   drive another deployment repo's pages

ANY DEPLOYMENT REPO, NOT ONLY THIS ONE. `purana-atlas`, `smp` and
`jagadguru-anugraha-bhashanam` are three sites with one contract, and a page is
not tested because it happens to sit next to this file. `--repo` points the run
at another checkout; every top-level directory there is linked into the scratch
root so relative fetches resolve, and its baseline is kept HERE as
`baselines/atlas_regress.<repo>.json` — test data does not belong in a
deployment, where GitHub Pages would publish it.

`refresh.py --check` already verifies the DATA: that a substrate parses, that
`cards` is a dict and `events` is a list, that the deep links resolve. It cannot
tell you whether pressing a mark plays anything, because nothing in a JSON file
knows that. Every atlas failure that reached the published site got past those
checks:

  * the player bootstrap race -- `iframe_api` appended BEFORE
    `onYouTubeIframeAPIReady` was defined. The page renders perfectly and every
    row is silent. Caught here by intercepting the append and asking whether
    the callback existed at that instant (`yt_order`).
  * 114 px of horizontal overflow on a phone. Caught here by loading at 390 px
    and comparing scrollWidth to clientWidth -- not by reading the CSS.
  * marks published below the confidence floor, and marks linked to episodes
    that only chanted the speaker tag. A mark that cannot be pressed, or that
    lands somewhere other than the time printed on its own face, is the
    behavioural half of that; `bad_time` is the check.

THE CONTRACT THIS ENFORCES, and it is deliberately about behaviour rather than
about class names, so it does not need a selector registry per page:

    pressing a control must do exactly one of three things --
      play      the stubbed player receives loadVideoById / seekTo / cueVideoById
      refuse    #toast is shown with a non-empty message
      act       the DOM changes

    a control that does none of the three is DEAD, and that is the finding.

Silence is the bug this catches, because silence is what every one of the
failures above looked like from the outside.

HOW IT RUNS. No Selenium, no CDP, no websocket client. Each page is copied to a
scratch directory with two script tags injected -- a stub of the YouTube IFrame
API at the top of <head>, a prober before </body> -- and served over
`http.server` (file:// would have fetch() blocked by CORS). Chrome runs
headless with `--dump-dom`; the prober leaves its findings in a <pre> as base64
so no page content can be mistaken for the result. Network is blackholed with
--host-resolver-rules: nothing here touches YouTube or Google Fonts.

THE BASELINE IS THE POINT. Numbers move for good reasons -- a new recording
adds marks, a new lane appears. So the run compares against
`baselines/atlas_regress.json` and fails only on a REGRESSION: a control that
went dead, a mark that stopped playing, a lane that disappeared, a JS error, an
overflow, a bad seek. `--update` after a legitimate change, and the diff in
that file is then the record of what moved and when.
"""
import argparse
import base64
import http.server
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))


def baseline_path(repo):
    name = os.path.basename(os.path.normpath(repo))
    fname = ('atlas_regress.json' if os.path.samefile(repo, HERE)
             else 'atlas_regress.%s.json' % name)
    return os.path.join(HERE, 'baselines', fname)
CHROME = next((p for p in ('/usr/bin/google-chrome', '/usr/bin/google-chrome-stable',
                           '/usr/bin/chromium', '/usr/bin/chromium-browser')
               if os.path.exists(p)), None)

# Seconds of slack between the time printed on a mark and the time the player
# is sent to. play() seeks to o.s - 0.4 on purpose, and the face is rendered
# through mmss(), so a whole second of rounding is expected. Anything past this
# means the mark and the seek disagree about which verse it is.
TIME_SLACK = 2.0

# Bump whenever the way a page is swept or counted changes. On 2026-09-14 the
# sweep went from a one-time snapshot to a live re-query: nothing on the site
# changed, and seven atlases' played counts moved anyway -- some up (controls
# the snapshot never reached), Śrāvaṇa down 20 (the snapshot had been pressing
# detached buttons whose direct onclick still fired: plays no user could make).
# Counts from two instruments are not a comparison, so compare() refuses one.
HARNESS_VERSION = 3

# THE PHONE PASS RUNS IN A 390 PX IFRAME, because headless Chrome will not make
# a window narrower than 500 px: --window-size=390 and =360 both report
# innerWidth 500. Until v3 every "0 overflow at 390px" this file printed was
# measured at 500. An iframe has no such floor, so the page is loaded inside
# one inside a normal window, and the prober reports the width it actually got
# -- a phone pass that did not run at phone width fails rather than passes.
PHONE_WIDTH = 390

STUB = r"""<script>
(function(){
  var R = {ytOrder:null, calls:[], errors:[], worstOverflow:0, worstAt:null};
  window.__R = R;
  window.addEventListener('error', function(e){
    R.errors.push(String(e.message) + ' @' + (e.lineno || '?'));
  });
  // The append is synchronous and adjacent to the callback's definition, so
  // this is the only moment at which their order can be observed. A
  // MutationObserver cannot see it -- it fires after both have run.
  var origAppend = document.head.appendChild.bind(document.head);
  document.head.appendChild = function(n){
    if (n && n.tagName === 'SCRIPT' && /iframe_api/.test(n.src || '')) {
      // STICKY FALSE. The first version of this recorded only the latest
      // append, so a page that requested the API early and then requested it
      // again after defining the callback reported "fine" -- the mutation test
      // with an injected race passed, which is the one outcome a regression
      // check must never produce. Any append before the callback exists is the
      // fault, whatever happens afterwards.
      var defined = (typeof window.onYouTubeIframeAPIReady === 'function');
      R.ytOrder = (R.ytOrder === null) ? defined : (R.ytOrder && defined);
      setTimeout(function(){
        if (typeof window.onYouTubeIframeAPIReady === 'function') {
          try { window.onYouTubeIframeAPIReady(); }
          catch(e){ R.errors.push('onYouTubeIframeAPIReady: ' + e.message); }
        }
      }, 0);
      return n;                      // never actually load YouTube
    }
    return origAppend(n);
  };
  window.YT = {
    PlayerState:{UNSTARTED:-1, ENDED:0, PLAYING:1, PAUSED:2, BUFFERING:3, CUED:5},
    Player: function(el, opts){
      var self = this;
      this.loadVideoById = function(o){
        R.calls.push({fn:'loadVideoById', v:(o&&o.videoId)||null, at:(o&&o.startSeconds)||0}); };
      this.cueVideoById = function(o){
        R.calls.push({fn:'cueVideoById', v:(o&&o.videoId)||null, at:(o&&o.startSeconds)||0}); };
      this.seekTo = function(t){ R.calls.push({fn:'seekTo', v:null, at:t}); };
      this.playVideo = function(){ R.calls.push({fn:'playVideo', v:null, at:null}); };
      this.pauseVideo = function(){ R.calls.push({fn:'pauseVideo', v:null, at:null}); };
      this.stopVideo=function(){};
      this.getCurrentTime=function(){return 0;}; this.getPlayerState=function(){return 2;};
      this.getDuration=function(){return 3600;}; this.destroy=function(){};
      this.getIframe=function(){return document.createElement('iframe');};
      this.addEventListener=function(){}; this.removeEventListener=function(){};
      setTimeout(function(){
        if (opts && opts.events && opts.events.onReady) {
          try { opts.events.onReady({target:self}); } catch(e){}
        }
      }, 0);
    }
  };
})();
</script>
"""

PROBE = r"""<script>
(function(){
  var R = window.__R;
  function all(s){ return Array.prototype.slice.call(document.querySelectorAll(s)); }
  function faceSeconds(t){
    var m = /(\d+):(\d\d)(?::(\d\d))?/.exec(t || '');
    if (!m) return null;
    return m[3] ? (+m[1]*3600 + +m[2]*60 + +m[3]) : (+m[1]*60 + +m[2]);
  }
  function clearToast(){
    var t = document.getElementById('toast');
    if (t) { t.className = t.className.replace(/\bshow\b/g,''); t.textContent = ''; }
  }
  // takeRecords() is synchronous; the observer's own callback is not, and a
  // click's effect has to be read before the next click happens.
  function probe(el){
    var before = R.calls.length, mo = new MutationObserver(function(){});
    clearToast();
    mo.observe(document.documentElement, {childList:true, subtree:true,
                                          attributes:true, characterData:true});
    var err = null;
    try { el.click(); } catch(e) { err = String(e.message); }
    var mut = mo.takeRecords().length;
    mo.disconnect();
    // THE WORST STATE, NOT THE LAST ONE. Overflow used to be read once, after
    // the sweep -- and the sweep ends on whatever view its last press opened.
    // The edition's index reported 0 while its "What it draws on" tab stood
    // 11px past a 390px screen: a pass on exactly the defect it exists to find.
    var de = document.documentElement, ov = de.scrollWidth - de.clientWidth;
    if (ov > R.worstOverflow) {
      R.worstOverflow = ov;
      R.worstAt = (el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 40);
    }
    var t = document.getElementById('toast');
    var toast = (t && /\bshow\b/.test(t.className) && t.textContent.trim()) || null;
    return {call: R.calls.length > before ? R.calls[R.calls.length-1] : null,
            mut: mut, toast: toast, err: err};
  }

  function sweepMarks(out, sel){
    var marks = all(sel);
    marks.forEach(function(m){
      if (m.disabled) return;
      out.marks.total++;
      var r = probe(m);
      if (r.err) { out.marks.errors.push({t:(m.textContent||'').trim().slice(0,40), e:r.err}); return; }
      if (r.call) {
        out.marks.played++;
        var face = faceSeconds(m.textContent);
        if (face !== null && r.call.at != null) {
          var d = Math.abs(r.call.at - face);
          if (d > SLACK) out.marks.bad_time.push(
            {t:(m.textContent||'').trim().slice(0,40), face:face, at:r.call.at, d:+d.toFixed(2)});
        }
      } else if (r.toast) {
        out.marks.refused++;
        if (out.marks.refusals.length < 6) out.marks.refusals.push(r.toast.slice(0,70));
      } else if (r.mut) {
        out.marks.acted++;
      } else {
        out.marks.dead.push((m.className||'') + ' | ' + (m.textContent||'').trim().slice(0,40));
      }
    });
  }

  function label(b){
    var id = b.id ? '#'+b.id : '';
    var cls = (b.className||'').trim().split(/\s+/).slice(0,2).join('.');
    var txt = (b.textContent||'').trim().replace(/\s+/g,' ').slice(0,28);
    return (id || ('.'+cls) || 'button') + (txt ? ' «'+txt+'»' : '');
  }

  setTimeout(function(){
    var out = {yt_order: R.ytOrder, errors: [], lanes: null,
               marks:{total:0, played:0, refused:0, acted:0, dead:[], bad_time:[],
                      errors:[], refusals:[]},
               controls:{total:0, dead:[]},
               overflow:null, rendered:0,
               buttons_at_start: all('button').length};

    try { out.lanes = V.langs.map(function(l){
            return {id:l.id, name:l.name||null, speaker:l.speaker||null, sim:!!l.sim}; }); }
    catch(e) { out.lanes = null; }

    out.rendered = all('.mk, .pl, .row, .verse, tr').length;

    // A play control is whatever plays, not whatever is called .mk. The
    // anukramaṇikā and the witness build theirs with `el('button')` and no
    // stable class, so a selector registry would simply have missed them --
    // which it did, on the first run of this file.
    var PLAY = 'button.mk, button.pl, button.playall, .marks button,' +
               ' .lane button, .lanes button, .row button, .part button';
    sweepMarks(out, PLAY);
    // The chapters come from the data, never from a guess. Varāha, Garuḍa and
    // Viṣṇu are scoped to the chapters actually walked, so 1, 2, 3 need not
    // exist -- and showChapter() does `esc(V.chapters[ch].name)` with no guard,
    // so a guessed number throws rather than returning empty. That was this
    // harness's own first "finding".
    var chaps = [];
    try { chaps = Object.keys(V.chapters).map(Number)
                    .filter(function(n){ return !isNaN(n); }); } catch(e) {}
    out.chapters = chaps.length;
    if (typeof showChapter === 'function' && chaps.length) {
      chaps.slice(0, 3).forEach(function(ch){
        try { showChapter(ch); } catch(e) { out.errors.push('showChapter(' + ch + '): ' + e.message); return; }
        sweepMarks(out, PLAY);       // showChapter rebuilds the rows
      });
    }
    var seen = {};
    all(PLAY).forEach(function(b){ seen[label(b)] = 1; });

    // Everything else. After the marks, because a panel toggle can hide the
    // rows they live in.
    //
    // LIVE, NOT A SNAPSHOT. The first version took all('button') once and
    // pressed each in turn. On the Smṛtimuktāphalam edition a click re-renders
    // the pane, so every later button in the snapshot was detached by the time
    // its turn came -- and a click on a detached node never bubbles to the
    // delegated listener on #pane. 194 of smp6's controls reported dead; all
    // 194 were detached; none was dead. So the buttons are re-read after every
    // press, deduplicated by label, and a detached one is never pressed.
    //
    // THE KEY IS LABEL + POSITION, not label alone. A label-only key collapsed
    // every verse's identical ▶ button into one press, and the suite caught
    // it: played counts fell on seven atlases with no page changed. The k-th
    // connected button bearing a given label is the same control across a
    // re-render, so it is the key that survives both failure modes.
    var probed = {}, presses = 0, CAP = 6000;
    var startSet = (function(){ var bs = all('button'), nth = {}, ks = [];
      bs.forEach(function(x){ if (!x.isConnected || x.disabled) return;
        var L = label(x); nth[L] = (nth[L] || 0) + 1; ks.push(L + '#' + nth[L]); });
      return ks; })();
    function nextButton(){
      var bs = all('button'), nth = {};
      for (var i = 0; i < bs.length; i++) {
        var b = bs[i];
        if (!b.isConnected) continue;
        var L = label(b), k = nth[L] = (nth[L] || 0) + 1, key = L + '#' + k;
        if (b.disabled || seen[L] || probed[key]) continue;
        return {el: b, key: key};
      }
      return null;
    }
    var nb, b;
    while (presses < CAP && (nb = nextButton())) {
      b = nb.el; probed[nb.key] = 1; presses++;
      out.controls.total++;
      var r = probe(b);
      if (r.call) { out.marks.total++; out.marks.played++;   // it played: it was a play control
        var face = faceSeconds(b.textContent);
        if (face !== null && r.call.at != null && r.call.fn !== 'playVideo'
            && r.call.fn !== 'pauseVideo') {
          var d = Math.abs(r.call.at - face);
          if (d > SLACK) out.marks.bad_time.push(
            {t:(b.textContent||'').trim().slice(0,40), face:face, at:r.call.at, d:+d.toFixed(2)});
        }
        continue; }
      if (!r.toast && !r.mut && !r.err) out.controls.dead.push(label(b));
    }
    out.controls.capped = presses >= CAP;
    // COVERAGE, reported rather than assumed: every button still on the page
    // that the sweep never pressed. A count that falls is only a finding if
    // this is zero -- otherwise it may be the sweep that missed, not the page.
    out.controls.unreached = (function(){
      var bs = all('button'), nth = {}, miss = [];
      bs.forEach(function(x){
        if (!x.isConnected || x.disabled) return;
        var L = label(x), k = nth[L] = (nth[L] || 0) + 1;
        if (!seen[L] && !probed[L + '#' + k]) miss.push(L + '#' + k);
      });
      return {n: miss.length, e: miss.slice(0, 5)};
    })();
    // Present when the sweep began, never pressed, gone by the end: removed by
    // an earlier press. Not reachable in the state the sweep drove the page to,
    // but reachable from a fresh load -- so this is a coverage gap, and it is
    // printed, never folded silently into a pass.
    out.controls.hidden_by_sweep = startSet.filter(function(k){
      return !probed[k] && !seen[k.replace(/#\d+$/, '')]; }).length;

    var de = document.documentElement;
    var endOverflow = de.scrollWidth - de.clientWidth;
    out.overflow = Math.max(endOverflow, R.worstOverflow);
    out.overflow_after = endOverflow >= R.worstOverflow ? '(page as left)' : R.worstAt;
    out.viewport = de.clientWidth;
    out.errors = out.errors.concat(R.errors).slice(0, 12);

    var pre = document.createElement('pre');
    pre.id = '__regress';
    pre.textContent = btoa(unescape(encodeURIComponent(JSON.stringify(out))));
    document.body.appendChild(pre);
  }, 1800);
})();
</script>
"""


def serve(root):
    """A quiet http.server on a free port, in a daemon thread."""
    s = socket.socket(); s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]; s.close()

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=root, **kw)

        def log_message(self, *a):
            pass

    httpd = http.server.ThreadingHTTPServer(('127.0.0.1', port), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, port


def instrument(src, dst):
    html = open(src, encoding='utf-8').read()
    probe = PROBE.replace('SLACK', repr(TIME_SLACK))
    if '<head>' in html:
        html = html.replace('<head>', '<head>\n' + STUB, 1)
    else:
        html = STUB + html
    if '</body>' in html:
        html = html.replace('</body>', probe + '\n</body>', 1)
    else:
        html = html + probe
    open(dst, 'w', encoding='utf-8').write(html)


PHONE_HOST = """<!doctype html><body style="margin:0">
<iframe id="f" src="%s" style="width:%dpx;height:780px;border:0;display:block"></iframe>
<script>
(function poll(){
  try {
    var d = document.getElementById('f').contentDocument;
    var p = d && d.getElementById('__regress');
    if (p) { var q = document.createElement('pre'); q.id = '__regress';
             q.textContent = p.textContent; document.body.appendChild(q); return; }
  } catch (e) {}
  setTimeout(poll, 100);
})();
</script>"""


def phone_host(root, name):
    host = '__phone__' + name
    open(os.path.join(root, host), 'w', encoding='utf-8').write(PHONE_HOST % (name, PHONE_WIDTH))
    return host


def run_page(port, name, width, height=900, budget=25000):
    url = 'http://127.0.0.1:%d/%s' % (port, name)
    cmd = [CHROME, '--headless', '--disable-gpu', '--no-sandbox',
           '--hide-scrollbars', '--disable-lcd-text',
           '--window-size=%d,%d' % (width, height),
           '--virtual-time-budget=%d' % budget,
           '--host-resolver-rules=MAP www.youtube.com 127.0.0.1,'
           'MAP youtube.com 127.0.0.1,MAP fonts.googleapis.com 127.0.0.1,'
           'MAP fonts.gstatic.com 127.0.0.1,MAP cdnjs.cloudflare.com 127.0.0.1',
           '--dump-dom', url]
    try:
        dom = subprocess.run(cmd, capture_output=True, text=True, timeout=180).stdout
    except subprocess.TimeoutExpired:
        return {'fatal': 'chrome timed out'}
    m = re.search(r'<pre id="__regress">([A-Za-z0-9+/=]+)</pre>', dom)
    if not m:
        # The prober never ran: the page threw before it could report.
        err = re.search(r'Uncaught[^<\n]{0,160}', dom)
        return {'fatal': 'no result from the page' + (' — ' + err.group(0) if err else '')}
    return json.loads(base64.b64decode(m.group(1)).decode('utf-8'))


def compare(name, now, was):
    """Regressions only. Growth is not a failure; loss and silence are."""
    bad = []
    if now.get('fatal'):
        return ['%s: %s' % (name, now['fatal'])]
    if now.get('errors'):
        bad.append('%s: %d JS error(s): %s' % (name, len(now['errors']), now['errors'][0]))
    if now.get('yt_order') is False:
        bad.append('%s: iframe_api appended BEFORE onYouTubeIframeAPIReady was '
                   'defined — the page will render and every row will be silent' % name)
    if now['marks']['dead']:
        bad.append('%s: %d mark(s) press to nothing — no play, no refusal, no change: %s'
                   % (name, len(now['marks']['dead']), now['marks']['dead'][0]))
    for b in now['marks']['bad_time']:
        bad.append('%s: mark «%s» prints %ds but seeks to %.1fs (%.1fs out)'
                   % (name, b['t'], b['face'], b['at'], b['d']))
    if now['marks']['errors']:
        bad.append('%s: %d mark(s) threw on click: %s'
                   % (name, len(now['marks']['errors']), now['marks']['errors'][0]))
    if not was:
        return bad
    if now['marks']['played'] < was['marks']['played']:
        bad.append('%s: %d marks played, baseline %d'
                   % (name, now['marks']['played'], was['marks']['played']))
    new_dead = set(now['controls']['dead']) - set(was['controls']['dead'])
    if new_dead:
        bad.append('%s: control(s) newly dead: %s' % (name, ', '.join(sorted(new_dead))))
    lanes_now = [l['id'] for l in (now.get('lanes') or [])]
    lanes_was = [l['id'] for l in (was.get('lanes') or [])]
    gone = [l for l in lanes_was if l not in lanes_now]
    if gone:
        bad.append('%s: lane(s) gone: %s' % (name, ', '.join(gone)))
    sim = [l['id'] for l in (now.get('lanes') or []) if l.get('sim')]
    if sim:
        bad.append('%s: simulated lane(s) published: %s' % (name, ', '.join(sim)))
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--page', action='append', help='one page; repeatable')
    ap.add_argument('--update', action='store_true', help='rewrite the baseline')
    ap.add_argument('--keep', action='store_true', help='keep the scratch copies')
    ap.add_argument('--no-mobile', action='store_true')
    ap.add_argument('--repo', default=HERE, help='deployment repo to drive (default: this one)')
    a = ap.parse_args()
    repo = os.path.abspath(a.repo)
    BASELINE = baseline_path(repo)

    if not CHROME:
        sys.exit('no chrome found — install google-chrome or chromium')

    # index.html is a real page on a site whose landing page is its content (the
    # anukramaṇikā), so it is only skipped where it is a hand-written front door.
    skip_index = os.path.samefile(repo, HERE)
    pages = a.page or sorted(f for f in os.listdir(repo)
                             if f.endswith('.html') and not (skip_index and f == 'index.html'))
    root = tempfile.mkdtemp(prefix='atlas-regress-')
    for d in os.listdir(repo):
        src = os.path.join(repo, d)
        if os.path.isdir(src) and not d.startswith('.') and d not in ('baselines', '__pycache__'):
            os.symlink(src, os.path.join(root, d))
    for p in pages:
        instrument(os.path.join(repo, p), os.path.join(root, p))

    httpd, port = serve(root)
    base = json.load(open(BASELINE)) if os.path.exists(BASELINE) else {}
    was_v = (base.get('_meta') or {}).get('harness_version', 1) if base else None
    if base and was_v != HARNESS_VERSION and not a.update:
        print('baseline %s was taken with harness v%s; this is v%s.'
              % (os.path.relpath(BASELINE, HERE), was_v, HARNESS_VERSION))
        print('Counts from two instruments are not a comparison. Check that no page')
        print('changed (git status in the repo), then rerun with --update.')
        return 2
    out, failures = {}, []

    for p in pages:
        r = run_page(port, p, 1280)
        if not a.no_mobile and not r.get('fatal'):
            m = run_page(port, phone_host(root, p), 1280, height=900)
            r['overflow_390'] = m.get('overflow')
            r['overflow_390_after'] = m.get('overflow_after')
            r['phone_viewport'] = m.get('viewport')
            if m.get('fatal'):
                failures.append('%s: phone pass: %s' % (p, m['fatal']))
            elif not isinstance(m.get('viewport'), int) or m['viewport'] > PHONE_WIDTH:
                failures.append('%s: the phone pass ran at %spx, not %dpx — its overflow '
                                'reading means nothing' % (p, m.get('viewport'), PHONE_WIDTH))
            elif isinstance(r['overflow_390'], (int, float)) and r['overflow_390'] > 1:
                failures.append('%s: %dpx of horizontal overflow at %dpx, after pressing «%s»'
                                % (p, r['overflow_390'], PHONE_WIDTH, r.get('overflow_390_after')))
        out[p] = r
        failures += compare(p, r, base.get(p))
        if r.get('fatal'):
            print('  %-30s FATAL  %s' % (p, r['fatal']))
            continue
        mk = r['marks']
        print('  %-30s %3d lanes·marks %4d  played %4d  refused %3d  dead %d  '
              'controls %3d (dead %d, unreached %s)  overflow %s'
              % (p, len(r.get('lanes') or []), mk['total'], mk['played'],
                 mk['refused'], len(mk['dead']), r['controls']['total'],
                 len(r['controls']['dead']),
                 '%s/%s' % ((r['controls'].get('unreached') or {}).get('n', '?'),
                            r['controls'].get('hidden_by_sweep', '?')),
                 r.get('overflow_390', '-')))

    httpd.shutdown()
    if not a.keep:
        shutil.rmtree(root, ignore_errors=True)
    else:
        print('\nscratch kept at', root)

    if a.update:
        # A BASELINE MUST NEVER ENCODE A FAILURE. --update used to write the file
        # and return before the failures were printed, so a run with an
        # overflow or a dead control could become the reference it is judged by.
        if failures:
            print()
            for f in failures:
                print('FAIL  ' + f)
            print('\nnot written: fix these first — a baseline is what passing looks like')
            return 1
        os.makedirs(os.path.dirname(BASELINE), exist_ok=True)
        # MERGE when only some pages ran. `--update --page x` once rewrote the
        # whole file with that one page, silently deleting every other page's
        # baseline; the next full run would then have "passed" those pages
        # against nothing. A full run still replaces the file outright, so a
        # page that no longer exists does not linger in it.
        if a.page and base and (base.get('_meta') or {}).get('harness_version') == HARNESS_VERSION:
            merged = {k: v for k, v in base.items() if k != '_meta'}
            merged.update(out)
            out = merged
        elif a.page:
            print('partial --update needs an existing v%d baseline to merge into; '
                  'run a full --update first' % HARNESS_VERSION)
            return 2
        out['_meta'] = {'harness_version': HARNESS_VERSION, 'repo': os.path.basename(repo)}
        json.dump(out, open(BASELINE, 'w'), indent=1, sort_keys=True)
        print('\nbaseline written:', BASELINE)
        return 0

    print()
    if failures:
        for f in failures:
            print('FAIL  ' + f)
        return 1
    print('OK — no regression against the baseline')
    return 0


if __name__ == '__main__':
    sys.exit(main())
