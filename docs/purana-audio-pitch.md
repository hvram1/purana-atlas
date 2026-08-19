# Purāṇa Audio Project

> Plain-text source of [`purana-audio.html`](purana-audio.html), which is the
> version to send anyone — same argument, typeset. Its companion is
> [`purana-nama-kosa.html`](purana-nama-kosa.html).

**Commissioning structured recordings of the purāṇas — tagged at the verse from
the moment they are recorded, not years afterwards.**

This document used to be a proposal for a proof of concept. The proof of concept
now exists, so this is a proposal for what to do next.

---

## Start with the working thing

Two texts, each verse tied to the second it is chanted in a recorded
*upanyāsam*. Click a verse and the recording plays from that verse.

| | [Virāṭa Parva](https://hvram1.github.io/purana-atlas/virata-atlas.html) | [Kārtika Māsa Māhātmya](https://hvram1.github.io/purana-atlas/kartika-atlas.html) |
|---|---|---|
| source | Mahābhārata, book 4 | Skanda Purāṇa |
| verses | 2,262 in 72 adhyāyas | 1,817 in 36 adhyāyas |
| reached by a recording | **2,000 — 88.4%** | **1,116 — 61.4%** |
| reciters | one | two, independently |
| recordings aligned | 22 parts | 35 parts |
| translation layer | M. N. Dutt, 1897 | none exists |
| entity layer | 2,195 cards, 2,039 verse annotations | none exists |

Neither atlas was hand-timed. Every onset is a measurement.

---

## What the machine does

1. **Transcribe** the recording.
2. **Match** the transcript against the printed text, which must already be
   machine-readable — this is the load-bearing precondition, see below.
3. **Force-align** each matched verse to the waveform, so its start and end are
   properties of the audio rather than an editor's judgement.
4. **Seat** the verse in the text, and emit subtitles and a searchable index.

Where a verse carries no timing, that is also a claim, and the atlas keeps the
two reasons apart: *the reciter did not chant it* is not the same as *we could
not find it*. Refusing to blur those is most of what makes the result usable as
a reference rather than a demo.

---

## What retrofitting taught us — the actual case for recording differently

Everything above was extracted from recordings made without any of this in mind.
That works, and the ceiling is visible in the numbers.

**Coverage tops out well short of the text, and not because of the software.**
Virāṭa reaches 88% because one reciter, expounding at his own pace, simply does
not chant every verse. Kārtika reaches 61% for the same reason. A recording made
*for* this purpose — where the reciter chants each verse before expounding it —
would approach the whole text. **That gap, 12 to 39 points, is what
commissioning buys.** It cannot be bought with better software.

**Two reciters of one text barely overlap, so they add rather than duplicate.**
The Kārtika atlas has two independent Tamil renditions of the same 1,817-verse
work:

| | verses reached |
|---|---|
| Reciter A alone | 974 |
| Reciter B alone | 320 |
| both | 178 |
| **union** | **1,116** |

They diverge because they read the book differently: A works straight through
from the first adhyāya, B follows the ritual calendar and takes each day's
verses from wherever the text supports them. The middle of the book is A's
alone; three whole chapters are B's alone. **A second reciter is not redundancy,
it is coverage** — and where they do overlap, those 178 verses become a
controlled comparison of two traditions saying the same words.

**If the printed text is not in the index, the output is citations, not
captions.** One series in the archive — twenty-six recordings, fourteen and a
half hours — produced 1,370 passages of chanted Sanskrit that match nothing. We
tested three candidate source texts against it, including scraping two complete
purāṇas we did not already hold; the best of them explained 1% of the passages.
The recordings are fine. The book being expounded is not one we have. **So the
first question about any commission is not the language or the reciter, it is
whether a machine-readable edition of that text exists.**

**The unit is the half-verse, not the verse.** Reciters re-chant a hemistich
before glossing it, which is invisible to anything looking for whole verses. We
learned this three times by measuring; a recording brief can simply say it.

---

## The precondition is already met

The Sringeri Śāradā Pīṭham corpus gives us all eighteen mahāpurāṇas as
structured text — **351,225 verses across 97 sections** — which is what step 2
above consumes. For the five texts this proposal names:

| text | verses available | notes |
|---|---|---|
| Viṣṇu Purāṇa | 6,258 | |
| Bhāgavata Purāṇa | 14,488 | |
| Padma Purāṇa | 49,326 | |
| Varāha Purāṇa | 10,258 | |
| Gāruḍa / Mārkaṇḍeya | 11,990 / 6,198 | |
| *(Skanda, for reference)* | *94,483* | the Kārtika atlas is one 1,817-verse section of it |

Every one of them is present. No text acquisition is on the critical path.

---

## What to commission

The original scope was five purāṇas in five languages, roughly 500 hours. That
still reads right, with one change of emphasis: **choose the pairings by
tradition, and take the machine-readability of the text as given rather than as
a risk.**

| Purāṇa | Language | Tradition | Est. hours |
|---|---|---|---|
| Viṣṇu | Tamil | Śrī Vaiṣṇava | 80–100 |
| Bhāgavata | Telugu | Andhra | 120–150 |
| Padma | Kannada | Karnataka | 100–120 |
| Varāha | Hindi | North Indian | 60–80 |
| Gāruḍa / Mārkaṇḍeya | Bengali | Bengal | 80–100 |

**The recording brief, which is the new deliverable of this proposal:**

- chant each verse in full before expounding it, and chant each half-verse
  before glossing it;
- name the adhyāya and verse aloud at the start of each session;
- record one clean channel, no music bed under the chant;
- keep the sessions in order and note where a session stops mid-adhyāya.

None of that constrains the reciter's own manner of exposition. All of it moves
coverage from ~60–88% toward the whole text, and it costs nothing at recording
time — only afterwards, when it cannot be bought at all.

---

## What it costs

Two separate numbers, which the original version of this document ran together.

**Processing recordings we already have is nearly free.** The archive that
produced the Kārtika atlas is 167 recordings, 93 hours. Machine cost is about
₹49 per hour of audio, so the whole archive is roughly ₹4,600. The binding
constraint is compute time, not money — about 176 CPU-hours for the archive, on
hardware we own.

**Commissioning new recordings is the real budget**, and it is an honorarium
question rather than a technical one: 500 hours of a senior *upanyāsakar*'s time
across five languages. That figure belongs to whoever sets the honorarium —
it is not something this pipeline can estimate, and pretending otherwise was the
weakest part of the earlier draft.

The useful ratio: **once a recording exists, turning it into a verse-addressable
edition costs about ₹49 an hour.** Commissioning is the expensive half; the
tagging is a rounding error. That is the argument for commissioning at all.

---

## Limits, stated plainly

- **There is no entity layer for a purāṇa.** The Virāṭa atlas's 2,195 character
  cards come from two Mahābhārata name indexes — Sorensen's and the Gita Press
  *nāmānukramaṇikā*. Neither covers the purāṇas, and no amount of further audio
  supplies them. The Kārtika atlas says so on its own face rather than showing
  an empty column. Building one is a separate project with a separate skill.
- **Coverage figures are not quality figures.** 61.4% means a verse has a
  measured onset, not that a listener has confirmed it. Spot-checking by ear is
  part of the work and has caught real errors.
- **Multi-language is not yet demonstrated.** The Virāṭa atlas can display four
  lanes, but only the Tamil one is a real recording; the Kannada, Telugu and
  Bengali lanes were invented timings, built so the interface could be judged
  before such recordings existed. They are switched off in this published site
  precisely because a public page should not show fabricated timings beside real
  ones. **Commissioning is what would make that interface honest** — which is,
  in one sentence, this whole proposal.

---

## Next steps

1. **Choose the first pairing** — one purāṇa, one language, one reciter.
2. **Agree the recording brief** above with that reciter, and record one adhyāya
   as a calibration run.
3. **Measure the coverage of that adhyāya** against the 61–88% retrofit
   baseline. If a purpose-made recording does not beat it substantially, the
   premise of this proposal is wrong and we should know that from one adhyāya
   rather than from a hundred hours.

---

*Text from the Sringeri Śāradā Pīṭham purāṇa corpus and the Mahābhārata critical
edition. Recordings by the reciters named in each atlas. Alignment by CTC forced
alignment over the waveform.*
