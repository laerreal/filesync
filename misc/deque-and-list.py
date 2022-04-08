from collections import deque
from time import time
from sys import stdout

if __name__ == "__main__":
    stdout.write("initializing...")

    d0 = deque(range(1, 10000000));

    print(" done")

    t = 0

    stdout.write("measurements")

    for _ in range(100):
        stdout.write(".")

        t -= time()
        _ = deque(d0)
        t += time()

    print(" done")

    print("deque -> deque: %s" % t)

    t = 0

    stdout.write("measurements")

    for _ in range(100):
        stdout.write(".")

        t -= time()
        _ = list(d0)
        t += time()

    print(" done")

    print("deque -> list: %s" % t)
