"""dingtalk_crypto.py
简化版的钉钉事件回调加解密实现，仅满足本示例用例。
参考官方示例与 https://github.com/open-dingtalk/DingTalk-Callback-Crypto
"""
from __future__ import annotations

import base64
import hashlib
import struct
import time
from typing import Tuple

from Crypto.Cipher import AES


class DingTalkCryptoError(Exception):
    pass


class DingTalkCrypto:
    """钉钉事件回调加解密工具

    仅实现 AES-CBC-128 + PKCS#7 解密、加密，以及 SHA1 签名校验。
    """

    block_size = 32

    def __init__(self, token: str, aes_key: str, owner_key: str):
        """初始化

        参数说明：
        token:   钉钉开发者后台配置的 token
        aes_key: 钉钉开发者后台生成的 43 位 EncodingAESKey
        owner_key: 企业内部应用为 corpId，三方应用为 suiteKey
        """
        if len(aes_key) != 43:
            raise DingTalkCryptoError('钉钉 AES Key 必须为 43 位。')
        self.token = token
        self.key = base64.b64decode(aes_key + "=")  # 32 bytes
        self.iv = self.key[:16]
        self.owner_key = owner_key

    # --------------------- util ---------------------
    @staticmethod
    def _sha1_signature(token: str, timestamp: str, nonce: str, encrypt: str) -> str:
        """生成 SHA1 签名"""
        sort_list = "".join(sorted([token, timestamp, nonce, encrypt]))
        sha = hashlib.sha1()
        sha.update(sort_list.encode())
        return sha.hexdigest()

    @staticmethod
    def _pkcs7_pad(text: bytes) -> bytes:
        """PKCS#7 补位"""
        pad_len = DingTalkCrypto.block_size - (len(text) % DingTalkCrypto.block_size)
        if pad_len == 0:
            pad_len = DingTalkCrypto.block_size
        padding = bytes([pad_len] * pad_len)
        return text + padding

    @staticmethod
    def _pkcs7_unpad(text: bytes) -> bytes:
        pad_len = text[-1]
        if pad_len < 1 or pad_len > DingTalkCrypto.block_size:
            raise DingTalkCryptoError('非法的填充长度')
        return text[:-pad_len]

    # --------------------- decrypt ---------------------
    def decrypt(self, encrypt_text: str) -> Tuple[str, str]:
        """解密 encrypt 字段并返回 (明文内容, owner_key)"""
        cipher = AES.new(self.key, AES.MODE_CBC, self.iv)
        encrypted = base64.b64decode(encrypt_text)
        plain_padded = cipher.decrypt(encrypted)
        plain = self._pkcs7_unpad(plain_padded)

        # 开头 16 字节随机，接下来 4 字节 msg_len，之后 msg, 最后 owner_key
        random_str = plain[:16]
        msg_len = struct.unpack('!I', plain[16:20])[0]
        msg_start = 20
        msg_end = msg_start + msg_len
        msg = plain[msg_start:msg_end].decode('utf-8')
        owner_key = plain[msg_end:].decode('utf-8')
        return msg, owner_key

    # --------------------- encrypt ---------------------
    def encrypt(self, plain_text: str) -> str:
        """将明文加密为 encrypt 字段"""
        import os

        random_str = os.urandom(16)
        msg_bytes = plain_text.encode()
        msg_len = struct.pack('!I', len(msg_bytes))
        plain = random_str + msg_len + msg_bytes + self.owner_key.encode()
        padded = self._pkcs7_pad(plain)

        cipher = AES.new(self.key, AES.MODE_CBC, self.iv)
        encrypted = cipher.encrypt(padded)
        return base64.b64encode(encrypted).decode()

    # --------------------- public helpers ---------------------
    def decrypt_event(self, signature: str, timestamp: str, nonce: str, encrypt_text: str) -> str:
        """完整事件解密并验证签名"""
        expected_sig = self._sha1_signature(self.token, timestamp, nonce, encrypt_text)
        if expected_sig != signature:
            raise DingTalkCryptoError('签名不匹配')
        msg, owner = self.decrypt(encrypt_text)
        if owner != self.owner_key:
            raise DingTalkCryptoError('owner_key 不匹配')
        return msg

    def encrypt_response(self, plain_text: str) -> dict:
        """将响应明文加密并返回应答 JSON dict"""
        encrypt_text = self.encrypt(plain_text)
        timestamp = str(int(time.time()))
        nonce = hashlib.md5(timestamp.encode()).hexdigest()[:8]
        sign = self._sha1_signature(self.token, timestamp, nonce, encrypt_text)
        return {
            'msg_signature': sign,
            'timeStamp': timestamp,
            'nonce': nonce,
            'encrypt': encrypt_text,
        } 