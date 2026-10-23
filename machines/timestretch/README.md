# Timestretch sample engine

Timestretch plays samples in time with the project, using either repitching or
pitch-preserving Capicola-derived timestretch. Each drum pad has its own
sample and settings. Retriggering a pad chokes its previous voice; other pads
and tracks keep playing. New presets use zero amp decay and release.

The stock drum page supplies the waveform, trim markers and graphics:

| Encoder | Main page | Shift |
| --- | --- | --- |
| 1 | Pitch, -12 to +12 semitones in 0.1 steps; press resets | Stock reverse control and icon |
| 2 | Sample start | Loop length or source BPM; press switches between them |
| 3 | Sample end | `repitch` or `timestretch`; press toggles |
| 4 | Loop or play once; press toggles | Stock volume control and glyph |

The factory page retains its saved-pad and live-track editing routes. Live
pitch adds up to 12 semitones in either direction to the pad's pitch, including
fractional semitones. Both pad edits and live/step edits use 0.1-semitone
increments. Pad pitch is stored in stock root/fine-tuning fields.
Live start/end controls move the saved markers toward
the sample boundaries. The display and audio use the same effective settings.
Live play and stretch controls have a middle `pad` position that inherits the
saved mode; reverse toggles the saved direction, and volume attenuates it.
Live tempo offsets the saved source BPM or bar selection.

The bundled preset centers pitch, start, end, play, tempo and mode, disables
live reverse and sets live volume to unity. Load this preset on a fresh track
when testing; previously saved tracks retain their stored parameter values.

Replacing a sample retains the pad's pitch, reverse, volume, loop/play and
repitch/timestretch settings. A valid BPM in the new filename updates source
BPM; otherwise the previous BPM or bar selection stays in place. Empty pads
start from the assignment defaults.
The stock sample recorder also assigns completed external-input recordings to
the selected pad. Recording over a pad retains its playback settings and starts
with full-sample trims. Recordings switch to source-BPM mode using the current
project tempo at assignment, rounded to the nearest whole BPM. They retain the
pad's loop/play and repitch/timestretch modes and do not import BPM from the file browser.
New assignments span the full loaded sample. Trim positions use the waveform
markers rather than numeric labels. Playback follows these outer start/end
markers; hidden sampler loop markers do not constrain them.
Length choices are 1/4, 1/2, 1, 2, 4 and
8 bars in 4/4. Source BPM is an integer from 20 to 300. Switching from bars
to BPM starts at 120; returning to bars starts at one bar. Correct the length
or source BPM before judging stretch quality. Pitch changes are independent
of loop speed in timestretch mode; they also change speed in repitch mode.
The +/- octave buttons retain the same pad's sample and change playback pitch
by 12 semitones per press, separately from the saved pad pitch. Empty pads
start with zero pad pitch.
Track settings transpose (-36 to +36 semitones) also adds to saved pad and
live/step pitch in both modes. The combined pitch is limited to -60 to +60
semitones. Retriggering the same pad at another octave chokes its prior voice.

For automatic source BPM, put exactly three digits at the beginning or end of
the filename, separated by a space, underscore or hyphen: `095_guitar.wav`
or `guitar_095.wav`. Only 020 through 300 are accepted. Conflicting values at
both ends are ignored. Directory names and numbers inside a name are ignored.
Without this convention, Timestretch suggests a length from duration and project
tempo; this does not detect beats in the audio.

Committed samples are analyzed on the stock file worker, one at a time. Scrolling the
browser does not start analysis; the shared progress overlay reports preparation
after assignment. Playback reads the original PCM with linear interpolation;
an immutable keyframe grid supplies adaptive splice timing. It is not a fully
prerendered audio cache. Repitch can
play while analysis is pending; timestretch waits for completed analysis.
The shared analysis cache has a 2 MiB limit and reports failures or exhaustion.
The stock loader's 882,000-frame limit still applies (20 seconds at 44.1 kHz).

`sample.cpp` and the control callbacks are portable C++ using the
[sample engine API](../../docs/api.md#sample-engines). The machine declares
analysis, same-key choke and drum controls in `definition.json`. The SDK owns
native addresses, registration, sample lifetime, analysis scheduling, control
dispatch and stock graphics. Adding another machine using these services
does not add firmware patch sites. Timestretch uses engine 35 and stock page 7.

Both repitch and timestretch retain stereo. Timestretch analyzes each channel
separately and shares playhead positions and crossfades, using the more active
channel to choose splice timing. Mono samples play equally on both sides.
Pitch changes also scale the crossfade speed, as in upstream Capicola.
Stereo analysis counts both channels against the shared cache budget.

The fixed-point adaptation uses integer derivative-crossing positions with
a 0.001 amplitude-change threshold to select grain placement and crossfade
duration. Keyframes do not store or reconstruct the audible waveform.
Stereo PCM shares interpolation positions and fade weights. The upstream
hardware UI and live-input processing are not included; the stock recorder
supplies completed audio files. See the
[upstream revision and AGPL notices](vendor/README.md).
