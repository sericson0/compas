# COMPAS — Tango Music Analyzer

Musical feature analysis for Argentine tango DJs and dancers: **BPM, key,
energy, and rubato** for tango, vals, and milonga, with a GUI, a CLI, and
tag-based integration with VirtualDJ (or any DJ software that reads tags).

## What it measures

| Metric | Meaning |
|---|---|
| **BPM** | Median beat-level tempo. The rhythm type constrains the plausible range, so a vals lands at ~178 quarter-note BPM instead of a half/double-tempo error. |
| **BPM range** | 10th–90th percentile of the *local* tempo across the song. For steady orchestras this is a couple of BPM wide; for late Pugliese it is the honest answer where a single BPM would be a lie. |
| **Bars/min** | BPM ÷ beats per bar (tango 4/4, vals 3/4, milonga 2/4). Vals is often compared in bars/min. |
| **Stability (0–100)** | How steady the tempo is, measured on the *detrended* local-tempo curve — a gradual accelerando (routine in valses) still counts as a fixed groove; only local push-pull (rubato) lowers it. Drives the **fixed / flexible** verdict (threshold 70 for tango/milonga, 50 for vals). |
| **Key / Camelot** | Chroma-based key estimate (Krumhansl–Kessler profiles). Note: 78 rpm transfer speeds vary, so old recordings can sit between concert keys — treat low-confidence keys as approximate. |
| **Energy (1–10)** | Composite of rhythmic drive, tempo relative to the genre norm, onset density, and loudness variance. Calibrated on golden-age recordings. |
| **Drive (0–100)** | How hard the compás is marked — separates Biagi/D'Arienzo from Fresedo/Di Sarli at the same tempo. |
| **Dyn (dB)** | Short-term loudness spread — the Pugliese dramatic arc vs. a flat Canaro side. |

## How tempo is measured (and why it works on old recordings)

The local tempo comes from a windowed autocorrelation tempogram (~6 s), with
three defenses that matter for golden-age material:

1. **Genre range restriction** — candidates outside the rhythm's plausible
   beat-tempo range are never considered, so half/double-tempo errors can't
   happen.
2. **Harmonic reinforcement** — a candidate tempo only scores well if its
   bar-level lag multiples also show periodicity. This kills the 4/3
   habanera artifact that derails beat trackers on milongas.
3. **Viterbi smoothing** — a transition penalty on log-tempo jumps forbids
   frame-to-frame metrical-level flipping while letting phrase-level rubato
   through. Vals is tracked at the *bar* level (the uneven oom-pah-pah
   smears the beat-level peak; the bar period stays sharp) and converted
   back to beat BPM.

### Validation against Mixed In Key

Several example files carry Mixed-In-Key tags, giving independent ground
truth. On the 19-track corpus: BPM agrees with MIK within ~1–3 BPM wherever
MIK produced a value (vals matches at the metrical-level factor, e.g. 70.5
vs 71.23 bars/min); MIK returned **bpm=0** (gave up) on the flexible
Pugliese tracks, where COMPAS reports a median plus an honest range and a
"flexible" verdict. Every steady track classifies as fixed, all three
flexible-time examples as flexible. Key detection agrees with MIK exactly on
5 of 9 labeled tracks; misses are fifth-relation or major/minor-mode errors,
which is typical for profile-based key detection on shellac-era recordings —
treat keys as approximate and prefer the existing MIK tag (shown in the "Tag
BPM/key" column) when present.

### Results on the example corpus

```
                                        rhythm     bpm     range  stab time      key  enrg  drv   dyn
Canaro - Silueta Portena - 1936         milonga  111.4   107-116    79 fixed     D#m   4.4   22   7.6
D'Arienzo - Milonga Del Corazon - 1938  milonga  108.6   105-111    83 fixed       G   5.1   30  11.8
Laurenz - Milonga De Mis Amores - 1944  milonga  103.6   100-106    88 fixed       A   5.1   38   9.5
Pugliese - Alma De Bohemio - 1958       tango    122.3   111-130    48 flexible   Am   4.0   25  16.6
Pugliese - El Adios - 1963              tango    123.3   111-128    47 flexible   Dm   4.1   25  17.1
Troilo - Danzarin - 1963                tango    124.5   116-131    52 flexible    G   3.9   29   9.7
Biagi - El Incendio - 1938              tango    130.8   128-133    95 fixed      Am   8.0  100  13.6
Canaro - Hotel Victoria - 1935          tango    119.5   117-122    95 fixed      D#   5.4   74   6.4
D'Arienzo - Amarras - 1944              tango    122.4   120-128    86 fixed       A   4.7   23  13.8
D'Arienzo - El Flete - 1936             tango    133.1   131-134    94 fixed       E   6.9   80  10.7
Di Sarli - El Amanecer - 1942           tango    123.0   121-125    95 fixed       G   5.7   53  15.5
Di Sarli - Nada - 1944                  tango    121.6   119-130    73 fixed       C   4.2   37  11.8
Donato - Carnaval De Mi Barrio - 1939   tango    136.5   134-138    94 fixed      Bm   6.6   67   9.2
Malerba - Gitana Rusa - 1942            tango    117.9   114-123    79 fixed       A   5.3   70  10.0
Troilo - Toda Mi Vida - 1941            tango    132.5   129-136    92 fixed       A   6.8   69  11.7
De Angelis - Mi Novia De Ayer - 1944    vals     211.4   196-214    79 fixed      A#   5.5   18   9.3
Laurenz - Paisaje - 1943                vals     208.1   196-213    69 fixed       A   5.7   31   9.3
Rodriguez - Tengo Mil Novias - 1939     vals     202.7   198-206    91 fixed       G   6.1   44   9.2
Victor - Temo - 1940                    vals     213.8   193-220    54 fixed      Am   4.0    3   8.5
```

Sanity checks worth noticing: the three flexible-time tracks are exactly the
three the corpus labels flexible; the late-Pugliese tracks pair *low* energy
with the corpus-highest dynamic range (16.6-17.1 dB) — intense drama, not
dance-floor drive — while El Incendio tops both drive and energy; and the
lyrical sides (Amarras, Nada) sit well below their orchestras' rhythmic
sides at nearly identical BPM, which is the point of measuring drive
separately from tempo.

## Rhythm selection

`auto` (default) resolves in this order:
1. **Explicit choice** — the rhythm switch in the GUI toolbar / `--rhythm` in the CLI.
2. **GENRE tag** — `Tango`, `Vals`/`Waltz`, `Milonga`/`Candombe`.
3. **Audio heuristic** — triple-vs-duple meter from beat-accent periodicity, then tango-vs-milonga by tempo-range fit.

The table shows which source was used: `tango (tag)`, `vals (set)`, `milonga (audio)`.

## GUI

```
run_gui.bat            (double-click)
# or:
C:\Users\seric\.venvs\compas\Scripts\python -m compas_gui
```

- Drag files or folders anywhere into the window (or use *Add files / Add folder*).
- Pick a rhythm mode (or leave `auto`) and press **Analyze**.
- Right-click selected rows to re-analyze them as a specific rhythm or remove them.
- **Write tags…** writes results into the files (only on request, never automatically):
  - `BPM` and `INITIALKEY` — the standard fields VirtualDJ imports from tags,
  - `COMPAS_*` fields — energy, drive, stability, timing, BPM range, bars/min,
  - optional `COMPAS Energy N` note **appended** to the comment (existing comment text is preserved).
- **Export CSV / JSON** for the whole session.

### VirtualDJ integration (works today, no plugin needed)

1. Analyze your files and use *Write tags…* (keep BPM + key checked).
2. In VirtualDJ's browser, right-click the tracks → **File Info → Load tags from file** (or enable tag reading in Options), so VDJ's BPM/Key columns use the tag values.
3. Energy: enable the *Comment* column (if you used the comment option), or map a custom field.

## CLI

```
C:\Users\seric\.venvs\compas\Scripts\python compas_cli.py example_songs
python compas_cli.py my_folder --rhythm auto --csv out.csv --json out.json
python compas_cli.py song.flac --write-tags --key-format camelot
```

## Project layout

```
compas_core/       analysis library (shared by GUI, CLI, and future plugin)
  audio.py         decoding (soundfile, ffmpeg fallback)
  rhythm.py        tango/vals/milonga specs, tempo priors, genre mapping
  tempo.py         tempogram-based local tempo, stability, beat tracking
  key.py           key + Camelot + confidence
  energy.py        drive, dynamic range, energy composite
  tags.py          tag read/write (FLAC, MP3, MP4)
  analyze.py       analyze_file() orchestration
compas_gui/        PySide6 app (drag-drop table, tag writer, exports)
compas_cli.py      batch CLI
```

Setup from scratch:

```
python -m venv C:\Users\seric\.venvs\compas
C:\Users\seric\.venvs\compas\Scripts\pip install numpy scipy librosa soundfile mutagen PySide6
```

(ffmpeg on PATH is used to decode non-FLAC formats.)

## Phase 2 — VST3 plugin (design)

Goal: a `COMPAS Analyzer` VST3 usable in VirtualDJ's effect slots and in any
DAW, showing live BPM / stability / energy for the playing deck.

Planned approach:

- **Framework**: JUCE (C++20), VST3 target; GUI shows the same metric set
  as the desktop table, computed on a rolling window.
- **Algorithms**: port of `compas_core`'s tempogram local-tempo method to
  streaming form (ring buffer of onset strength, ~6 s window, genre-range
  folding identical to `rhythm.py`); energy/drive from the same feature
  formulas. The Python implementation stays the reference; a shared JSON of
  calibration constants keeps the two in sync.
- **Rhythm switch**: plugin parameter (tango/vals/milonga/auto), automatable
  by the host.
- **Why Phase 2**: real-time C++ is a build-toolchain project (MSVC + JUCE +
  VST3 SDK). The analysis logic should be proven and calibrated in Python
  first — which is what Phase 1 does.

## Notes on conventions

- Tango is treated as 4/4, vals 3/4, milonga 2/4 (beat = quarter note).
  Sites like tango.info count tango in 2/4 bars, so their "bars/min" is 2×
  the value shown here; the beat-level BPM is convention-independent.
- Beat-level tempo priors: tango 100–145, vals 150–215, milonga 85–135 BPM.
  Adjust in `compas_core/rhythm.py` if your collection disagrees.
