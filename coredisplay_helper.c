// coredisplay_helper.c
// Лёгкий C‑бинарь для управления яркостью через приватный CoreDisplay.framework
#include <stdio.h>
#include <stdlib.h>
#include <dlfcn.h>
#include <CoreGraphics/CoreGraphics.h>

int main(int argc, char *argv[]) {
    if (argc != 2) {
        fprintf(stderr, "Usage: coredisplay_helper <value>\n");
        return 1;
    }
    float val = strtof(argv[1], NULL);
    uint32_t disp = CGMainDisplayID();
    // Попытка через DisplayServices.framework (Apple Silicon)
    void *handle_ds = dlopen("/System/Library/PrivateFrameworks/DisplayServices.framework/DisplayServices", RTLD_LAZY);
    if (handle_ds) {
        typedef int (*DSSetBr)(uint32_t, float);
        DSSetBr ds_fn = (DSSetBr)dlsym(handle_ds, "DisplayServicesSetBrightness");
        if (ds_fn) {
            int res = ds_fn(disp, val);
            dlclose(handle_ds);
            return (res == 0) ? 0 : res;
        }
        dlclose(handle_ds);
    }
    // Fallback: через CoreDisplay.framework, если доступен
    void *handle_cd = dlopen("/System/Library/PrivateFrameworks/CoreDisplay.framework/CoreDisplay", RTLD_LAZY);
    if (handle_cd) {
        typedef int (*CDSetBr)(uint32_t, float);
        CDSetBr cd_fn = (CDSetBr)dlsym(handle_cd, "CoreDisplay_Display_SetUserBrightness");
        if (cd_fn) {
            int res = cd_fn(disp, val);
            dlclose(handle_cd);
            return (res == 0) ? 0 : res;
        }
        dlclose(handle_cd);
    }
    fprintf(stderr, "Failed to load brightness API\n");
    return 1;
}