# Purāṇa Atlas — deployment

Two Sanskrit texts, each verse tied to the second it is chanted in a recorded
*upanyāsam*. This repository is the **published site**, not the source: it holds
the built pages and their data, and one script that refreshes them.

The pages themselves and the JSON they read are produced in
`dharmasastra-gcp/workbench` and copied here by `refresh.py`. Do not edit them
in place — the next refresh will overwrite them.

## What is here

```
index.html                 landing page; its figures come from data/stats.json
virata-atlas.html          Virāṭa Parva, Mahābhārata book 4
kartika-atlas.html         Kārtika Māsa Māhātmya, Skanda Purāṇa
data/*.json                one 4lang + one substrate file per atlas, + stats.json
docs/purana-audio.html     proposal — commission verse-addressable recitation
docs/purana-nama-kosa.html proposal — a Sorensen-style index of Paurāṇic names
docs/purana-audio-pitch.md plain-text source of the first, for reading on GitHub
refresh.py                 rebuild-and-verify; the only script here
.nojekyll                  serve the files verbatim, no Jekyll pass
```

Every path in the site is **relative**, so it works from any subdirectory —
including a GitHub Pages project site at `https://<user>.github.io/<repo>/`.
Each atlas fetches exactly two JSON files; the only off-site request any page
makes is `https://www.youtube.com/iframe_api`, on the two atlases alone.

About 13 MB on disk, **≈2.1 MB over the wire** once gzipped.

## Publishing it

```sh
git init && git add -A && git commit -m "purāṇa atlas"
gh repo create purana-atlas --public --source=. --push   # or push to a repo you made
```

Then in the repository's **Settings → Pages**, set the source to your default
branch and the folder to `/ (root)`. Give it a minute and the site is at
`https://<user>.github.io/purana-atlas/`.

The two HTML proposals link to the atlases relatively and need nothing. The
markdown copy is read on github.com, where a relative link resolves to a source
blob, so give it the live URL once:

```sh
./refresh.py --site-url https://<user>.github.io/purana-atlas
```

The URL is remembered in `.site-url`, so later refreshes keep it.

**GitHub Pages needs the repository to be public**, unless you are on GitHub Pro
or Team. Everything here is generated output and safe to publish; that is the
point of keeping it in its own repository rather than serving the workbench,
which is 22 GB and full of things that are not for the web.

Cloudflare Pages works equally well and needs no repository —
`wrangler pages deploy .` from this directory.

## Refreshing after a rebuild

```sh
cd ../dharmasastra-gcp/workbench
myenv/bin/python scripts/build_kartika_audio.py    # or build_virata_audio.py
cd ../../purana-atlas
./refresh.py
git commit -am "refresh atlases" && git push
```

`refresh.py` copies, then **verifies before letting anything land**, and exits
non-zero if something would break in a way a copy cannot see:

- the substrate's container shapes — `cards`/`ann`/`cast` must be dicts,
  `kin`/`spouse`/`sib`/`events` must be lists. Ship `{}` where a list belongs
  and every visitor gets "Could not load data", a blank page rather than an
  empty layer;
- every page declares `charset=utf-8`, or the Devanagari mojibakes on any
  server that serves `text/html` bare;
- every page fetches the JSON by the relative path we ship it at, and none
  fetches an absolute `/data/...` that would 404 under `/<repo>/`;
- every occurrence in a real lane has an episode row behind it, since that row
  is the only place a video URL lives.

Other modes:

| | |
|---|---|
| `./refresh.py --check` | verify what is already here, copy nothing |
| `./refresh.py --with-sim` | keep the simulated Virāṭa lanes (see below) |
| `./refresh.py --src DIR` | read from a workbench somewhere else |

## The simulated lanes are dropped by default

The Virāṭa atlas can show four lanes, but only Tamil is a real recording — the
Kannada, Telugu and Bengali lanes are **invented timings**, built so the
interface could be judged before such recordings existed. The atlas marks them
`sim` and refuses to play them, which is honest enough for a workbench.

It is not honest enough for a public URL, and the reason is what a visitor
actually sees. On adhyāya 1 the real Tamil lane is empty — the reciter does not
expound those verses — while all three invented lanes show full coloured bars
and plausible timestamps. The opening screen would be three fabricated
recordings looking complete beside the one real recording looking absent, with a
small grey badge as the only correction.

So the published site ships the real lane alone. Pass `--with-sim` to publish
the mockup anyway; it is a fair illustration of what `docs/` is asking to fund,
which is an argument for putting it in the pitch as a labelled screenshot rather
than live on the page.

## Before you make it public

- **The videos must be public or unlisted, with embedding allowed.** Playback is
  a YouTube embed; a private video will not play for anyone but you. Unlisted is
  fine and embeds normally.
- **The video ids are in the JSON in plain text.** Publishing the atlas makes
  unlisted uploads effectively findable. That is usually what you want here, but
  it should be a decision rather than a surprise.
- **Devanagari needs a font on the visitor's machine.** The pages ask for Noto
  Serif Devanagari and fall back to whatever is installed; a machine with
  nothing suitable shows boxes. Adding a webfont is a one-line change to each
  page if that matters.

## The two proposals

`docs/` carries the pair of proposals these atlases are the evidence for. They
share a corpus and each is worth more with the other: one would make the Purāṇas
**audible** at the verse, the other **searchable** by name.

- **Purāṇa Audio Project** — commission recitation that is verse-addressable
  from the moment it is recorded. Its argument is the measured ceiling of
  retrofitting: 61–88% of a text, because a reciter does not chant every verse.
- **Purāṇa Nāma-Kośa** — a scholar-verified index of the names, peoples and
  places of the Paurāṇic corpus, beginning with the Harivaṃśa: 16,099 verses,
  the largest book in the epic corpus, absent from Sorensen and from the Gītā
  Press *nāmānukramaṇikā* alike. This one also exists as a Claude artifact; the
  copy here is a deployment of it and carries an added link to its companion,
  so the two versions are deliberately not byte-identical.

Both are self-contained HTML and are checked by `refresh.py` on every run for a
declared charset and for loading nothing from outside this site — a proposal
that mojibakes its own Sanskrit, or waits on someone else's CDN, is not fit to
send to anyone.

## Where the material comes from

Text: the Sringeri Śāradā Pīṭham purāṇa corpus (all eighteen mahāpurāṇas,
351,225 verses) and the Mahābhārata critical edition, with M. N. Dutt's 1897
translation on the Virāṭa side. Timings: CTC forced alignment over the waveform,
not hand-marked. Recordings by the reciters named in each atlas.
