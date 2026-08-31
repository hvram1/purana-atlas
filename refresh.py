#!/usr/bin/env python3
"""Publish the atlas pages and their data from the workbench into this repo.

This repository is a *deployment*, not a source tree. Nothing here is authored
by hand except index.html, README.md and docs/. Everything else is produced in
the workbench and copied in by this script:

    dharmasastra-gcp/workbench/virata-atlas.html   + data/virata_*.json
    dharmasastra-gcp/workbench/kartika-atlas.html  + data/kartika_*.json
    audio-ingest/tulakaveri-witness.html           + data/tulakaveri_*.json

The atlases come from the workbench because that is where the corpus and the
entity substrate they read live. The Tulā Kāverī page comes from audio-ingest
because that is where ITS inputs live -- the cross-series matches, the forced
alignments, the colophons -- and it reads nothing from the workbench at all.
The source of a page follows its inputs, not the habit of the page beside it.

So the loop is: rebuild there, refresh here, commit here.

    workbench$  myenv/bin/python scripts/build_kartika_audio.py
    purana-atlas$ ./refresh.py
    purana-atlas$ git commit -am "refresh atlases" && git push

Each page fetches exactly two JSON files by *relative* path, so the whole site
is six files and works from any subdirectory -- including a GitHub Pages
project site at https://<user>.github.io/<repo>/. The only off-site request
either page makes is https://www.youtube.com/iframe_api.

WHY THIS SCRIPT VERIFIES INSTEAD OF JUST COPYING
------------------------------------------------
The container shapes in the substrate are load-bearing: the pages do
`A.cards[id]` on dicts and `A.events.filter(...)` on lists. Ship a substrate
whose `events` is `{}` and every visitor sees "Could not load data" -- a broken
page, not an empty layer, and nothing in a copy would have told you. So each
file is parsed and shape-checked before it is allowed to land, and the script
exits non-zero rather than publishing something that will not render.

    ./refresh.py                 copy, verify, report
    ./refresh.py --check         verify what is already here; copy nothing
    ./refresh.py --with-sim      keep the simulated Virāṭa lanes in the site

THE SIMULATED LANES ARE DROPPED BY DEFAULT
------------------------------------------
The Virāṭa atlas carries four lanes and only Tamil is a real recording; the
Kannada, Telugu and Bengali lanes are *invented timings*, built so the
interface could be judged before such recordings existed. The page marks them
`sim` and refuses to play them, which is honest enough for a workbench.

It is not honest enough for a public URL, and the reason is visual rather than
ethical. On adhyāya 1 the Tamil lane is empty -- Musiri does not expound those
verses -- while all three invented lanes show full coloured bars and
plausible timestamps. A first-time visitor's opening screen is therefore three
fabricated recordings looking complete beside the one real recording looking
absent, with an 8px grey badge as the only correction. So the published site
ships the real lane alone, where the same screen reads "not expounded" and the
next verse shows twenty-two genuine timestamps.

Pass --with-sim to publish the mockup anyway -- it is a fair illustration of
what docs/ is asking to fund, and that is an argument for putting it in the
pitch as a labelled screenshot rather than live on the page.
"""

import argparse
import datetime
import gzip
import json
import os
import re
import shutil
from html.parser import HTMLParser
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.environ.get("ATLAS_SRC",
                     "/home/wipro/projects/dharmasastra-gcp/workbench")
INGEST = os.environ.get("ATLAS_INGEST", "/home/wipro/projects/audio-ingest")

# (page, 4lang file, substrate file). The page names the JSON in its own
# fetch() calls; these must agree, and check_fetches() below proves they do
# rather than trusting this list.
ATLASES = [
    ("virata-atlas.html", "virata_4lang.json", "virata_atlas_substrate.json"),
    ("kartika-atlas.html", "kartika_4lang.json", "kartika_atlas_substrate.json"),
    ("adhyatma-atlas.html", "adhyatma_4lang.json",
     "adhyatma_atlas_substrate.json"),
]

# The Tulā Kāverī page is not an atlas and deliberately does not have a
# substrate: there is no printed edition for one to be the authority over. It
# ships one file, whose rows are correspondences between two RECORDINGS, so it
# gets its own shape check further down rather than being bent into ATLASES.
# It also comes from a different repo -- see the header -- so it carries where
# each half is found rather than inheriting the ATLASES layout.
WITNESS = ("tulakaveri-witness.html", "tulakaveri_witness.json")
WITNESS_SRC = ("", os.path.join("build", "witness"))   # page dir, data dir

# Shape contract of the substrate. Getting one of these wrong does not degrade
# the page, it blanks it.
DICTS = ("text", "chapters", "cards", "ann", "cast")
LISTS = ("kin", "spouse", "sib", "events")


def fail(msg):
    print("  FAIL  " + msg)
    return 1


def check_fetches(page_path, expect):
    """The page must fetch exactly the files we are shipping, relatively.

    An absolute '/data/...' would work at a user-site root and 404 under
    /<repo>/, which is the one deployment difference a local test misses.
    """
    html = open(page_path, encoding="utf-8").read()
    bad = 0
    # A page of Devanagari with no declared charset renders as mojibake on any
    # server that serves text/html bare. This is not hypothetical -- index.html
    # shipped without it and the verse titles came out as "à¤µà¤¿à¤°à¤¾à¤Ÿ".
    if 'charset="utf-8"' not in html.lower() and "charset=utf-8" not in html.lower():
        bad += fail("%s declares no charset; Devanagari will mojibake"
                    % os.path.basename(page_path))
    for name in expect:
        if "fetch('data/%s')" % name not in html:
            bad += fail("%s does not fetch data/%s the way we ship it"
                        % (os.path.basename(page_path), name))
    if "fetch('/" in html or 'fetch("/' in html:
        bad += fail("%s fetches an absolute path; it will 404 under /<repo>/"
                    % os.path.basename(page_path))
    return bad


# `url(...)` and `@import` inside CSS, which carry no `=` and so are invisible
# to any check written against tag attributes alone.
CSS_URL = re.compile(r'''(?:url\(|@import\s+)\s*['"]?\s*(https?://[^)'"\s]+)''')


def check_selfcontained(path):
    """No page may *load* from a host we do not control, bar the YouTube API.

    A webfont or stylesheet pulled from a CDN turns a page that works into a
    page that works until someone else's certificate expires -- and on a
    proposal being read by a reviewer offline, into a page that never worked.

    A hyperlink in prose is not that, and the distinction is the whole point of
    this site: a citation SHOULD point at the thing it cites. An <a href> to
    another site loads nothing, breaks nothing offline, and is the one outbound
    reference a document about checkable citations is obliged to make. So the
    rule is by kind, not by string -- `src` anywhere and `href` on anything that
    is not an anchor must be local; an anchor may point where it likes.

    Outbound links are printed rather than passed over in silence, because a
    page quietly acquiring them is worth seeing on every run.
    """
    class Scan(HTMLParser):
        def __init__(self):
            HTMLParser.__init__(self)
            self.loads = set()
            self.links = set()
            self.in_style = False

        def handle_starttag(self, tag, attrs):
            if tag == "style":
                self.in_style = True
            for k, v in attrs:
                if v and k == "style":
                    self.loads.update(CSS_URL.findall(v))
                if not v or not v.lower().startswith(("http://", "https://")):
                    continue
                if k == "href" and tag == "a":
                    self.links.add(v)
                elif k in ("src", "href", "data", "poster"):
                    self.loads.add(v)

        def handle_endtag(self, tag):
            if tag == "style":
                self.in_style = False

        def handle_data(self, data):
            # A @font-face `src:url(https://fonts.gstatic.com/...)` lives in CSS
            # text, not in a tag attribute, so the tag walk above cannot see it.
            # That is the exact failure this whole check exists to prevent -- the
            # README promises the Devanagari is self-hosted -- and it went
            # uncaught for as long as the check matched `src=` with an equals
            # sign. Verified by breaking it.
            if self.in_style:
                self.loads.update(CSS_URL.findall(data))

    scan = Scan()
    scan.feed(open(path, encoding="utf-8").read())
    outside = {u for u in scan.loads if "youtube.com/iframe_api" not in u}
    if outside:
        return (fail("%s loads from outside this site: %s"
                     % (os.path.basename(path), sorted(outside)[:2])),
                [])
    return 0, sorted(scan.links)


def check_4lang(path):
    d = json.load(open(path, encoding="utf-8"))
    bad = 0
    for k in ("langs", "ta_episodes", "verses", "chapters"):
        if k not in d:
            bad += fail("%s has no %r" % (os.path.basename(path), k))
    for l in d.get("langs", []):
        if l.get("sim") and l.get("nourl"):
            bad += fail("lane %s is both simulated and unuploaded -- those are "
                        "different claims and the page says them differently"
                        % l.get("id"))
    # An occurrence in a REAL lane must have an episode row, because that row
    # is the only place a URL lives: without it the verse reads "not uploaded
    # yet" forever, however many videos go up. Simulated lanes are exempt --
    # they have no episodes by construction, which is what makes them
    # unplayable rather than broken.
    eps = {e["id"] for e in d.get("ta_episodes", [])}
    sim = {l["id"] for l in d.get("langs", []) if l.get("sim")}
    orphan = {o["ep"] for v in d.get("verses", {}).values()
              for lid, rec in (v.get("lang") or {}).items() if lid not in sim
              for o in rec.get("occ", []) if o["ep"] not in eps}
    if orphan:
        bad += fail("real occurrences reference episodes with no row: %s -- "
                    "those verses can never find a URL" % sorted(orphan)[:4])
    return bad, d


def check_substrate(path):
    d = json.load(open(path, encoding="utf-8"))
    bad = 0
    if not d.get("text"):
        bad += fail("%s has no text -- it is the authority for which verses "
                    "exist" % os.path.basename(path))
    for k in DICTS:
        if k in d and not isinstance(d[k], dict):
            bad += fail("%s.%s must be a dict; a list renders as 'Could not "
                        "load data'" % (os.path.basename(path), k))
    for k in LISTS:
        if k in d and not isinstance(d[k], list):
            bad += fail("%s.%s must be a list; `.filter is not a function` "
                        "blanks the page" % (os.path.basename(path), k))
    # The DCS layer, when a substrate carries one. The page does `A.dcs.v[ref]`
    # and then indexes `h.p` and `h.a` positionally, so the container kinds are
    # load-bearing the same way the ones above are. An anvaya that is not a
    # permutation of that hemistich's own padas is the one error the data can
    # carry that renders as plausible Sanskrit rather than as a broken page.
    dcs = d.get("dcs")
    if dcs is not None:
        if not isinstance(dcs.get("v"), dict):
            bad += fail("%s.dcs.v must be a dict keyed by verse ref"
                        % os.path.basename(path))
        else:
            if not dcs.get("anvaya_derived"):
                bad += fail("%s.dcs does not declare the anvaya derived; the "
                            "page badges it from this flag"
                            % os.path.basename(path))
            for ref, hs in dcs["v"].items():
                for h in hs:
                    n = len(h.get("p") or ())
                    a = h.get("a")
                    if a is None:
                        continue
                    if sorted(a) != list(range(n)):
                        bad += fail("%s.dcs.v[%s] anvaya is not a permutation "
                                    "of its padas" % (os.path.basename(path),
                                                      ref))
                        break
    return bad, d


def check_witness(path):
    """The witness page blanks differently from an atlas, so it checks so.

    An atlas that loses a container renders nothing and the visitor sees it.
    This page's failure is quieter and worse: a row whose episode has no video
    id still renders, still prints its Sanskrit, and offers a play button that
    does nothing when pressed. The whole claim of the page is that both
    recordings can be heard, so a row that cannot be heard is not a degraded
    row, it is a false one. Hence the id check, per row, per side.
    """
    d = json.load(open(path, encoding="utf-8"))
    bad = 0
    rows = d.get("rows")
    if not isinstance(rows, list) or not rows:
        return fail("%s has no rows" % os.path.basename(path)), {}
    eps = d.get("episodes") or {}
    if not isinstance(eps, dict) or not eps:
        return fail("%s has no episodes to play" % os.path.basename(path)), {}
    silent, malformed = set(), 0
    for r in rows:
        for side in ("tk", "dsb"):
            v = r.get(side) or {}
            if not all(k in v for k in ("ep", "t", "e", "text")):
                malformed += 1
                continue
            if v["e"] <= v["t"]:
                malformed += 1
            e = eps.get(v["ep"]) or {}
            if not e.get("yt"):
                silent.add(v["ep"])
    if malformed:
        bad += fail("%s: %d row sides are malformed or end before they start"
                    % (os.path.basename(path), malformed))
    if silent:
        bad += fail("%s: no video id for %s -- those rows would offer a play "
                    "button that does nothing"
                    % (os.path.basename(path), ", ".join(sorted(silent))))
    st = d.get("stats") or {}
    if st.get("shared") != len(rows):
        bad += fail("%s: stats say %s correspondences, rows say %d"
                    % (os.path.basename(path), st.get("shared"), len(rows)))
    if st.get("in_index") != 0:
        bad += fail("%s: in_index is %r -- the page's whole claim is that it "
                    "is nought" % (os.path.basename(path), st.get("in_index")))
    return bad, d


def strip_sim(four):
    """Remove the simulated lanes, and every occurrence that belonged to them."""
    sim = {l["id"] for l in four.get("langs", []) if l.get("sim")}
    if not sim:
        return four, sim
    four["langs"] = [l for l in four["langs"] if not l.get("sim")]
    for v in four.get("verses", {}).values():
        for lid in list((v.get("lang") or {})):
            if lid in sim:
                del v["lang"][lid]
    # A verse with no lane left is still a verse of the text; the substrate,
    # not this file, decides what exists, so drop only the empty lane maps.
    four["verses"] = {r: v for r, v in four["verses"].items() if v.get("lang")}
    four["ta_episodes"] = [e for e in four.get("ta_episodes", [])
                           if e.get("lane") not in sim]
    return four, sim


SITE_URL_FILE = os.path.join(HERE, ".site-url")
PLACEHOLDER = "SITE_URL"


def set_site_url(url, check_only):
    """Point the docs at the live site, once, and remember where that is.

    The pitch in docs/ is read on github.com, where a relative link to
    ../virata-atlas.html resolves to a source blob rather than to the page. So
    the links are absolute, and the base URL is substituted here rather than
    typed into the prose -- typed once, it would be wrong the first time the
    repo is renamed and nobody would look.

    Returns a failure count: an unsubstituted placeholder is a broken link in
    the document we are asking people to read, so it is reported, but it does
    not stop a deploy that is otherwise fine.
    """
    if url:
        url = url.rstrip("/")
        with open(SITE_URL_FILE, "w", encoding="utf-8") as f:
            f.write(url + "\n")
    elif os.path.exists(SITE_URL_FILE):
        url = open(SITE_URL_FILE, encoding="utf-8").read().strip()

    docs = os.path.join(HERE, "docs")
    left = 0
    for name in sorted(os.listdir(docs)) if os.path.isdir(docs) else []:
        if not name.endswith(".md"):
            continue
        path = os.path.join(docs, name)
        text = open(path, encoding="utf-8").read()
        if url and PLACEHOLDER in text and not check_only:
            open(path, "w", encoding="utf-8").write(
                text.replace(PLACEHOLDER, url))
            print("docs/%s -> %s" % (name, url))
        elif PLACEHOLDER in text:
            left += 1
            print("  WARN  docs/%s still has %s in its links -- pass "
                  "--site-url once" % (name, PLACEHOLDER))
    # A warning, not a failure: an unlinked pitch is a worse document, not an
    # unpublishable site.
    return 0


def check_deeplinks(path, four_by_page):
    """A link into an atlas must name a verse that atlas actually has.

    The atlases route on the fragment: `#13.4` calls showChapter(13) and
    focuses the verse. But the guard is `if(h && V.verses[h])`, so a fragment
    the data does not carry falls through to `showChapter(1)` -- the page loads,
    looks perfect, and quietly shows the wrong adhyaya. Nothing about that is
    visible to a link checker, to the author, or to the reader who assumes the
    verse they were promised is the one on screen.

    So the fragment is checked against the same 4lang file the page will load,
    which is why this runs after the atlases are copied rather than before.
    A bad deep link is a false citation in a document arguing that our
    citations resolve, and it stops the deploy.
    """
    html = open(path, encoding="utf-8").read()
    bad = 0
    for page, frag in re.findall(r'href="(?:\.\./)?([a-z-]+-atlas\.html)#([^"]+)"',
                                 html):
        four = four_by_page.get(page)
        if four is None:
            bad += fail("%s links to %s, which this site does not publish"
                        % (os.path.basename(path), page))
        elif frag not in four.get("verses", {}):
            bad += fail("%s links to %s#%s -- no such verse; the atlas would "
                        "silently open at adhyaya 1"
                        % (os.path.basename(path), page, frag))
    return bad


def sizes(path):
    raw = os.path.getsize(path)
    gz = len(gzip.compress(open(path, "rb").read(), 6))
    return raw, gz


# The Sanskrit is self-hosted, not asked of the visitor's machine and not
# fetched from Google. Every page declares @font-face against these files by a
# RELATIVE path -- `fonts/` from the root, `../fonts/` from docs/ -- so the
# site keeps working from any subdirectory and keeps making exactly one
# off-site request, the YouTube iframe API.
FONTS = ("NotoSerifDevanagari.woff2", "OFL.txt")


def copy_fonts(src, check):
    """Ship the webfont, and refuse to ship a page that cannot reach it.

    A missing font file does not fail loudly at runtime -- it silently falls
    back to whatever the visitor has, which is the boxes this replaced. So the
    absence is checked here, where it is still cheap to fix.
    """
    dst_dir = os.path.join(HERE, "fonts")
    os.makedirs(dst_dir, exist_ok=True)
    bad = 0
    print("\nfonts")
    for name in FONTS:
        dst = os.path.join(dst_dir, name)
        if not check:
            s = os.path.join(src, "fonts", name)
            if not os.path.exists(s):
                bad += fail("missing in the workbench: %s" % s)
                continue
            shutil.copyfile(s, dst)
        if not os.path.exists(dst):
            bad += fail("fonts/%s is not here" % name)
            continue
        print("    %-36s %6.2f MB" % (name, os.path.getsize(dst) / 1e6))
    if os.path.exists(os.path.join(dst_dir, FONTS[0])):
        with open(os.path.join(dst_dir, FONTS[0]), "rb") as fh:
            if fh.read(4) != b"wOF2":
                bad += fail("fonts/%s is not a woff2 file" % FONTS[0])
    return bad


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true",
                    help="verify what is already here; copy nothing")
    ap.add_argument("--with-sim", action="store_true",
                    help="keep the simulated Virāṭa lanes (dropped by default)")
    ap.add_argument("--src", default=SRC, help="workbench directory")
    ap.add_argument("--ingest", default=INGEST,
                    help="audio-ingest directory, source of the witness page")
    ap.add_argument("--site-url", help="public base URL, e.g. "
                    "https://hvram1.github.io/purana-atlas -- substituted into "
                    "docs/*.md and remembered in .site-url for later refreshes")
    a = ap.parse_args()

    if not a.check and not os.path.isdir(a.src):
        sys.exit("no workbench at %s -- set --src or $ATLAS_SRC" % a.src)
    if not a.check and not os.path.isdir(a.ingest):
        sys.exit("no audio-ingest at %s -- set --ingest or $ATLAS_INGEST"
                 % a.ingest)

    bad_url = set_site_url(a.site_url, a.check)
    data_dir = os.path.join(HERE, "data")
    os.makedirs(data_dir, exist_ok=True)
    bad, total_raw, total_gz = bad_url, 0, 0
    stats = {}
    bad += copy_fonts(a.src, a.check)

    # Kept so the authored pages in docs/ can have their deep links checked
    # against the very data the atlas will load, further down.
    four_by_page = {}

    for page, four_name, sub_name in ATLASES:
        key = page.split("-")[0]
        print("\n%s" % page)
        page_dst = os.path.join(HERE, page)
        four_dst = os.path.join(data_dir, four_name)
        sub_dst = os.path.join(data_dir, sub_name)

        if not a.check:
            for name, dst in ((page, page_dst), (four_name, four_dst),
                              (sub_name, sub_dst)):
                src = os.path.join(a.src, "" if name.endswith(".html") else "data",
                                   name)
                if not os.path.exists(src):
                    bad += fail("missing in the workbench: %s" % src)
                    continue
                shutil.copyfile(src, dst)

        if not os.path.exists(page_dst):
            bad += fail("%s is not here" % page)
            continue

        bad += check_fetches(page_dst, (four_name, sub_name))
        b, four = check_4lang(four_dst); bad += b
        four_by_page[page] = four
        b, sub = check_substrate(sub_dst); bad += b

        if not a.with_sim and not a.check:
            four, sim = strip_sim(four)
            if sim:
                json.dump(four, open(four_dst, "w", encoding="utf-8"),
                          ensure_ascii=False, separators=(",", ":"))
                print("  stripped simulated lanes: %s" % sorted(sim))

        real = {l["id"] for l in four["langs"] if not l.get("sim")}
        verses = len(sub.get("text") or {})
        reached = sum(1 for v in four["verses"].values()
                      if any(lid in real for lid in (v.get("lang") or {})))
        both = sum(1 for v in four["verses"].values()
                   if len(real & set(v.get("lang") or {})) > 1)
        eps = four.get("ta_episodes", [])
        # A "recording" is a part with a video behind it. The quote-only rows
        # carry an id so a cited verse can find its part, but they are not
        # recordings OF this text and must not be counted as such.
        rec = sum(1 for e in eps if e.get("yt") and not e.get("quotes_only"))
        stats[key] = {
            "verses": verses, "chapters": len(sub.get("chapters") or {}),
            "reached": reached,
            "reached_pct": round(100.0 * reached / max(1, verses), 1),
            "lanes": len(four["langs"]), "real_lanes": len(real),
            "recordings": rec, "parts": len(eps), "both_lanes": both,
            # Who is chanting, read off the lanes rather than typed into
            # index.html -- the same rule the coverage figures follow. A lane
            # with no `speaker` contributes nothing rather than an empty
            # string, so the page can tell "not recorded here" from "unknown".
            "speakers": sorted({l["speaker"] for l in four["langs"]
                                if l.get("speaker")}),
            "lane_axis": four.get("lane_axis") or "",
        }
        print("  %d verses · %d reached by a real recording (%.1f%%) · "
              "%d lanes (%d real) · %d parts, %d recordings"
              % (verses, reached, stats[key]["reached_pct"],
                 len(four["langs"]), len(real), len(eps), rec))
        for p in (page_dst, four_dst, sub_dst):
            raw, gz = sizes(p)
            total_raw += raw; total_gz += gz
            print("    %-34s %7.2f MB raw  %6.2f MB gzip"
                  % (os.path.basename(p), raw / 1e6, gz / 1e6))

    # The witness page. Same copy-then-verify loop as an atlas, one file
    # lighter, and its numbers land beside theirs so index.html can name it
    # without anybody typing 141 into the markup.
    print("\n%s" % WITNESS[0])
    wit = {}
    page_dst = os.path.join(HERE, WITNESS[0])
    data_dst = os.path.join(data_dir, WITNESS[1])
    if not a.check:
        for name, sub_dir, dst in ((WITNESS[0], WITNESS_SRC[0], page_dst),
                                   (WITNESS[1], WITNESS_SRC[1], data_dst)):
            src = os.path.join(a.ingest, sub_dir, name)
            if not os.path.exists(src):
                bad += fail("missing in audio-ingest: %s -- run "
                            "scripts/tulakaveri_witness.py there" % src)
                continue
            shutil.copyfile(src, dst)
    if not os.path.exists(page_dst):
        bad += fail("%s is not here" % WITNESS[0])
    else:
        bad += check_fetches(page_dst, (WITNESS[1],))
        b, cites = check_selfcontained(page_dst); bad += b
        b, wd = check_witness(data_dst); bad += b
        if wd:
            st = wd["stats"]
            wit = {
                "shared": st["shared"], "identical": st["identical"],
                "index_verses": st["index_verses"],
                "control": st["control"]["shared"],
                "recordings": st["tk_episodes"] + st["dsb_episodes"],
                "hours": round(st["tk_hours"] + st["dsb_hours"], 1),
                "adhyayas": len(st["adhyayas_attested"]),
                "speakers": sorted(w["name"] for w in wd["speakers"].values()),
            }
            print("  %d correspondences · %d with identical decodes · "
                  "0 of them in %s indexed verses · %d recordings, %.1f h"
                  % (wit["shared"], wit["identical"],
                     format(wit["index_verses"], ","), wit["recordings"],
                     wit["hours"]))
        for pth in (page_dst, data_dst):
            raw, gz = sizes(pth)
            total_raw += raw; total_gz += gz
            print("    %-34s %7.2f MB raw  %6.2f MB gzip"
                  % (os.path.basename(pth), raw / 1e6, gz / 1e6))
        for u in cites:
            print("      %-32s cites %s" % ("", u))

    # index.html renders its figures from this file rather than carrying them
    # in the markup, so coverage printed on the landing page cannot drift away
    # from the coverage in the data. [[derive-do-not-ask-the-human]]
    if not a.check:
        json.dump({"built": datetime.date.today().isoformat(),
                   "simulated_lanes": bool(a.with_sim), "atlases": stats,
                   "witness": wit},
                  open(os.path.join(data_dir, "stats.json"), "w",
                       encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print("\nwrote data/stats.json -- index.html reads its numbers from it")

    # The hand-authored pages -- landing page and the two proposals -- are not
    # copied from anywhere, so nothing else would ever look at them. They get
    # the same charset and self-containment checks: a proposal that mojibakes
    # its own Sanskrit, or silently reaches for a font on someone else's CDN,
    # is not fit to send to anyone.
    print("\nauthored pages")
    for rel in ["index.html"] + ["docs/" + n for n in
                                 sorted(os.listdir(os.path.join(HERE, "docs")))
                                 if n.endswith(".html")]:
        path = os.path.join(HERE, rel)
        bad += check_fetches(path, ())
        b, cites = check_selfcontained(path); bad += b
        bad += check_deeplinks(path, four_by_page)
        raw, gz = sizes(path)
        total_raw += raw; total_gz += gz
        print("    %-34s %7.2f MB raw  %6.2f MB gzip" % (rel, raw/1e6, gz/1e6))
        for u in cites:
            print("      %-32s cites %s" % ("", u))

    print("\nsite total  %.2f MB raw   %.2f MB over the wire (gzip)"
          % (total_raw / 1e6, total_gz / 1e6))
    if bad:
        print("\n%d problem(s) -- NOT fit to publish" % bad)
        return 1
    print("nothing here will 404 and nothing will blank. Safe to commit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
