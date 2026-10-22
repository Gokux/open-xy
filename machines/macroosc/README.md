# Macro Osc

47 Braids oscillator models by Emilie Gillet, adapted to the SDK's explicit
lifecycle and segment display. The [vendor license](vendor/LICENSE) and
[source provenance](vendor/VENDOR.md) remain with the port.

Four controls: **Model**, **Timbre**, **Color**, **Finetune**. Timbre/Color retain
each model's upstream meaning. Finetune spans roughly a semitone either side
of center. The complete model/code/label list is in [models.hpp](models.hpp).
The screen shows the model code on four glowing 14-segment characters and one
knob per control; the Model knob steps between models.

```sh
python sdk.py preview --engine macroosc --out local/macro-preview-001
python tools/serve_harness.py --preview local/macro-preview-001
python sdk.py check
```

| File | Owns |
| --- | --- |
| [definition.json](definition.json) | Controls and resource declarations |
| [core.h](core.h), [engine.cpp](engine.cpp) | Voice/shared state, lifecycle and sound |
| [display.cpp](display.cpp), [models.hpp](models.hpp) | Model-to-segment frame and model table |
| [pitch.h](pitch.h), [vendor/braids/resources.cc](vendor/braids/resources.cc) | 44.1 kHz pitch and Braids tables |
| [machine.json](machine.json) | Kind, display and the vendored translation units |

The SDK supplies storage, callbacks and rendering backends. Callbacks and the
vendor RNG swap require serialized access. See [engine API](../../docs/api.md).

## Port fidelity

Tables are regenerated for 44.1 kHz; Braids originally runs at 96 kHz. Delay-line
lengths are halved. Table-driven pitch/filter data use the new rate, but
hard-coded per-sample/per-block decay constants retain their upstream values,
so some decays are about 2.18 times slower and fixed filters lower. Half-rate
models run at 22.05 kHz; naive digital waveforms alias more. Pitch updates occur
at samples 0, 24 and 48 of each 64-sample callback. Oversampling is not implemented.

The module AD envelope, bit/rate reduction, signature waveshaper, quantizer and
VCO drift are not ported. Stock processing remains downstream on the device;
the browser has a simple audition gate.

## Native notes

Model selects `((q31 >> 16) * 47) >> 15`, clamped to 0..46. Timbre and Color
use 0..32767. Finetune is `((q31 >> 16) - 16384) >> 7` in 1/128 semitone, so
50% is in tune. Changing model restrikes the oscillator. Render produces
24 + 24 + 16 Braids samples per 64-sample block and scales int16 output to
half-scale Q31.

Five models (SAW_COMB, PLUK, BOWD, BLOW, FLUT) lease an 8,200-byte delay line
from a shared pool of 16. When the pool is full the oldest lease is stolen and
its voice falls silent until restruck.
