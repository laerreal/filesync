from re import (
    compile,
)
from Crypto.Random import (
    get_random_bytes,
)

re_spaces = compile("\s")

prime_2048_str = "".join(re_spaces.split("""
FFFFFFFF FFFFFFFF C90FDAA2 2168C234 C4C6628B 80DC1CD1
29024E08 8A67CC74 020BBEA6 3B139B22 514A0879 8E3404DD
EF9519B3 CD3A431B 302B0A6D F25F1437 4FE1356D 6D51C245
E485B576 625E7EC6 F44C42E9 A637ED6B 0BFF5CB6 F406B7ED
EE386BFB 5A899FA5 AE9F2411 7C4B1FE6 49286651 ECE45B3D
C2007CB8 A163BF05 98DA4836 1C55D39A 69163FA8 FD24CF5F
83655D23 DCA3AD96 1C62F356 208552BB 9ED52907 7096966D
670C354E 4ABC9804 F1746C08 CA18217C 32905E46 2E36CE3B
E39E772C 180E8603 9B2783A2 EC07A28F B5C55DF0 6F4C52C9
DE2BCBF6 95581718 3995497C EA956AE5 15D22618 98FA0510
15728E5A 8AACAA68 FFFFFFFF FFFFFFFF
"""))



class PrimeCache(object):

    def __init__(self, prime):
        self.prime = prime

        self._two_pow_two_pow_i = [2]

    def tow_pow_two_pow_i(self, i):
        tptpi = self._two_pow_two_pow_i
        prime = self.prime
        x_prev = tptpi[-1]
        for _i in range(len(tptpi), i + 1):
            x_i = (x_prev * x_prev) % prime
            tptpi.append(x_i)
            x_prev = x_i
            print(x_i)

        return tptpi[i]

    def two_pow_x(self, x):
        res = 1
        i = 0
        prime = self.prime
        while x:
            if x & 1:
                two_pow = self.tow_pow_two_pow_i(i)
                res *= two_pow
                res %= prime
            x >>= 1
            i += 1
        return res

    __call__ = two_pow_x


def main():
    print(prime_2048_str)
    prime_2048 = int(prime_2048_str, 16)
    prime_2048_back = "%X" % prime_2048
    if prime_2048_back != prime_2048_str:
        print("diffs: " + prime_2048_back)
        return 1
    print("OK")
    prime_cache = PrimeCache(prime_2048)

    aes_key_bytes = get_random_bytes(32)
    aes_key = 0
    for b in aes_key_bytes:
        aes_key <<= 8
        aes_key += b

    print(prime_cache(aes_key))


if __name__ == "__main__":
    exit(main() or 0)