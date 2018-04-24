__all__ = [
    "byte2int",
    "bytes2int",
    "int2bytes"
]

from sys import version_info

if version_info[0] == 2:
    # byte is a one character string in Py2
    byte2int = ord
else:
    byte2int = int

def bytes2int(bytes):
    result = 0

    for b in bytes:
        result = result * 256 + byte2int(b)

    return result

def int2bytes(value, length):
    result = []

    for i in range(0, length):
        result.append(value >> (i * 8) & 0xff)

    result.reverse()
    result = bytes(result)

    return result