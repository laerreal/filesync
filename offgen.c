#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <errno.h>
#include <string.h>

int main(int c, char **av)
{
    uint8_t bytes[256];
    size_t size = atol(av[2]);
    uint8_t offsetBytes = atoi(av[3]);

    FILE *f = fopen(av[1], "wb");
    if (!f) return errno;

    memset(bytes, 0, 256);
    size_t rest = size / offsetBytes;
    size_t curOffset = 0;
    while (rest--) {
        size_t val = curOffset;
        curOffset += offsetBytes;

        int i = offsetBytes;
        while (i--) {
            bytes[i] = val & 0xFF;
            if (!(val >>= 8)) break;
        }

        if (fwrite(bytes, offsetBytes, 1, f) != 1) return errno;
    }

    int tail = size % offsetBytes;
    if (tail){
        memset(bytes, 0, tail);
        if (fwrite(bytes, 1, tail, f) != tail) return errno;
    }

    fclose(f);
    return 0;
}
