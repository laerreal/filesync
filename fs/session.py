from Crypto.Cipher import (
    AES,
    PKCS1_OAEP,
)
from Crypto.PublicKey import (
    RSA,
)
from Crypto.Random import (
    get_random_bytes,
)


class Session(object):

    def __init__(self, identity, other_pub_key_data):
        self.identity = identity

        self.other_pub_key_data = other_pub_key_data
        self.other_pub_key = other_pub_key = RSA.importKey(other_pub_key_data)

        self.other_oaep = PKCS1_OAEP.new(other_pub_key)
        self.oaep = PKCS1_OAEP.new(identity.priv_key)

        self.trusted = False

    @property
    def aes(self):
        # Note that some implementations are not reusable and raises:
        # TypeError: encrypt() cannot be called after decrypt()
        return AES.new(self.session_key, AES.MODE_CFB, self.iv)

    @property
    def challenge_message(self):
        return (self.challenge, self.identity.pub_key_data)

    @property
    def challenge(self):
        self.session_key = session_key = get_random_bytes(32) # 256 bits
        self.iv = iv = get_random_bytes(16) # initialization vector

        priv = iv + session_key
        # TODO: is padding required for PKCS1_OAEP?
        self.session_private = priv + get_random_bytes(128 - len(priv))

        while True:
            seed = get_random_bytes(64)
            if seed != seed[::-1]:
                break

        self.session_seed = seed = get_random_bytes(64)

        enc_seed = self.aes.encrypt(seed)
        enc_private = self.other_oaep.encrypt(self.session_private)
        return (enc_private, enc_seed)

    def solve_challenge(self, challenge):
        enc_private, enc_seed = challenge

        private = self.oaep.decrypt(enc_private)
        self.session_private = private

        self.iv = private[:16]
        self.session_key = private[16:16 + 32]

        self.session_seed = seed = self.aes.decrypt(enc_seed)

        resp = seed[::-1]

        return self.aes.encrypt(resp)

    def check_solution(self, challenge_solution):
        resp = self.aes.decrypt(challenge_solution)
        correct = (resp == self.session_seed[::-1])

        self.trusted = correct
        # print("correct %s" % correct)
        return correct
