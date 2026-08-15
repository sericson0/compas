# COMPAS — Tango Music Analyzer

Musical feature analysis for Argentine tango DJs and dancers: **BPM, key,
energy, rubato, articulation and texture** for tango, vals, and milonga, with a GUI, a CLI, tag-based integration with VirtualDJ (or any DJ
software that reads tags), and a **facet grid** that turns the numbers into
words in English or tango vocabulary.

## What it measures

| Metric | Meaning |
|---|---|
| **BPM** | Median beat-level tempo. The rhythm type constrains the plausible range, so a vals lands at ~205 quarter-note BPM instead of a half/double-tempo error. |
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
                                       rhythm      bpm stab  key enrg drv snc art tex hrm   LRA
Biagi - El Incendio - 1938             tango     130.8   95   Am  7.0  99  19  95  63  12   5.7
Canaro - Hotel Victoria - 1935         tango     119.5   95   D#  5.0  73  43  48  33  35   4.6
D'Arienzo - Amarras - 1944             tango     122.4   86    A  4.6   6  47  23  58  49   7.0
D'Arienzo - El Flete - 1936            tango     133.1   94    E  6.3  78  40  83  48  67   6.7
Di Sarli - El Amanecer - 1942          tango     123.0   95    G  4.7  18  57  36  36  69  10.9
Di Sarli - Nada - 1944                 tango     121.6   73    C  3.4   7  52  23  62  47   7.0
Donato - Carnaval De Mi Barrio - 1939  tango     136.5   94   Bm  6.4  75  37  72  72  41   5.8
Malerba - Gitana Rusa - 1942           tango     117.9   79    A  3.7  33  25  48  78  23   7.1
Pugliese - Alma De Bohemio - 1958      tango     122.3   48   Am  4.4  33  49  23  40  68  12.2
Pugliese - El Adios - 1963             tango     123.3   47   Dm  3.9  16  46  33  78  38  13.2
Troilo - Danzarin - 1963               tango     124.5   52    G  3.7  21  45  24  28  63   7.0
Troilo - Toda Mi Vida - 1941           tango     132.5   92    A  5.5  38  50  69  62  55   8.3
De Angelis - Mi Novia De Ayer - 1944   vals      213.8   90   A#  6.0  47  40  23  59  33   5.1
Laurenz - Paisaje - 1943               vals      210.6   81    A  5.2  43  34  30  61  66   6.0
Rodriguez - Tengo Mil Novias - 1939    vals      203.5   93    G  5.8  75  19  62  73  37   5.9
Victor - Temo - 1940                   vals      219.3   90   Am  5.7  61  43  17  47  45   5.1
Canaro - Silueta Portena - 1936        milonga   112.9   84  D#m  5.8  61  27  38  39  33   5.5
D'Arienzo - Milonga Del Corazon - 1938 milonga   108.8   83    G  5.1  18  64  20  57  65   7.1
Laurenz - Milonga De Mis Amores - 1944 milonga   103.8   89    A  4.7  13  64  28  46  45   5.8
```

BPM range, timing and LUFS are omitted here for width; the CLI and GUI show
them all.

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
Biagi - El Incendio - 1938             fast driving            rápido rítmico
Canaro - Hotel Victoria - 1935         slow driving            lento rítmico
Pugliese - El Adios - 1963             flexible                fraseo
Troilo - Danzarin - 1963               flexible                fraseo
Laurenz - Milonga De Mis Amores - 1944 slow smooth             lento melódico
```

The same tracks with articulation and texture switched on as well:

```
Biagi - El Incendio - 1938             fast driving staccato
Canaro - Hotel Victoria - 1935         slow driving sustained
Pugliese - El Adios - 1963             percussive flexible
Troilo - Danzarin - 1963               legato sustained flexible
Laurenz - Milonga De Mis Amores - 1944 slow smooth
```

The composed label skips any axis on which a track is unremarkable, so it
reads "fast driving instrumental" rather than "fast driving mixed balanced
steady instrumental". The per-axis columns still show every level.

| Axis | English | Tango | From |
|---|---|---|---|
| Tempo * | slow / medium / fast | lento / medio / rápido | BPM ÷ the rhythm's typical BPM |
| Character * | smooth / balanced / driving | melódico / intermedio / rítmico | Drive |
| Articulation | legato / detached / staccato | ligado / medio / picado | Artic |
| Texture | sustained / mixed / percussive | lírico / equilibrado / percusivo | Texture |
| Placement | straight / mixed / syncopated | liso / medio / sincopado | Sync |
| Phrasing * | steady / flexible | compás / fraseo | Timing |
| Harmony | simple / moderate / complex | directo / elaborado / complejo | Harmony |
| Lift | gentle / moderate / lively | suave / medio / enérgico | Energy |
| Dynamics | even / dynamic / dramatic | parejo / dinámico / dramático | LRA |
| Mode | major / minor | mayor / menor | Key |

`*` = on by default. Tempo is deliberately **genre-relative**, so a vals at
210 BPM is not automatically "fast".

Two things worth being clear about:

1. **A facet is a view of a column, not a new measurement.** Nothing here is
   computed that is not already in the table. A label that reads wrong is a
   threshold to argue with, and the number it came from is in the next
   column over.
2. **The thresholds are calibrated, not universal.** They are the 25th and
   75th percentiles of an 11,948-track library, so half of that collection
   reads as unremarkable on any given axis and a quarter earns each outer
   word. A collection weighted differently — heavy on Canaro, or on
   post-war material — will want its own; see
   [Calibrating on your own library](#calibrating-on-your-own-library).

## Vocal presence (currently DISABLED)

> **This feature is switched off.** It is commented out in
> `compas_core/analyze.py`, `facets.py`, `compas_gui/model.py` and
> `compas_cli.py` — each site marked the same way — while
> `compas_core/vocal.py` and its two scripts stay intact. The reason is the
> table below: it only earns its keep on tango from 1940-1959, and on vals
> and milonga it does not beat guessing the majority class. Since a library
> that marks instrumentals in the filename already knows the answer for
> those, it was not paying for its 0.12 s/track. The write-up is kept
> because the negative results in it are the useful part.
>
> To switch it back on, uncomment the five `TrackAnalysis` fields in
> `analyze.py` and follow the four matching notes.


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

### How well it actually works

Scored on an **11,948-track library** whose filenames carry ground truth —
3,421 marked "Instrumental" against 8,527 not, a 71% base rate.

**Overall: d′ = 1.03, 80% correct.** Nine points over the base rate, and a
long way below what the 19-track example corpus advertised (d′ = 2.0). The
small corpus was not wrong so much as unrepresentative: it is all 1935–1963
material, which is exactly where this method works.

The averages hide the thing that matters, which is that accuracy depends
strongly on era and on rhythm:

| era | n | d′ | correct | | rhythm | n | d′ | correct | base |
|---|---|---|---|---|---|---|---|---|---|
| pre-1930 | 1296 | +0.43 | 66% | | tango | 9896 | +1.26 | 80% | 69% |
| 1930–34 | 1000 | +0.82 | 86% | | vals | 1126 | +0.23 | 85% | 85% |
| 1935–39 | 983 | +0.59 | 78% | | milonga | 926 | +0.98 | 84% | 84% |
| **1940–44** | 2298 | **+1.71** | **91%** |
| **1945–49** | 1397 | **+2.49** | **93%** |
| **1950–59** | 2103 | **+2.23** | **91%** |
| 1960+ | 2762 | +0.44 | 76% |

Read that as: **trust it on tango from 1940–1959**, treat it as a hint
elsewhere, and note that on **vals and milonga it barely beats guessing** —
those repertoires are 84–85% vocal to begin with, so there is little for it
to add.

Two caveats on the table itself. The 1960+ row is polluted by reissue dates:
the library's tags run to 2023, so remastered golden-age sides land there.
And "vocal" only means "the filename does not say instrumental", so an
untagged instrumental counts as a detector error when it is really a
labelling gap.

Also worth knowing:

- **The band and the statistic were tuned on real data, not the corpus.** A
  grid over both, scored separately on early and golden-age material, moved
  the window from 200–3000 Hz to **150–2000 Hz** and the statistic from the
  70th to the **85th percentile**. That improved every slice at once (early
  d′ 0.74→0.96, golden-age 1.99→2.20). Above ~2 kHz a shellac transfer is
  mostly surface noise, so the wider band was adding noise rather than
  formants; the higher percentile catches singers who only take a refrain.
- **The failure mode is musically coherent**: a cantabile instrumental solo
  looks like a singer, and the early era is full of them.
- **A filename beats the audio.** Where the title says "Instrumental" that
  answer is used and the audio estimate is only reported, exactly as a GENRE
  tag overrides the rhythm heuristic. The rule is one-directional: the word
  being present is reliable, its absence proves nothing.
- **`estribillo` is untested, not merely provisional.** No labelled refrain
  set exists, so the cut is set where a library produces none — it fires on
  0% of the 11,948. Read "estribillo" as "vocal, possibly brief".

To score it on your own library:

```
python scripts/validate_vocal.py D:\Tango
python scripts/validate_vocal.py library.csv     # from analyze_library.py
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

It was also the worst-anchored metric: on 11,948 tracks the original
`VARIETY_ANCHORS` saturated **21% of the library at 100**, i.e. a fifth of
it was reported as equally, maximally varied. The anchors are now fitted to
that library, but the underlying doubt stands.

## Calibration: what 11,948 tracks changed

The thresholds and anchors that ship were fitted on a real discography
(11,948 files, 142 GB, 1916–2023, median year 1945). The 19-track versions
they replaced were wrong nearly everywhere:

| axis | 19 tracks | 11,948 tracks |
|---|---|---|
| drive | (30, 60) | **(16, 50)** |
| articulation | (25, 55) | (27, 55) |
| texture | (35, 65) | (41, 70) |
| syncopation | (35, 55) | (39, 51) |
| harmony | (45, 80) | (45, 72) |
| energy | (4.5, 6.0) | (4.0, 5.2) |
| dynamics | (6.0, 9.0) | (5.6, 8.6) |

And the anchors underneath them, which were clipping badly:

| anchor | was | now | clipped |
|---|---|---|---|
| `ATTACK_ANCHORS` | (2.5, 9.0) | (1.45, 8.27) | 8.2% at 0 |
| `RELEASE_ANCHORS` | (3.0, 8.5) | (2.39, 8.87) | 4.4% at 0 |
| `PERCUSSIVE_ANCHORS` | (0.385, 0.48) | (0.346, 0.511) | 6.9% at 0, 9.7% at 100 |
| `VARIETY_ANCHORS` | (6.5, 9.0) | (6.28, 9.95) | **20.6% at 100** |

Three things that generalise beyond this particular library:

1. **Anchors and thresholds must be re-fitted together.** The thresholds are
   percentiles *of the scale the anchors define*, so changing one without
   the other silently reclassifies everything. Correcting the anchors moved
   the harmony cuts from (64, 89) to (45, 72) — same data, different scale.
2. **A small corpus flatters a metric it was fitted on.** Every headline
   number here got worse under real data, the vocal detector most of all.
3. **The rhythms want their own cuts.** Median drive runs milonga 12 /
   tango 32 / vals 23; median harmony 59 / 79 / 64. One set for all three is
   a compromise, and a large collection would justify splitting them.

## Calibrating on your own library

The shipped thresholds come from an 11,948-track library (see
[Calibration](#calibration-what-11948-tracks-changed)). To re-fit them on
yours:

```
python scripts/analyze_library.py D:\Tango --csv library.csv --fast
python scripts/calibrate_facets.py library.csv --split 25 75 --per-rhythm
python scripts/validate_vocal.py library.csv
```

Use `analyze_library.py` rather than the CLI for anything large. It writes
each row as it completes, resumes on a re-run (just run the same command
again), survives individual failures, and **shuffles the work list** so that
any partial CSV is a representative sample of the library rather than
everything alphabetically before "Canaro" — which is what makes it possible
to calibrate off a partial run instead of waiting hours for the end.

The GUI is resumable too now (it autosaves results as they land and restores
them on the next launch), so it is a reasonable way to work through a large
library in sittings. `analyze_library.py` is still the right tool when the
goal is *calibration* specifically, for the shuffling: it is the only one of
the three that makes a partial run representative.

`calibrate_facets.py` works in two steps, and the order matters:

1. **Anchors** — the constants that map a raw measurement onto 0–100. Too
   narrow and the score pins at 0 or 100 for a slice of the library, which
   is resolution thrown away exactly where the cuts need it.
2. **Thresholds** — percentiles *of the scale those anchors define*. This
   is why the script re-fits both in one pass: change an anchor without the
   threshold and the label silently means something else.

`--per-rhythm` is worth reading. The three rhythms do not share a
distribution — median drive runs milonga 12 / tango 32 / vals 23 and median
harmony 59 / 79 / 64 — so one set of cuts for all three is a deliberate
compromise that a large enough collection would justify splitting.

If you change the vocal detector itself, `scripts/rescore_vocal.py` updates
only the five vocal columns of an existing CSV. Everything the detector
needs beyond the audio is the tempo, which is already in the file, so
retuning costs about twenty minutes on twelve thousand tracks instead of a
full re-analysis.

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
- **Columns ▾** shows or hides any column, metric or facet; the choice is
  remembered between sessions. Hover any column header for what it means, or
  read them all in **Help ▸ What the columns mean**. Seven secondary columns
  (`BPM range`, `Bars/min`, `Camelot`, `Tag BPM/key`, `LUFS`, `LRA`, `Harmony`)
  start hidden so the table fits a normal window; tick them back on here.
  Window size and column widths are remembered too. Wide headers are painted
  abbreviated (`Stab`, `Tex`, `≡ Char`); the full name is in the tooltip and
  in the Columns menu. `Status` sits second so you can see the run's progress
  without scrolling.
- **Filter box** (Ctrl+F) narrows the list to matching tracks. It matches the
  filename, rhythm, key, status, the facet readings and any error message, so
  `milonga`, `Dm`, `driving` and `ffmpeg` all work. **View ▸ Show only failed
  tracks** (Ctrl+Shift+F) collects the failures after a big run.
  Filtering only changes what you see — Analyze and Write tags always act on
  the whole list, and the status bar says so while a filter is active.
- **Facets ▾** switches the vocabulary (English / Tango) and picks which axes
  to compare over. Each ticked axis adds a `≡` column you can sort on, plus a
  `Facets` column with the composed phrase. Both choices persist.
- Right-click selected rows to re-analyze them as a specific rhythm or remove them.
- **Write tags…** writes results into the files (only on request, never automatically):
  - `BPM` and `INITIALKEY` — the standard fields VirtualDJ imports from tags,
  - `COMPAS_*` fields — energy, drive, articulation, texture, harmony,
    stability, timing, BPM range, bars/min,
  - `COMPAS_FACETS` — the composed phrase in the vocabulary and axes you
    currently have selected, which is the form worth browsing on in VirtualDJ,
  - optional `COMPAS Energy N` note **appended** to the comment (existing comment text is preserved).

  The dialog names the files it is about to touch, and says how many of them
  already carry a BPM or key tag from another tool — those two fields are the
  only ones that overwrite anything. Untick them to leave a Mixed In Key
  library alone. It acts on the selected tracks when the selection contains
  analyzed ones, and on everything analyzed otherwise; the heading says which.
- **Export CSV / JSON** for the whole session, including the facet columns and
  the composed phrase.
- **Your session is saved as it goes.** The track list and every result are
  written to `%APPDATA%\compas\COMPAS\session.json` as each track finishes, and
  restored on the next launch — closing the window mid-run no longer throws
  away half an hour of analysis. Tracks that were still in flight come back as
  pending, so Analyze picks up where it left off. *Clear all* discards the
  saved session too (and asks first, if anything has been analyzed). Only the
  measured numbers are stored: facet readings and the composed phrase are
  recomputed on load, so recalibrated thresholds apply to old results.
- **Long runs report a time estimate.** The status bar shows
  `Analyzing… 143/500 done (4 in flight) · ≈12 min left`, measured from the
  run's own recent throughput, with a progress bar beside it and the
  percentage in the window title so a minimised window still says how far
  along it is.

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
python compas_cli.py my_folder --facet-axes tempo,drive,articulation,texture
python compas_cli.py my_folder --facets off           # numbers only

# Tag writing is field-by-field, as in the GUI dialog. --no-bpm/--no-key keep
# what Mixed In Key already wrote; --comment appends "COMPAS Energy N" to the
# comment without touching the existing text.
python compas_cli.py my_folder --write-tags --no-bpm --no-key
python compas_cli.py my_folder --write-tags --no-bpm --no-key --comment
python compas_cli.py my_folder --write-tags --no-compas --comment
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
BPM, range, stability, timing, drive, sync, **articulation and texture**,
energy and loudness are bit-identical either way; only Key, Camelot and
Harmony can move.

**The new metrics cost 0.06 s/track between them** — measured
single-threaded on the example corpus:

| stage | s/track |
|---|---|
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
  vocal.py         instrumental / estribillo / vocal (DISABLED)
  facets.py        axes, English + tango vocabularies, composed labels
  loudness.py      EBU R128 LUFS / LRA
  tags.py          tag read/write (FLAC, MP3, MP4)
  analyze.py       analyze_file() orchestration
compas_gui/        PySide6 app (drag-drop table, tag writer, exports)
compas_cli.py      batch CLI
scripts/
  analyze_library.py    resumable, parallel, shuffled whole-library run
  calibrate_facets.py   re-fit anchors + facet thresholds from a library CSV
  validate_vocal.py     score the vocal detector on filename ground truth
  rescore_vocal.py      recompute only the vocal columns of a library CSV
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
- Beat-level tempo priors: tango 100–145, vals 155–235, milonga 85–135 BPM.
  Adjust in `compas_core/rhythm.py` if your collection disagrees.
