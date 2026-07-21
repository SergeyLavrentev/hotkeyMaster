#include "CMultitouchBridge.h"

#include <CoreFoundation/CoreFoundation.h>
#include <dlfcn.h>
#include <math.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>

typedef struct { float x; float y; } MTPoint;
typedef struct { MTPoint pos; MTPoint vel; } MTReadout;
typedef struct {
    int32_t frame;
    double timestamp;
    int32_t pathIndex;
    uint32_t state;
    int32_t fingerID;
    int32_t handID;
    MTReadout normalized;
    float size;
    int32_t pad2;
    float angle;
    float major;
    float minor;
    int32_t pad3[5];
} MTFinger;

_Static_assert(offsetof(MTFinger, normalized) == 32, "Unexpected MTFinger layout");

enum {
    MTTouchStateMakeTouch = 3,
    MTTouchStateTouching = 4,
    MTTouchStateBreakTouch = 5,
};

typedef CFArrayRef (*MTDeviceCreateListFn)(void);
typedef void (*MTFrameCallbackFn)(void *, MTFinger *, size_t, double, size_t);
typedef void (*MTRegisterContactFrameCallbackFn)(void *, MTFrameCallbackFn);
typedef void (*MTUnregisterContactFrameCallbackFn)(void *, MTFrameCallbackFn);
typedef void (*MTDeviceStartFn)(void *, int);
typedef void (*MTDeviceStopFn)(void *);

struct HMTrackpad {
    void *framework;
    CFArrayRef devices;
    CFIndex deviceCount;
    HMTouchFrameCallback callback;
    void *context;
    MTRegisterContactFrameCallbackFn registerCallback;
    MTUnregisterContactFrameCallbackFn unregisterCallback;
    MTDeviceStartFn deviceStart;
    MTDeviceStopFn deviceStop;
    bool started;
};

static HMTrackpad *activeTrackpad = NULL;

static void setError(char **errorMessage, const char *message) {
    if (errorMessage == NULL) return;
    *errorMessage = strdup(message != NULL ? message : "Unknown MultitouchSupport error");
}

static void *openFramework(void) {
    return dlopen(
        "/System/Library/PrivateFrameworks/MultitouchSupport.framework/MultitouchSupport",
        RTLD_NOW | RTLD_LOCAL
    );
}

bool HMTrackpadFrameworkAvailable(void) {
    void *handle = openFramework();
    if (handle == NULL) return false;
    dlclose(handle);
    return true;
}

static void contactFrameCallback(void *device, MTFinger *fingers, size_t count, double timestamp, size_t frame) {
    (void)device;
    (void)frame;
    HMTrackpad *trackpad = activeTrackpad;
    if (trackpad == NULL || trackpad->callback == NULL) return;

    const size_t inputCount = count > 32 ? 32 : count;
    HMTouchContact contacts[32];
    int32_t outputCount = 0;
    for (size_t index = 0; index < inputCount; index++) {
        int32_t canonicalState;
        switch (fingers[index].state) {
        case MTTouchStateMakeTouch:
            canonicalState = 1;
            break;
        case MTTouchStateTouching:
            canonicalState = 2;
            break;
        case MTTouchStateBreakTouch:
            canonicalState = 4;
            break;
        default:
            // Hover/range phases are not physical contact and must not start a tap.
            continue;
        }
        contacts[outputCount].identifier = fingers[index].pathIndex;
        contacts[outputCount].state = canonicalState;
        contacts[outputCount].x = fingers[index].normalized.pos.x;
        contacts[outputCount].y = fingers[index].normalized.pos.y;
        outputCount++;
    }
    trackpad->callback(contacts, outputCount, timestamp, trackpad->context);
}

HMTrackpad *HMTrackpadCreate(HMTouchFrameCallback callback, void *context, char **errorMessage) {
    if (callback == NULL) {
        setError(errorMessage, "A frame callback is required");
        return NULL;
    }
    HMTrackpad *trackpad = calloc(1, sizeof(HMTrackpad));
    if (trackpad == NULL) {
        setError(errorMessage, "Unable to allocate trackpad bridge");
        return NULL;
    }
    trackpad->framework = openFramework();
    if (trackpad->framework == NULL) {
        setError(errorMessage, dlerror());
        free(trackpad);
        return NULL;
    }

    MTDeviceCreateListFn createList = (MTDeviceCreateListFn)dlsym(trackpad->framework, "MTDeviceCreateList");
    trackpad->registerCallback = (MTRegisterContactFrameCallbackFn)dlsym(trackpad->framework, "MTRegisterContactFrameCallback");
    trackpad->unregisterCallback = (MTUnregisterContactFrameCallbackFn)dlsym(trackpad->framework, "MTUnregisterContactFrameCallback");
    trackpad->deviceStart = (MTDeviceStartFn)dlsym(trackpad->framework, "MTDeviceStart");
    trackpad->deviceStop = (MTDeviceStopFn)dlsym(trackpad->framework, "MTDeviceStop");
    if (createList == NULL || trackpad->registerCallback == NULL || trackpad->deviceStart == NULL) {
        setError(errorMessage, "MultitouchSupport is missing required symbols");
        HMTrackpadDestroy(trackpad);
        return NULL;
    }

    trackpad->devices = createList();
    if (trackpad->devices == NULL || CFArrayGetCount(trackpad->devices) == 0) {
        setError(errorMessage, "No trackpad was found");
        HMTrackpadDestroy(trackpad);
        return NULL;
    }
    trackpad->deviceCount = CFArrayGetCount(trackpad->devices);
    trackpad->callback = callback;
    trackpad->context = context;
    return trackpad;
}

bool HMTrackpadStart(HMTrackpad *trackpad, char **errorMessage) {
    if (trackpad == NULL) {
        setError(errorMessage, "Trackpad bridge is not initialized");
        return false;
    }
    if (trackpad->started) return true;
    if (activeTrackpad != NULL && activeTrackpad != trackpad) {
        setError(errorMessage, "Another trackpad bridge is already active");
        return false;
    }
    activeTrackpad = trackpad;
    for (CFIndex index = 0; index < trackpad->deviceCount; index++) {
        void *device = (void *)CFArrayGetValueAtIndex(trackpad->devices, index);
        trackpad->registerCallback(device, contactFrameCallback);
        trackpad->deviceStart(device, 0);
    }
    trackpad->started = true;
    return true;
}

void HMTrackpadStop(HMTrackpad *trackpad) {
    if (trackpad == NULL || !trackpad->started) return;
    for (CFIndex index = 0; index < trackpad->deviceCount; index++) {
        void *device = (void *)CFArrayGetValueAtIndex(trackpad->devices, index);
        if (trackpad->deviceStop != NULL) trackpad->deviceStop(device);
        if (trackpad->unregisterCallback != NULL) {
            trackpad->unregisterCallback(device, contactFrameCallback);
        }
    }
    trackpad->started = false;
    if (activeTrackpad == trackpad) activeTrackpad = NULL;
}

void HMTrackpadDestroy(HMTrackpad *trackpad) {
    if (trackpad == NULL) return;
    HMTrackpadStop(trackpad);
    if (trackpad->devices != NULL) CFRelease(trackpad->devices);
    if (trackpad->framework != NULL) dlclose(trackpad->framework);
    free(trackpad);
}

void HMTrackpadFreeError(char *errorMessage) {
    free(errorMessage);
}
