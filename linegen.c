#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <errno.h>
#include <string.h>

int main(int c, char **av)
{
    size_t lines = atol(av[2]);
    int i;

    FILE *f = fopen(av[1], "wb");
    if (!f) return errno;

    for (i = 1; i <= lines; i++) {
        fprintf(f, "%d\r\n", i);
    }

    fclose(f);
    return 0;
}
