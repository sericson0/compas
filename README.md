# COMPAS — Tango Music Analyzer

Musical feature analysis for Argentine tango DJs and dancers: **BPM, key,
energy, rubato, articulation, texture and voice** for tango, vals, and
milonga, with a GUI, a CLI, tag-based integration with VirtualDJ (or any DJ
software that reads tags), and a **facet grid** that turns the numbers into
words in English or tango vocabulary.

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
| **Artic (0–100)** | Articulation: how detached the playing is — attack sharpness plus how far each note falls away before the next. Measured in fixed 50/140 ms windows so it is not a restatement of tempo. Related to drive (r = 0.73) but not the same: Victor's *Temo* marks the compás firmly (drive 61) with the softest attacks in the corpus (artic 5). |
| **Texture (0–100)** | Percussive versus sustained, from the anisotropy of the spectrogram — percussive energy changes fast in time and slowly in frequency, harmonic energy the reverse. Effectively **independent of drive (r = 0.06)**, so it is a genuinely new axis rather than a restatement. |
| **Harmony (0–100)** | How many distinct harmonies the piece uses. **Provisional** — the least validated number here; see [Harmonic complexity](#harmonic-complexity-read-this-one-sceptically). |
| **Voice** | `instrumental` / `estribillo` / `vocal`. Taken from the filename when it says "Instrumental", otherwise estimated from syllabic modulation with the beat grid notched out. See [Vocal presence](#vocal-presence). |
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
                                       rhythm      bpm stab  key enrg drv snc art tex hrm voice          LRA
Biagi - El Incendio - 1938             tango     130.8   95   Am  7.0  99  19  97  68   9 instrumental*  5.7
Canaro - Hotel Victoria - 1935         tango     119.5   95   D#  5.0  73  43  39  16  43 instrumental*  4.6
D'Arienzo - Amarras - 1944             tango     122.4   86    A  4.6   6  47  13  60  63 vocal          7.0
D'Arienzo - El Flete - 1936            tango     133.1   94    E  6.3  78  40  79  43  90 instrumental*  6.7
Di Sarli - El Amanecer - 1942          tango     123.0   95    G  4.7  18  57  27  22  93 instrumental* 10.9
Di Sarli - Nada - 1944                 tango     121.6   73    C  3.4   7  52  12  67  61 vocal?         7.0
Donato - Carnaval De Mi Barrio - 1939  tango     136.5   94   Bm  6.4  75  37  67  83  52 vocal          5.8
Malerba - Gitana Rusa - 1942           tango     117.9   79    A  3.7  33  25  40  94  25 vocal          7.1
Pugliese - Alma De Bohemio - 1958      tango     122.3   48   Am  4.4  33  49  11  28  91 instrumental* 12.2
Pugliese - El Adios - 1963             tango     123.3   47   Dm  3.9  16  46  23  94  47 vocal         13.2
Troilo - Danzarin - 1963               tango     124.5   52    G  3.7  21  45  13   7  83 instrumental*  7.0
Troilo - Toda Mi Vida - 1941           tango     132.5   92    A  5.5  38  50  64  67  71 instrumental?  8.3
De Angelis - Mi Novia De Ayer - 1944   vals      213.8   90   A#  6.0  47  40  12  61  40 vocal          5.1
Laurenz - Paisaje - 1943               vals      210.6   81    A  5.2  43  34  19  65  88 vocal          6.0
Rodriguez - Tengo Mil Novias - 1939    vals      203.5   93    G  5.8  75  19  55  86  46 vocal          5.9
Victor - Temo - 1940                   vals      219.3   90   Am  5.7  61  43   5  41  57 vocal          5.1
Canaro - Silueta Portena - 1936        milonga   112.9   84  D#m  5.8  61  27  29  26  40 vocal          5.5
D'Arienzo - Milonga Del Corazon - 1938 milonga   108.8   83    G  5.1  18  64   8  58  86 vocal          7.1
Laurenz - Milonga De Mis Amores - 1944 milonga   103.8   89    A  4.7  13  64  18  38  58 instrumental*  5.8
```

`*` = taken from the filename, `?` = a close audio call. BPM range, timing
and LUFS are omitted here for width; the CLI and GUI show them all.

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
- **Articulation is not a second drive column.** They agree where you would
  expect (Biagi 99/97, Amarras 6/13) and part company where it matters:
  Victor's *Temo* marks the compás firmly at drive 61 with the softest
  attacks in the corpus (artic 5), and Troilo's *Toda Mi Vida* is the
  reverse (drive 38, artic 64). Overall r = 0.73 — half the variance is
  independent.
- **Texture is orthogonal to drive** (r = 0.06). The surprise is late
  Pugliese near the top (*El Adiós* 94): the yumba really is a percussive
  attack, and a full HPSS split agrees.

## Facets — the numbers as words

Every metric above is also available as a **facet**: one thresholded number
rendered as a word, in English or in tango vocabulary. Pick which axes to
compare over from the **Facets ▾** menu (or `--facet-axes` on the CLI); each
one adds a `≡` column, and a `Facets` column composes them into a phrase.

```
Biagi - El Incendio - 1938             fast driving instrumental      rapido ritmico instrumental
Pugliese - El Adios - 1963             smooth flexible vocal          melodico fraseo cantado
Troilo - Danzarin - 1963               smooth flexible instrumental   melodico fraseo instrumental
Canaro - Hotel Victoria - 1935         slow driving instrumental      lento ritmico instrumental
Laurenz - Milonga De Mis Amores - 1944 slow smooth instrumental       lento melodico instrumental
```

The same tracks with articulation and texture switched on as well:

```
Biagi - El Incendio - 1938             fast driving staccato percussive instrumental
Pugliese - El Adios - 1963             smooth legato percussive flexible vocal
Troilo - Danzarin - 1963               smooth legato sustained flexible instrumental
Canaro - Hotel Victoria - 1935         slow driving sustained instrumental
Laurenz - Milonga De Mis Amores - 1944 slow smooth legato instrumental
```

The composed label skips any axis on which a track is unremarkable, so it
reads "fast driving instrumental" rather than "fast driving mixed balanced
steady instrumental". The per-axis columns still show every level.

| Axis | English | Tango | From |
|---|---|---|---|
| Tempo * | slow / medium / fast | lento / medio / rapido | BPM ÷ the rhythm's typical BPM |
| Character * | smooth / balanced / driving | melodico / mixto / ritmico | Drive |
| Articulation | legato / detached / staccato | ligado / medio / picado | Artic |
| Texture | sustained / mixed / percussive | lirico / equilibrado / percusivo | Texture |
| Placement | straight / mixed / syncopated | liso / medio / sincopado | Sync |
| Phrasing * | steady / flexible | compas / fraseo | Timing |
| Voice * | instrumental / refrain / vocal | instrumental / estribillo / cantado | Voice |
| Harmony | simple / moderate / complex | directo / elaborado / complejo | Harmony |
| Lift | gentle / moderate / lively | suave / medio / energico | Energy |
| Dynamics | even / dynamic / dramatic | parejo / dinamico / dramatico | LRA |
| Mode | major / minor | mayor / menor | Key |

`*` = on by default. Tempo is deliberately **genre-relative**, so a vals at
210 BPM is not automatically "fast".

Two things worth being clear about:

1. **A facet is a view of a column, not a new measurement.** Nothing here is
   computed that is not already in the table. A label that reads wrong is a
   threshold to argue with, and the number it came from is in the next
   column over.
2. **The thresholds are provisional.** Every cut point was placed to split a
   19-track corpus into sensible groups. That is enough to make the feature
   usable and nowhere near enough to make it right — see
   [Calibrating on your own library](#calibrating-on-your-own-library).

## Vocal presence

Instrumental / estribillo / vocal is the thing tanda building actually turns
on, and it is the one metric here with free ground truth: a library that
marks instrumentals in the title supplies its own labels.

**Why the obvious approaches fail.** A monophonic pitch tracker (pyin)
scored 58% on the example corpus — worse than always guessing "vocal" (63%)
— because it assumes one sounding pitch and a tango orchestra never offers
one. Vibrato is not much better: on narrow-band mono the violins vibrate in
the singer's register, and a bandoneón, being a free-reed instrument, can
barely vibrate at all.

**What works.** A singer's syllable rate lands in the classic 2.5–7.5 Hz
speech band — but so does a tango orchestra's note rate, since eighth notes
at 130 BPM are 4.3 Hz. The difference is that the orchestra's modulation is
*locked to the beat* and the singer's is not. We already know the tempo to a
fraction of a BPM, so the metrical comb can simply be notched out of the
modulation spectrum, and the syllabic energy that survives is the vocal
evidence.

On the 19-track corpus this separates the classes at **d′ = 2.0**
(instrumentals mean 12.6, vocals 17.3) for **18/19** at the fitted
threshold. It is a plateau across window lengths and notch widths, not one
lucky cell of a parameter sweep.

Read that number with the care it deserves:

- **19 tracks is not a validation set**, and the two classes overlap between
  14.1 and 17.6. The optimum sits in a plateau 0.1 wide — the top
  instrumental scores 14.1, the bottom vocal 14.2. `VOCAL_THRESHOLD` is the
  fitted optimum, not a robust one.
- **The failure mode is musically coherent**: a cantabile instrumental solo
  looks like a singer. The single miss is exactly that — Laurenz's *Milonga
  De Mis Amores*, whose melody line sings. Troilo's *Danzarín* is the next
  closest for the same reason.
- **A filename beats the audio.** Where the title says "Instrumental" that
  answer is used and the audio estimate is only reported, exactly as a GENRE
  tag overrides the rhythm heuristic. The rule is one-directional: the word
  being present is reliable, its absence proves nothing.
- **`estribillo` is untested, not merely provisional.** The corpus contains
  no labelled refrain, so the cut is set where the corpus produces none.
  Until it is calibrated, read "estribillo" as "vocal, possibly brief".

To score it on your own library — which is the real test:

```
python scripts/validate_vocal.py D:\Tango
python scripts/validate_vocal.py library.csv     # from compas_cli --csv
```

It reports d′, precision/recall, the misses by name, and the threshold to
paste back into `compas_core/vocal.py`.

## Harmonic complexity (read this one sceptically)

Chroma on shellac-era mono is smeared — surface noise puts energy in every
pitch class — and three plausible measures died against the corpus before
the one that shipped:

- whole-song chroma entropy is pinned at 0.98 for every track, because the
  noise floor dominates the average;
- harmonic-change rate per *second* (Harte's HCDF) just re-sorts the corpus
  by genre: valses change chords more often per second because they are
  faster, which says nothing about complexity;
- the same rate per *bar* inverts that and sorts by genre the other way.

What ships is **variety**: beat-synchronous CENS chroma with each pitch
class's own 20th percentile subtracted (hiss lifts all twelve by roughly the
same amount, so the floor is removable), then the effective rank of the
result — read it as "how many independent harmonic shapes does this piece
use". Biagi's *El Incendio*, four chords hammered for three minutes, comes
last at 9/100.

**It agrees with a hand-written expert ordering of the 19 tracks at only
Spearman 0.41**, and it correlates with syncopation at r = 0.62, which is
more than a genuinely independent axis should. That is suggestive, not
established. The Harmony facet axis is therefore **off by default** —
calibrate it on a real library before trusting it, or leave it off and lose
nothing else.

## Calibrating on your own library

The facet thresholds and the vocal threshold are fitted to 19 tracks. Two
commands replace them with numbers from a real collection:

```
python compas_cli.py D:\Tango --fast --csv library.csv
python scripts/calibrate_facets.py library.csv
python scripts/validate_vocal.py library.csv
```

`calibrate_facets.py` proposes percentile cut points (terciles by default;
`--split 20 80` makes the outer levels narrower, which usually reads better
as labels), reports how much of each 0–100 anchor range the library actually
occupies, and with `--per-rhythm` shows medians per rhythm. That last one
matters: on the example corpus median drive runs milonga 18 / tango 33 /
vals 54, so a single set of cut points is already a compromise, and a large
library may justify per-rhythm thresholds.

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
- Pick a rhythm mode (or leave `auto`) and press **Analyze** (or Ctrl+Enter).
- **Fast** trades key accuracy for speed on large batches — see
  [Analysis speed](#analysis-speed).
- **Columns ▾** lets you check/uncheck which metrics are shown; the choice is
  remembered between sessions. Hover any column header for what it means.
- **Facets ▾** switches the vocabulary (English / Tango) and picks which axes
  to compare over. Each ticked axis adds a `≡` column you can sort on, plus a
  `Facets` column with the composed phrase. Both choices persist.
- Right-click selected rows to re-analyze them as a specific rhythm or remove them.
- **Write tags…** writes results into the files (only on request, never automatically):
  - `BPM` and `INITIALKEY` — the standard fields VirtualDJ imports from tags,
  - `COMPAS_*` fields — energy, drive, articulation, texture, harmony, voice,
    stability, timing, BPM range, bars/min,
  - `COMPAS_FACETS` — the composed phrase in the vocabulary and axes you
    currently have selected, which is the form worth browsing on in VirtualDJ,
  - optional `COMPAS Energy N` note **appended** to the comment (existing comment text is preserved).
- **Export CSV / JSON** for the whole session.

### Standalone executables (no Python needed)

```
packaging\build_windows.bat        → dist\COMPAS\COMPAS.exe   (run on Windows)
bash packaging/build_macos.sh      → dist/COMPAS.app          (run on a Mac)
```

Both use the shared PyInstaller spec `packaging/compas.spec`. The output is a
folder (`dist\COMPAS\`) — ship the whole folder (zip it); the exe inside won't
run alone. A Mac app cannot be cross-built from Windows; either run the script
on a Mac, or push the repo to GitHub and run the **Build executables** workflow
(`.github/workflows/build.yml`), which builds Windows + macOS (Apple Silicon
and Intel) and uploads them as downloadable artifacts. Unsigned macOS apps
need right-click → Open on first launch (or
`xattr -dr com.apple.quarantine COMPAS.app`).

### VirtualDJ integration (works today, no plugin needed)

1. Analyze your files and use *Write tags…* (keep BPM + key checked).
2. In VirtualDJ's browser, right-click the tracks → **File Info → Load tags from file** (or enable tag reading in Options), so VDJ's BPM/Key columns use the tag values.
3. Energy: enable the *Comment* column (if you used the comment option), or map a custom field.

## CLI

```
C:\Users\seric\.venvs\compas\Scripts\python compas_cli.py example_songs
python compas_cli.py my_folder --rhythm auto --csv out.csv --json out.json
python compas_cli.py my_folder --fast --csv out.csv
python compas_cli.py song.flac --write-tags --key-format camelot

python compas_cli.py . --list-axes                    # the facet axes
python compas_cli.py my_folder --facets tango         # tango vocabulary
python compas_cli.py my_folder --facet-axes tempo,drive,articulation,texture,vocal
python compas_cli.py my_folder --facets off           # numbers only
```

## Analysis speed

Measured on the 19-track example corpus (55 minutes of audio, 8-core machine,
4 worker threads — what the GUI uses):

| mode | per track | corpus | ×realtime |
|---|---|---|---|
| default | 3.6 s | 68 s | 49× |
| `--fast` / **Fast** | 1.1 s | 20 s | 164× |

Nearly all of the difference is one step. Harmonic/percussive separation is
**~75% of a track's analysis time**, and the only things that read its output
are the key estimate and harmonic variety — every other metric is computed
from the full mix. Fast mode skips it and works from the full mix instead, so
BPM, range, stability, timing, drive, sync, **articulation, texture, voice**,
energy and loudness are bit-identical either way; only Key, Camelot and
Harmony can move.

**The four new metrics cost 0.18 s/track between them** — 8% of fast mode, 2%
of default — measured single-threaded on the example corpus:

| stage | s/track |
|---|---|
| vocal presence | 0.12 |
| texture + articulation | 0.05 |
| harmonic variety | <0.01 |

That is cheap for two deliberate reasons. Texture uses spectrogram anisotropy
rather than a full HPSS split — Spearman 0.74 against the real thing for
0.09 s/track against 6.7 — and articulation, drive and texture now share one
magnitude STFT, while the key and harmony chromas share one constant-Q
transform. The shared CQT is bit-identical to the two separate calls it
replaced, which is what keeps the key results from moving.

How much they move: on the example corpus, 3 tracks of 19 got a different key,
and accuracy against the Mixed In Key labels went 5/9 → 4/9 — one label lost,
one gained, i.e. no measurable difference on a corpus this small. Cheaper
middle grounds were tried (smaller FFT, coarser hop, smaller median kernel,
separating in the CQT domain) and none of them held all 19 keys, so there is
no free lunch here — it is a genuine speed-for-key-confidence trade.

Since the library already carries Mixed In Key tags (surfaced in the
**Tag BPM/key** column), fast mode is usually the right default for bulk runs;
leave it off when COMPAS's own key is the number you care about.

Threading scales sub-linearly — 1/2/4/6 workers take 217/111/68/59 s in default
mode — because each track is already partly vectorised. The pool is capped at
`min(4, cores-1)`.

## Project layout

```
compas_core/       analysis library (shared by GUI, CLI, and future plugin)
  audio.py         decoding (soundfile, ffmpeg fallback)
  rhythm.py        tango/vals/milonga specs, tempo priors, genre mapping
  tempo.py         tempogram-based local tempo, stability, beat tracking
  key.py           key + Camelot + confidence
  energy.py        drive, syncopation, dynamic range, energy composite
  texture.py       articulation, melodic/percussive texture
  harmony.py       harmonic variety (provisional)
  vocal.py         instrumental / estribillo / vocal
  facets.py        axes, English + tango vocabularies, composed labels
  loudness.py      EBU R128 LUFS / LRA
  tags.py          tag read/write (FLAC, MP3, MP4)
  analyze.py       analyze_file() orchestration
compas_gui/        PySide6 app (drag-drop table, tag writer, exports)
compas_cli.py      batch CLI
scripts/
  validate_vocal.py     score the vocal detector on filename ground truth
  calibrate_facets.py   re-fit facet thresholds from a library CSV
```

Setup from scratch:

```
python -m venv C:\Users\seric\.venvs\compas
C:\Users\seric\.venvs\compas\Scripts\pip install numpy scipy librosa soundfile mutagen pyloudnorm PySide6
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
