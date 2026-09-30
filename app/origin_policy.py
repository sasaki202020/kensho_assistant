"""Fail-closed origin policy. Candidate approval is checked separately."""
from __future__ import annotations

import json
import hashlib
import re
from urllib.parse import urlsplit

from . import paths

DEFAULT_DENYLIST = frozenset({
    'x.com', 'twitter.com', 'instagram.com', 'facebook.com', 'line.me',
    'tiktok.com', 'youtube.com', 'google.com', 'apple.com', 'amazon.co.jp',
    'amazon.com', 'rakuten.co.jp', 'paypal.com', 'paypay.ne.jp', 'login.yahoo.co.jp',
})
LOGIN_SUBDOMAIN = re.compile(r'login|signin|account|auth|pay', re.I)
LOOPBACK_HOSTS = frozenset({'127.0.0.1', 'localhost'})


def _denied_domains() -> set[str]:
    denied = set(DEFAULT_DENYLIST)
    config = paths.CONFIG_DIR / 'origin_denylist.json'
    if config.exists():
        data = json.loads(config.read_text(encoding='utf-8'))
        if data.get('schema_version') != 1 or not isinstance(data.get('domains'), list):
            raise ValueError('origin_policy_invalid')
        for domain in data['domains']:
            if not isinstance(domain, str) or not re.fullmatch(r'[a-z0-9]+(?:[a-z0-9.-]*[a-z0-9])?', domain):
                raise ValueError('origin_policy_invalid')
            denied.add(domain)
    return denied


def policy_fingerprint() -> str:
    """Pilot attests the effective policy, including mandatory code defaults."""
    policy = {'domains': sorted(_denied_domains()), 'login_subdomain': LOGIN_SUBDOMAIN.pattern,
              'https_only': True, 'standard_ports_only': True}
    return hashlib.sha256(json.dumps(policy, sort_keys=True).encode('utf-8')).hexdigest()


def normalize_origin(url: str) -> str:
    if not isinstance(url, str) or not url or any(c.isspace() or ord(c) < 32 for c in url) or '\\' in url:
        raise ValueError('invalid_origin')
    try:
        parsed = urlsplit(url)
        port = parsed.port
        if (parsed.scheme not in {'https', 'http'} or not parsed.hostname
                or parsed.username is not None or parsed.password is not None):
            raise ValueError
        host = parsed.hostname.encode('idna').decode('ascii').lower().rstrip('.')
        if not re.fullmatch(r'[a-z0-9]+(?:[a-z0-9.-]*[a-z0-9])?', host) or '..' in host:
            raise ValueError
        if port == 0:
            raise ValueError
        default = 443 if parsed.scheme == 'https' else 80
        return f'{parsed.scheme}://{host}' + (f':{port}' if port and port != default else '')
    except (ValueError, UnicodeError):
        raise ValueError('invalid_origin') from None


def is_origin_allowed(origin: str, *, allow_loopback_http: bool = False) -> tuple[bool, str]:
    try:
        normalized = normalize_origin(origin)
        parsed_input = urlsplit(origin)
        if parsed_input.path not in {'', '/'} or parsed_input.query or parsed_input.fragment:
            return False, 'invalid_origin'
        parsed = urlsplit(normalized)
        if parsed.scheme != 'https' and not (
            allow_loopback_http is True and parsed.hostname in LOOPBACK_HOSTS
        ):
            return False, 'https_required'
        if parsed.port and not (allow_loopback_http is True and parsed.hostname in LOOPBACK_HOSTS):
            return False, 'nonstandard_port'
        denied = _denied_domains()
        host = parsed.hostname
        if any(host == d or host.endswith('.' + d) for d in denied):
            return False, 'denied_domain'
        # Treat every label before the final two labels conservatively as a subdomain.
        if any(LOGIN_SUBDOMAIN.search(label) for label in host.split('.')[:-2]):
            return False, 'login_subdomain'
        return True, ''
    except (ValueError, OSError, TypeError, AttributeError):
        return False, 'origin_policy_invalid'
