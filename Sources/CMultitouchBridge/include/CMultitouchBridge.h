#ifndef CMultitouchBridge_h
#define CMultitouchBridge_h

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct HMTrackpad HMTrackpad;

typedef struct {
    int32_t identifier;
    int32_t state;
    double x;
    double y;
} HMTouchContact;

typedef void (*HMTouchFrameCallback)(
    const HMTouchContact *contacts,
    int32_t count,
    double timestamp,
    void *context
);

bool HMTrackpadFrameworkAvailable(void);
HMTrackpad *HMTrackpadCreate(HMTouchFrameCallback callback, void *context, char **errorMessage);
bool HMTrackpadStart(HMTrackpad *trackpad, char **errorMessage);
void HMTrackpadStop(HMTrackpad *trackpad);
void HMTrackpadDestroy(HMTrackpad *trackpad);
void HMTrackpadFreeError(char *errorMessage);

#ifdef __cplusplus
}
#endif

#endif
