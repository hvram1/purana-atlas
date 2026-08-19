#!/usr/bin/env python3
"""Publish the atlas pages and their data from the workbench into this repo.

This repository is a *deployment*, not a source tree. Nothing here is authored
by hand except index.html, README.md and docs/. Everything else is produced in
the workbench and copied in by this script:

    dharmasastra-gcp/workbench/virata-atlas.html   + data/virata_*.json
    dharmasastra-gcp/workbench/kartika-atlas.html  + data/kartika_*.json

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
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.environ.get("ATLAS_SRC",
                     "/home/wipro/projects/dharmasastra-gcp/workbench")

# (page, 4lang file, substrate file). The page names the JSON in its own
# fetch() calls; these must agree, and check_fetches() below proves they do
# rather than trusting this list.
ATLASES = [
    ("virata-atlas.html", "virata_4lang.json", "virata_atlas_substrate.json"),
    ("kartika-atlas.html", "kartika_4lang.json", "kartika_atlas_substrate.json"),
]

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


def check_selfcontained(path):
    """No page may depend on a host we do not control, bar the YouTube API.

    A webfont or stylesheet pulled from a CDN turns a page that works into a
    page that works until someone else's certificate expires -- and on a
    proposal being read by a reviewer offline, into a page that never worked.
    """
    html = open(path, encoding="utf-8").read()
    outside = {u for u in re.findall(r'(?:src|href)\s*=\s*["\'](https?://[^"\']+)',
                                     html)
               if "youtube.com/iframe_api" not in u}
    if outside:
        return fail("%s loads from outside this site: %s"
                    % (os.path.basename(path), sorted(outside)[:2]))
    return 0


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


def sizes(path):
    raw = os.path.getsize(path)
    gz = len(gzip.compress(open(path, "rb").read(), 6))
    return raw, gz


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true",
                    help="verify what is already here; copy nothing")
    ap.add_argument("--with-sim", action="store_true",
                    help="keep the simulated Virāṭa lanes (dropped by default)")
    ap.add_argument("--src", default=SRC, help="workbench directory")
    ap.add_argument("--site-url", help="public base URL, e.g. "
                    "https://hvram1.github.io/purana-atlas -- substituted into "
                    "docs/*.md and remembered in .site-url for later refreshes")
    a = ap.parse_args()

    if not a.check and not os.path.isdir(a.src):
        sys.exit("no workbench at %s -- set --src or $ATLAS_SRC" % a.src)

    bad_url = set_site_url(a.site_url, a.check)
    data_dir = os.path.join(HERE, "data")
    os.makedirs(data_dir, exist_ok=True)
    bad, total_raw, total_gz = bad_url, 0, 0
    stats = {}

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

    # index.html renders its figures from this file rather than carrying them
    # in the markup, so coverage printed on the landing page cannot drift away
    # from the coverage in the data. [[derive-do-not-ask-the-human]]
    if not a.check:
        json.dump({"built": datetime.date.today().isoformat(),
                   "simulated_lanes": bool(a.with_sim), "atlases": stats},
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
        bad += check_selfcontained(path)
        raw, gz = sizes(path)
        total_raw += raw; total_gz += gz
        print("    %-34s %7.2f MB raw  %6.2f MB gzip" % (rel, raw/1e6, gz/1e6))

    print("\nsite total  %.2f MB raw   %.2f MB over the wire (gzip)"
          % (total_raw / 1e6, total_gz / 1e6))
    if bad:
        print("\n%d problem(s) -- NOT fit to publish" % bad)
        return 1
    print("nothing here will 404 and nothing will blank. Safe to commit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
