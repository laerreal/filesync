from os.path import (
    join,
    exists,
)
from Crypto.PublicKey import (
    RSA,
)
from .config import (
    CFG_DIRECTORY
)
from getpass import (
    getpass,
)

ID_PATH = CFG_DIRECTORY


class NewPassPhrase: pass
class RepeatPassPhrase: pass
class PassPhraseMissmatch: pass
class BadPassPhrase: pass
class GetPassPhrase: pass
class KeyImportError: pass


def do_print(msg):
    print(msg)


class Identity(object):

    def __init__(self, path = ID_PATH, keylength = 2048):
        self.path = path
        self.keylength = keylength

        self.priv_key_name = join(path, "key.priv")
        self.pub_key_name = join(path, "key.pub")

    @property
    def is_open(self):
        return hasattr(self, "priv_key")

    def co_open(self):
        priv_key_name = self.priv_key_name

        if exists(priv_key_name):
            with open(priv_key_name, "rb") as f:
                priv_key_data = f.read()

            status = GetPassPhrase
            while True:
                passphrase = (yield status)
                try:
                    priv_key = RSA.importKey(priv_key_data,
                        passphrase = passphrase
                    )
                except:
                    status = KeyImportError
                    continue
                else:
                    break
                finally:
                    del passphrase
        else:
            priv_key = RSA.generate(self.keylength)

            status = NewPassPhrase
            while True:
                passphrase = (yield status)
                if not passphrase:
                    status = BadPassPhrase
                elif passphrase == (yield RepeatPassPhrase):
                    break
                else:
                    status = PassPhraseMissmatch

            priv_key_data = priv_key.exportKey("PEM", passphrase = passphrase)
            del passphrase

            with open(priv_key_name, "wb") as f:
                f.write(priv_key_data)

        pub_key_name = self.pub_key_name

        if exists(pub_key_name):
            with open(pub_key_name, "rb") as f:
                pub_key_data = f.read()
            pub_key = RSA.importKey(pub_key_data)
        else:
            pub_key = priv_key.publickey()
            pub_key_data = pub_key.exportKey("PEM")
            with open(pub_key_name, "wb") as f:
                f.write(pub_key_data)

        self.pub_key = pub_key
        self.pub_key_data = pub_key_data
        self.priv_key = priv_key

    def open_ui(self,
        getpass = getpass,
        feedback = do_print,
        passphrase = None
    ):
        co_open = self.co_open()
        state = next(co_open)

        while True:
            if state is NewPassPhrase:
                ask_message = "Enter passphrase for NEW private key"
            elif state is RepeatPassPhrase:
                ask_message = "Repeat passphrase for new private key"
            elif state is PassPhraseMissmatch:
                ask_message = "Passphrases missmatch, try again"
            elif state is BadPassPhrase:
                ask_message = "Bad passphrase, try different"
            elif state is GetPassPhrase:
                ask_message = "Enter passphrase for private key"
            elif state is KeyImportError:
                ask_message = "Key import error (incorrect passphrase?)"
            else:
                # This is for developer mostly...
                feedback("Unknown authentication state: " + repr(state))
                return False

            if passphrase is None:
                try:
                    passphrase = getpass(ask_message)
                except KeyboardInterrupt:
                    passphrase = None

            if passphrase is None:
                feedback("Authentication cancelled")
                return False

            try:
                state = co_open.send(passphrase)
            except StopIteration: # success
                return True
            finally:
                del passphrase
