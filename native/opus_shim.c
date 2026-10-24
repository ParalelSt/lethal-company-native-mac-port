// Opus for Dissonance on macOS: libopus statically linked, plus the four
// non-variadic ctl wrappers Dissonance's custom opus build exports.
#include <opus/opus.h>
#define EXPORT __attribute__((visibility("default")))
EXPORT int dissonance_opus_encoder_ctl_in(OpusEncoder *st, int request, int value) { return opus_encoder_ctl(st, request, value); }
EXPORT int dissonance_opus_encoder_ctl_out(OpusEncoder *st, int request, int *value) { return opus_encoder_ctl(st, request, value); }
EXPORT int dissonance_opus_decoder_ctl_in(OpusDecoder *st, int request, int value) { return opus_decoder_ctl(st, request, value); }
EXPORT int dissonance_opus_decoder_ctl_out(OpusDecoder *st, int request, int *value) { return opus_decoder_ctl(st, request, value); }
