"""Security checks use generated ephemeral signing keys, never stored credentials."""
import time
import unittest
from unittest.mock import Mock

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa


class AccessTests(unittest.IsolatedAsyncioTestCase):
    async def test_signature_audience_expiry_and_owner_are_all_required(self):
        from hsuh.access import AccessGate
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        gate = AccessGate('https://hsuh.example.test','fixture-team','fixture-audience', 'owner@example.test')
        gate.jwks = Mock()
        gate.jwks.get_signing_key_from_jwt.return_value = Mock(key=key.public_key())
        claims = {'iss':'https://fixture-team.cloudflareaccess.com','aud':['fixture-audience'],
                  'sub':'fixture-owner', 'email':'owner@example.test','iat':int(time.time()), 'exp':int(time.time())+60}
        async def allowed(changes):
            token=jwt.encode(claims|changes,key,algorithm='RS256')
            return await gate.allows(token)
        self.assertTrue(await allowed({}))
        self.assertFalse(await allowed({'email':'stranger@example.test'}))
        self.assertFalse(await allowed({'aud':['wrong-app']}))
        self.assertFalse(await allowed({'exp':int(time.time())-60}))
        self.assertFalse(await gate.allows(jwt.encode(claims,'',algorithm='none')))


if __name__ == '__main__':
    unittest.main()
