"""Local prototype credentials; never persist or log raw Bearer tokens."""
import hashlib
import hmac
import secrets
import time
from uuid import uuid4

from app.services import RuleError
from app.storage import one

ITERATIONS = 600000
KINDS = {'human', 'relay', 'codex', 'agent'}


def password_digest(password, salt, iterations=ITERATIONS):
    return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt), iterations).hex()


class Credentials:
    def __init__(self, db):
        self.db = db

    def _user(self, c, user):
        if not one(c, 'SELECT id FROM users WHERE id=?', (user,)):
            raise RuleError('Unknown user', 401)

    def set_password(self, user, password):
        user = user.lower()
        if not 12 <= len(password) <= 1024:
            raise RuleError('Use a password of 12 to 1024 characters', 422)
        salt = secrets.token_hex(16)
        digest = password_digest(password, salt)
        with self.db.write() as c:
            self._user(c, user)
            c.exec_driver_sql('INSERT INTO human_passwords(user_id,salt,password_hash,iterations) VALUES (?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET salt=excluded.salt,password_hash=excluded.password_hash,iterations=excluded.iterations',
                              (user, salt, digest, ITERATIONS))
            c.exec_driver_sql("UPDATE principal_tokens SET revoked=1 WHERE user_id=? AND kind='human'", (user,))

    def _issue(self, c, user, kind, ttl):
        token = secrets.token_urlsafe(32)
        identity = str(uuid4())
        created = int(time.time())
        c.exec_driver_sql('INSERT INTO principal_tokens(id,user_id,kind,token_hash,created_at,expires_at) VALUES (?,?,?,?,?,?)',
                          (identity, user, kind, hashlib.sha256(token.encode()).hexdigest(), created, created + ttl))
        return {'access_token': token, 'token_type': 'bearer', 'expires_in': ttl,
                'principal': kind, 'principal_id': identity, 'user_id': user}

    def issue(self, user, kind, ttl=86400):
        user = user.lower()
        if kind == 'human':
            # Human sessions come only from password login, so a locally minted token cannot pose as a person.
            raise RuleError('Human sessions come only from password login', 422)
        if kind not in KINDS or type(ttl) is not int or not 1 <= ttl <= 2592000:
            raise RuleError('Invalid principal kind or token lifetime (1..2592000 seconds)', 422)
        with self.db.write() as c:
            self._user(c, user)
            return self._issue(c, user, kind, ttl)

    def login(self, user, password):
        user = user.lower()
        with self.db.engine.connect() as c:
            row = one(c, 'SELECT * FROM human_passwords WHERE user_id=?', (user,))
        # Perform comparable hashing work for an unknown username too.
        salt = row['salt'] if row else '00' * 16
        iterations = row['iterations'] if row else ITERATIONS
        digest = password_digest(password, salt, iterations)
        if not row or not hmac.compare_digest(digest, row['password_hash']):
            raise RuleError('Invalid credentials', 401)
        with self.db.write() as c:
            # A concurrent password reset must not mint a session from stale proof.
            current = one(c, 'SELECT * FROM human_passwords WHERE user_id=?', (user,))
            if current != row:
                raise RuleError('Invalid credentials', 401)
            return self._issue(c, user, 'human', 28800)

    def resolve(self, token):
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self.db.engine.connect() as c:
            row = one(c, 'SELECT * FROM principal_tokens WHERE token_hash=?', (digest,))
        if not row or row['revoked'] or row['expires_at'] <= int(time.time()):
            raise RuleError('Invalid credentials', 401)
        return {'user_id': row['user_id'], 'principal': row['kind'], 'principal_id': row['id']}

    def revoke(self, identity):
        with self.db.write() as c:
            c.exec_driver_sql('UPDATE principal_tokens SET revoked=1 WHERE id=?', (identity,))
