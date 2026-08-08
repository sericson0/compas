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
| **Energy (1–10)** | Composite of rhythmic drive (half the weight), tempo relative to the genre norm, onset density, and loudness variance. Calibrated on golden-age recordings. |
| **Drive (0–100)** | How hard the compás is marked: on-beat vs. off-beat spectral flux in 150–400 Hz (bass, piano left hand) and 400–1200 Hz (bandoneón). Separates Biagi/D'Arienzo from Di Sarli at the same tempo — and separates an orchestra from *itself*, e.g. D'Arienzo's rhythmic *El Flete* from his lyrical *Amarras*. |
| **Sync (0–100)** | Syncopation: how much onset energy falls *between* beats rather than on them. Milonga's habanera scores high, Biagi's straight marking low. Only weakly correlated with drive (r ≈ −0.3), so it adds independent information. |
| **LUFS** | EBU R128 integrated loudness — the number to match levels on across a set. |
| **LRA (LU)** | EBU R128 loudness range: the standardised dynamic-range measure. Note that K-weighting boosts above 2 kHz, exactly where shellac surface noise lives, so LRA reads low on noisy transfers; relative ordering stays meaningful, absolute values are not comparable to a modern master. |

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
                                        rhythm     bpm     range  stab time      key  enrg  drv sync   LUFS   LRA
Canaro - Silueta Portena - 1936         milonga  112.9   109-116    84 fixed     D#m   5.8   61   27  -16.9   5.5
D'Arienzo - Milonga Del Corazon - 1938  milonga  108.8   105-111    83 fixed       G   5.1   18   64  -14.5   7.1
Laurenz - Milonga De Mis Amores - 1944  milonga  103.8   101-106    89 fixed       A   4.7   13   64  -15.8   5.8
Pugliese - Alma De Bohemio - 1958       tango    122.3   111-130    48 flexible   Am   4.4   33   49  -16.3  12.2
Pugliese - El Adios - 1963              tango    123.3   111-128    47 flexible   Dm   3.9   16   46  -18.1  13.2
Troilo - Danzarin - 1963                tango    124.5   116-131    52 flexible    G   3.7   21   45  -18.4   7.0
Biagi - El Incendio - 1938              tango    130.8   128-133    95 fixed      Am   7.0   99   19  -17.1   5.7
Canaro - Hotel Victoria - 1935          tango    119.5   117-122    95 fixed      D#   5.0   73   43  -17.3   4.6
D'Arienzo - Amarras - 1944              tango    122.4   120-128    86 fixed       A   4.6    6   47  -18.6   7.0
D'Arienzo - El Flete - 1936             tango    133.1   131-134    94 fixed       E   6.3   78   40  -16.2   6.7
Di Sarli - El Amanecer - 1942           tango    123.0   121-125    95 fixed       G   4.7   18   57  -15.5  10.9
Di Sarli - Nada - 1944                  tango    121.6   119-130    73 fixed       C   3.4    7   52  -15.4   7.0
Donato - Carnaval De Mi Barrio - 1939   tango    136.5   134-138    94 fixed      Bm   6.4   75   37  -15.0   5.8
Malerba - Gitana Rusa - 1942            tango    117.9   114-123    79 fixed       A   3.7   33   25  -18.9   7.1
Troilo - Toda Mi Vida - 1941            tango    132.5   129-136    92 fixed       A   5.5   38   50  -19.0   8.3
De Angelis - Mi Novia De Ayer - 1944    vals     213.8   210-220    90 fixed      A#   6.0   47   40  -17.9   5.1
Laurenz - Paisaje - 1943                vals     210.6   206-217    81 fixed       A   5.2   43   34  -15.0   6.0
Rodriguez - Tengo Mil Novias - 1939     vals     203.5   200-207    93 fixed       G   5.8   75   19  -18.4   5.9
Victor - Temo - 1940                    vals     219.3   215-223    90 fixed      Am   5.7   61   43  -15.4   5.1
```

Sanity checks worth noticing:

- The three flexible-time tracks are exactly the three the corpus labels
  flexible (stability 47–52; everything else is 73–95).
- **Drive separates an orchestra from itself.** D'Arienzo's rhythmic *El Flete*
  scores 78 against his own lyrical *Amarras* at 6, at almost the same tempo;
  Di Sarli's two sides sit at 18 and 7. That within-orchestra spread is the
  point — orchestra identity is already free metadata, so an audio feature only
  earns its place by varying inside it.
- **Drive and syncopation are near-opposites, as they should be.** Biagi's
  *El Incendio* is 99 drive / 19 sync (relentlessly on the beat); the two
  straight milongas are 13–18 drive / 64 sync (habanera weight falling between
  the beats). They correlate only about −0.3, so both are worth reporting.
- The late-Pugliese tracks pair low energy with the corpus-highest loudness
  range (12.2–13.2 LU) — intense drama, not dance-floor drive.
- LUFS spans −14.5 to −19.0, i.e. **4.5 dB of gain difference** you would
  otherwise be riding the fader for.

## Rhythm selection

`auto` (default) resolves in this order:
1. **Explicit choice** — the rhythm switch in the GUI toolbar / `--rhythm` in the CLI.
2. **GENRE tag** — `Tango`, `Vals`/`Waltz`, `Milonga`/`Candombe`.
3. **Audio detection** (below).

The table shows which source was used: `tango (tag)`, `vals (set)`, `milonga (audio)`.
A trailing `?` — `vals (audio?)` — means the audio guess was low-confidence and
is worth setting by hand; hover the cell for the confidence value.

### How audio detection works

Two steps, because the three rhythms do not separate along one axis.

**Ternary vs. duple.** At the candidate vals beat lag *L*, compare onset
autocorrelation at 3*L* against the midpoint of 2*L* and 4*L*. In 3/4 the bar
falls on 3*L* and sits above its neighbours; in duple meter 3*L* is not a bar
multiple and dips below. Taking the *excess over neighbours* is what makes this
work — raw support at 3*L* is high in every meter, since any integer multiple of
the beat period correlates well. An earlier version that scored raw multiples
did no better than chance on vals.

**Tango vs. milonga.** Both are duple and give identical grouping evidence, so
only tempo separates them: one tempo pass with a wide duple probe (88–148 BPM),
then compare against each genre's typical tempo.

On the 19-track example corpus this scores **19/19**, up from 74% for the
previous heuristic (which misread 3 of 4 valses as milonga). Treat that number
with care: the ternary threshold is fitted to this corpus, only four of the
tracks are valses, and only one sits near the decision boundary. It needs
validation on a larger, more varied set.

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
