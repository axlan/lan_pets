# Copy of /home/vscode/.local/lib/python3.12/site-packages/Crypto/Cipher/PKCS1_v1_5.py with custom padding

from Crypto import Random
from Crypto.Cipher.PKCS1_v1_5 import PKCS115_Cipher
from Crypto.Util.number import bytes_to_long, long_to_bytes


class Custom_PKCS115_Cipher(PKCS115_Cipher):
    def encrypt(self, message):
        """Produce the PKCS#1 v1.5 encryption of a message.

        This function is named ``RSAES-PKCS1-V1_5-ENCRYPT``, and it is specified in
        `section 7.2.1 of RFC8017
        <https://tools.ietf.org/html/rfc8017#page-28>`_.

        :param message:
            The message to encrypt, also known as plaintext. It can be of
            variable length, but not longer than the RSA modulus (in bytes) minus 11.
        :type message: bytes/bytearray/memoryview

        :Returns: A byte string, the ciphertext in which the message is encrypted.
            It is as long as the RSA modulus (in bytes).

        :Raises ValueError:
            If the RSA key length is not sufficiently long to deal with the given
            message.
        """

        # See 7.2.1 in RFC8017
        k = self._key.size_in_bytes()
        mLen = len(message)

        # Step 1
        if mLen > k - 11:
            raise ValueError("Plaintext is too long.")
        # Step 2a
        # Original Implementation
        # ps = []
        # while len(ps) != k - mLen - 3:
        #     new_byte = self._randfunc(1)
        #     if bord(new_byte[0]) == 0x00:
        #         continue
        #     ps.append(new_byte)
        # ps = b"".join(ps)
        # # Step 2b
        # em = b'\x00\x02' + ps + b'\x00' + _copy_bytes(None, None, message)
        em = message + b'\x00' * (k - mLen)
        # Step 3a (OS2IP)
        em_int = bytes_to_long(em)
        # Step 3b (RSAEP)
        m_int = self._key._encrypt(em_int)
        # Step 3c (I2OSP)
        c = long_to_bytes(m_int, k)
        return c


def new(key, randfunc=None):
    """Create a cipher for performing PKCS#1 v1.5 encryption or decryption.

    :param key:
      The key to use to encrypt or decrypt the message. This is a `Crypto.PublicKey.RSA` object.
      Decryption is only possible if *key* is a private RSA key.
    :type key: RSA key object

    :param randfunc:
      Function that return random bytes.
      The default is :func:`Crypto.Random.get_random_bytes`.
    :type randfunc: callable

    :returns: A cipher object `PKCS115_Cipher`.
    """

    if randfunc is None:
        randfunc = Random.get_random_bytes
    return Custom_PKCS115_Cipher(key, randfunc)
