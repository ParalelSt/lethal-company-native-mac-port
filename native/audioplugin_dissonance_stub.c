// Stand-in for the closed-source AudioPluginDissonance native plugin (no macOS build available).
// Pass-through preprocessor: no noise suppression / AEC, VAD reports speech when the frame has energy.
// Signatures mirror Dissonance.Audio.Capture.AudioPluginDissonanceNative (DissonanceVoip.dll).
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <math.h>
#define EXPORT __attribute__((visibility("default")))

typedef struct { int sampleRate; int vad; float vadThreshold; } Preproc;
typedef struct { int dummy; } Rnn;

EXPORT void *Dissonance_CreatePreprocessor(int nsLevel, int aecLevel, int aecDelayAgnostic, int aecExtended, int aecRefined, int aecmRoutingMode, int aecmComfortNoise) {
    Preproc *p = (Preproc *)calloc(1, sizeof(Preproc)); p->vad = 1; p->vadThreshold = 0.0005f; return p;
}
EXPORT void Dissonance_DestroyPreprocessor(void *h) { free(h); }
EXPORT void Dissonance_ConfigureNoiseSuppression(void *h, int nsLevel) {}
EXPORT void Dissonance_ConfigureAecSuppression(void *h, int aecLevel, int aecmRouting) {}
EXPORT void Dissonance_ConfigureVadSensitivity(void *h, int level) {
    Preproc *p = (Preproc *)h; if (!p) return;
    static const float t[] = { 0.0002f, 0.0005f, 0.001f, 0.002f };
    p->vadThreshold = (level >= 0 && level < 4) ? t[level] : 0.0005f;
}
EXPORT void Dissonance_SetAgcIsOutputMutedState(void *h, int muted) {}
// Dissonance feeds 10 ms frames: sampleRate/100 samples. Copy input -> output.
EXPORT int Dissonance_PreprocessCaptureFrame(void *h, int sampleRate, const float *input, float *output, int streamDelay) {
    Preproc *p = (Preproc *)h; if (!p || !input || !output) return -5; /* NullPointer */
    int n = sampleRate / 100; if (n <= 0) return -7; /* BadSampleRate */
    double e = 0; for (int i = 0; i < n; i++) { output[i] = input[i]; e += (double)input[i] * input[i]; }
    p->vad = (e / n) > p->vadThreshold; return 0; /* Ok */
}
EXPORT int Dissonance_GetVadSpeechState(void *h) { Preproc *p = (Preproc *)h; return p ? p->vad : 0; }
EXPORT int Dissonance_PreprocessorExchangeInstance(void *previous, void *replacement) { return 1; }
EXPORT int Dissonance_GetFilterState(void) { return 0; /* FilterNotRunning: no AEC mixer effect */ }
EXPORT void Dissonance_GetAecMetrics(float *buf, int len) { if (buf && len > 0) memset(buf, 0, sizeof(float) * (size_t)len); }
EXPORT void *Dissonance_CreateRnnoiseState(void) { return calloc(1, sizeof(Rnn)); }
EXPORT void Dissonance_DestroyRnnoiseState(void *s) { free(s); }
EXPORT int Dissonance_RnnoiseProcessFrame(void *s, int count, int sampleRate, const float *input, float *output) {
    if (!input || !output || count <= 0) return 0; if (input != output) memcpy(output, input, sizeof(float) * (size_t)count); return 1;
}
EXPORT int Dissonance_RnnoiseGetGains(void *s, float *output, int length) { if (output) for (int i = 0; i < length; i++) output[i] = 1.0f; return length; }
// Unity native audio plugin entry point: register zero mixer effects so the AudioMixer loads cleanly.
EXPORT int UnityGetAudioEffectDefinitions(void ***defs) { if (defs) *defs = NULL; return 0; }
