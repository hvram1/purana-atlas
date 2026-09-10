#!/usr/bin/env python3
"""What the four repositories are for, and whether the site is behind them.

Written to be read by an agent at the start of a session, through a SessionStart
hook in each of the four repos:

    {"hooks": {"SessionStart": [{"hooks": [{"type": "command",
      "command": "/home/wipro/projects/purana-atlas/atlas_context.py --hook"}]}]}}

    ./atlas_context.py           the text, for a human
    ./atlas_context.py --hook    the same text wrapped as hook JSON

WHY A HOOK, AND WHAT BELONGS IN ONE
-----------------------------------
Doctrine does not belong here. "Everything serves the atlas" is a constant, and
a constant paid for on every session start is waste -- it belongs in each repo's
AGENTS.md, written once. What a hook is for is the part that CHANGES and that
nobody will think to go and look up: whether the work in the repo you just
opened has actually reached the published site.

The four-line map below is the one piece of constant here, and it earns its
place by being the thing that makes the state readable at all -- a stale
`kartika_4lang.json` means nothing until you know which repo builds it.

WHY IT NEVER FAILS
------------------
A hook that errors is noise at the top of every session, and a hook that blocks
is worse. Every lookup here is wrapped: a missing repo, an unreadable stats.json
or an unmounted drive costs one line saying so, and the rest still prints. This
script exits 0 whatever happens.

WHY IT COMPARES MTIMES AND NOTHING ELSE
---------------------------------------
`refresh.py --check` already verifies that what is published will render -- it
parses every file and checks the container shapes the pages index into. That is
the deeper check and it is the one to run before committing. It cannot answer
this question, because a file that is stale renders perfectly. So the two are
complementary: refresh.py asks "will it work", this asks "is it current".

The tables are imported from refresh.py rather than restated. It owns which
page comes from which repo, and a second copy here would go quietly wrong the
first time a page moved.
"""
import argparse
import importlib.util
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))

MAP = """PURĀṆA ATLAS — the deliverable the other three repositories serve
  purana-atlas/      the published site. A DEPLOYMENT: nothing here is authored
                     by hand except index.html, README.md and docs/.
  audio-ingest/      Measurement — recordings to verses on the clock. Also
                     authors the two pages that have no edition behind them.
  dharmasastra-gcp/  workbench/ = Kośa + the atlas builders; smp/ = the
                     Smṛtimuktāphalam digest.
  sharadapeetham/    the Text — index.db, the corpora, shloka_setu.
  The loop is: rebuild in the repo that owns the inputs, ./refresh.py here,
  commit here. A page's source follows its inputs, not the page beside it."""


def load_refresh():
    """refresh.py owns the page -> source mapping. Import it, don't copy it.

    `dont_write_bytecode` is not tidiness: without it the first session start
    drops a __pycache__/ into a repo whose whole contract is that everything in
    it was published by refresh.py, and it shows up as an untracked file in
    every `git status` after.
    """
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location(
        'refresh', os.path.join(HERE, 'refresh.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def pairs(r):
    """(deployed, source) for every file refresh.py publishes."""
    out = []
    for page, four, sub in r.ATLASES:
        out.append((os.path.join(HERE, page), os.path.join(r.SRC, page)))
        for name in (four, sub):
            out.append((os.path.join(HERE, 'data', name),
                        os.path.join(r.SRC, 'data', name)))
    for page, data in (r.WITNESS, r.ANUK):
        out.append((os.path.join(HERE, page),
                    os.path.join(r.INGEST, r.WITNESS_SRC[0], page)))
        out.append((os.path.join(HERE, 'data', data),
                    os.path.join(r.INGEST, r.WITNESS_SRC[1], data)))
    return out


def stale(r):
    """Deployed files whose source is newer. A day of slack: refresh.py copies
    with copyfile, which does not preserve mtime, so the deployed file is
    always a little younger than its source and a strict > would cry wolf."""
    late, missing = [], []
    for dst, src in pairs(r):
        if not os.path.exists(src):
            missing.append(os.path.relpath(src, os.path.dirname(HERE)))
            continue
        if not os.path.exists(dst):
            late.append((os.path.basename(dst), 'not published'))
            continue
        gap = os.path.getmtime(src) - os.path.getmtime(dst)
        if gap > 86400:
            late.append((os.path.basename(dst),
                         'source %.0f days newer' % (gap / 86400.0)))
    return late, missing


def published():
    """The headline figures, from the file index.html itself reads."""
    with open(os.path.join(HERE, 'data', 'stats.json')) as f:
        s = json.load(f)
    lines = ['published (data/stats.json, built %s)' % s.get('built', '?')]
    for key, a in (s.get('atlases') or {}).items():
        lines.append('  %-11s %5d verses  %5.1f%% reached  %d lane%s, %d recordings'
                     % (key, a['verses'], a['reached_pct'], a['real_lanes'],
                        '' if a['real_lanes'] == 1 else 's', a['recordings']))
    # The two edition-less pages. They are top-level keys, not atlases, because
    # they measure something else: `reached` needs a printed text to be reached.
    w = s.get('witness') or {}
    if w:
        lines.append('  tulakaveri  no edition — %d correspondences, %d '
                     'identical, %d recordings, %.1f h  (two witnesses)'
                     % (w.get('shared', 0), w.get('identical', 0),
                        w.get('recordings', 0), w.get('hours', 0.0)))
    k = s.get('anukramanika') or {}
    if k:
        lines.append('  shravana    no edition — %d chanted passages (%.2f h) '
                     'of %d recordings, %d verbatim in the index'
                     % (k.get('chant', 0), k.get('chant_hours', 0.0),
                        k.get('recordings', 0), k.get('quoted', 0)))
    return lines


def uncommitted():
    """Work sitting in the deployment that has not been pushed is invisible."""
    st = subprocess.run(['git', '-C', HERE, 'status', '--porcelain'],
                        capture_output=True, text=True, timeout=10)
    n = len([l for l in st.stdout.splitlines() if l.strip()])
    ahead = subprocess.run(
        ['git', '-C', HERE, 'rev-list', '--count', '@{u}..HEAD'],
        capture_output=True, text=True, timeout=10).stdout.strip()
    bits = []
    if n:
        bits.append('%d uncommitted file%s' % (n, '' if n == 1 else 's'))
    if ahead.isdigit() and int(ahead):
        bits.append('%s commit(s) unpushed' % ahead)
    return '  purana-atlas: ' + ', '.join(bits) if bits else None


def report():
    out = [MAP, '']
    try:
        r = load_refresh()
    except Exception as e:                                   # noqa: BLE001
        return '\n'.join(out + ['  (refresh.py unreadable: %s)' % e])

    try:
        out += published()
    except Exception as e:                                   # noqa: BLE001
        out.append('  (stats.json unreadable: %s)' % e)

    try:
        late, missing = stale(r)
        out.append('')
        if late:
            out.append('STALE — %d published file(s) behind their source; '
                       'run ./refresh.py in purana-atlas' % len(late))
            for name, why in late:
                out.append('  %-34s %s' % (name, why))
        else:
            out.append('the published site is current with its sources')
        if missing:
            out.append('  sources not found (repo moved, or never built): %s'
                       % ', '.join(missing[:4]))
    except Exception as e:                                   # noqa: BLE001
        out.append('  (staleness check failed: %s)' % e)

    try:
        u = uncommitted()
        if u:
            out.append(u)
    except Exception:                                        # noqa: BLE001
        pass
    return '\n'.join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--hook', action='store_true',
                    help='emit SessionStart hook JSON instead of plain text')
    a = ap.parse_args()
    t0 = time.time()
    try:
        text = report()
    except Exception as e:                                   # noqa: BLE001
        text = 'atlas_context.py failed: %s' % e
    if a.hook:
        print(json.dumps({'hookSpecificOutput': {
            'hookEventName': 'SessionStart', 'additionalContext': text}}))
    else:
        print(text)
        print('\n(%.2fs)' % (time.time() - t0), file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
