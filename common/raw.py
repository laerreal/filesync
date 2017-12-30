__all__ = [
    "bytes2int",
    "int2bytes"
]

def bytes2int(bytes):
    result = 0

    for b in bytes:
        result = result * 256 + int(b)

    return result

def int2bytes(value, length):
    result = []

    for i in range(0, length):
        result.append(value >> (i * 8) & 0xff)

    result.reverse()
    result = bytes(result)

    return result