// Freestanding byte operations. Kept out of contributor DSP and browser builds.
#include <stddef.h>
extern "C" void* memset(void* destination, int value, size_t size) {
    unsigned char* d = static_cast<unsigned char*>(destination);
    while (size--) *d++ = static_cast<unsigned char>(value);
    return destination;
}
extern "C" void* memcpy(void* destination, const void* source, size_t size) {
    unsigned char* d = static_cast<unsigned char*>(destination);
    const unsigned char* s = static_cast<const unsigned char*>(source);
    while (size--) *d++ = *s++;
    return destination;
}
