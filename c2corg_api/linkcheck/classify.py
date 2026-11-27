"""What the answer of a URL says about its link (see c2corg_api.linkcheck)."""

import re
import unicodedata
from urllib.parse import urlsplit

import tldextract

from c2corg_api.linkcheck import fetch as f

# the outcomes of one check
OK = 'ok'
MOVED = 'moved'
OFFSITE = 'offsite'
PARKED = 'parked'
SUSPECT = 'suspect'
FAILURE = 'failure'
# failures too: a page redirected to the home page or to a login page (the
# page linked is not there for readers any more)
HOME = 'home'
LOGIN = 'login'
FAILURES = (FAILURE, HOME, LOGIN)
INCONCLUSIVE = 'inconclusive'
BLOCKED = 'blocked'

# errors that say the page is not there (counted, dead after a few)
_FAILURE_ERRORS = {f.DNS, f.PRIVATE, f.REFUSED, f.TLS}
# answers that say the page is not there
_FAILURE_STATUSES = {404, 410}

# the Public Suffix List of the package (no download), with the private
# suffixes: two blogs on blogspot.com are two sites
_extract = tldextract.TLDExtract(suffix_list_urls=(), include_psl_private_domains=True)

# hosts whose links redirect to another site by design
SHORTENERS = {
    'bit.ly',
    'goo.gl',
    'maps.app.goo.gl',
    't.co',
    'tinyurl.com',
    'ow.ly',
    'is.gd',
    'youtu.be',
    'urlz.fr',
}

# a page offering the domain for sale, or parked by a parking service
_PARKED_RE = re.compile(
    r'this domain (?:name )?(?:is|may be) for sale'
    r'|buy this domain'
    r'|domain (?:name )?(?:is )?for sale'
    r'|this domain has expired'
    r'|ce (?:nom de )?domaine (?:est|peut être) à vendre'
    r'|diese domain (?:steht zum verkauf|kaufen|ist zu verkaufen)'
    r'|questo dominio è in vendita'
    r'|este dominio (?:está|puede estar) en venta'
    r'|\b(?:sedoparking|parkingcrew|bodis|afternic|hugedomains|domainmarket'
    r'|undeveloped|dan)\.(?:com|net)\b',
    re.IGNORECASE,
)

# a title saying the page does not exist (served with a 200)
_NOT_FOUND_TITLE_RE = re.compile(
    r'\b(?:404|page not found|not found|page introuvable|page non trouvée'
    r'|page inexistante|seite nicht gefunden|pagina non trovata'
    r'|página no encontrada)\b',
    re.IGNORECASE,
)

# a title about something else than mountains: the domain was taken over
_SPAM_TITLE_RE = re.compile(
    r'\b(?:casinos?|poker|betting|paris sportifs|scommesse|apuestas|viagra'
    r'|cialis|porn\w*|xxx|escorts?|payday|loans?|crypto\w*|bitcoin|replica'
    r'|pharmacy|jackpot|bonus sans dépôt)\b',
    re.IGNORECASE,
)


# the last segments of the path of a home page: /, /fr/, /it/home, /accueil...
_HOME_SEGMENTS = {
    'home',
    'accueil',
    'start',
    'startseite',
    'inicio',
    'index',
    'index.html',
    'index.htm',
    'index.php',
    'default.asp',
    'default.aspx',
}
_LANG_SEGMENT_RE = re.compile(r'^[a-z]{2}(?:[-_][a-z]{2})?$', re.IGNORECASE)

# a login page
_LOGIN_RE = re.compile(
    r'log-?in|sign-?in|connexion|identification|anmeld|accedi|wp-login|/auth\b'
    r'|/account\b',
    re.IGNORECASE,
)


def _segments(url):
    return [s for s in urlsplit(url).path.split('/') if s]


def is_home(url):
    """Tell whether a URL is a home page: no query, a path such as /fr/home."""
    if urlsplit(url).query:
        return False
    segments = [s.lower() for s in _segments(url)]
    if segments and _LANG_SEGMENT_RE.match(segments[0]):
        segments = segments[1:]
    return not segments or segments == [segments[0]] and segments[0] in _HOME_SEGMENTS


def _redirected_away(url, final_url):
    """Return HOME or LOGIN when a link was sent there instead of its page."""
    # a link to a home page or a login page may lead to one
    if _LOGIN_RE.search(final_url) and not _LOGIN_RE.search(url):
        return LOGIN
    if is_home(final_url) and not is_home(url):
        return HOME
    return None


def site(host):
    """Return the registrable domain of a host (example.co.uk)."""
    # an unknown suffix: its last two labels
    extracted = _extract(host)
    return extracted.top_domain_under_public_suffix or '.'.join(host.split('.')[-2:])


def same_site(host, other):
    """Tell whether two hosts are the same site: same domain, or same name."""
    # google.fr and google.com, x.blogspot.fr and x.blogspot.com: the same
    # organisation (only the last label changed)
    if site(host) == site(other):
        return True
    host, other = host.removeprefix('www.'), other.removeprefix('www.')
    if '.' in host and host.rsplit('.', 1)[0] == other.rsplit('.', 1)[0]:
        return True
    first, second = _extract(host), _extract(other)
    # names under a known suffix only (an unknown one is no domain name)
    return bool(first.suffix and second.suffix) and first.domain == second.domain


def _comparable(url):
    """Return the URL without what does not change the page (scheme, www., /)."""
    parts = urlsplit(url)
    host = (parts.hostname or '').removeprefix('www.')
    return host, parts.path.rstrip('/'), parts.query


def _words(title):
    text = unicodedata.normalize('NFKD', title.lower())
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return {w for w in re.findall(r'\w+', text) if len(w) >= 3 and not w.isdigit()}


def title_changed(reference, title):
    """Tell whether a title has nothing in common with the one of reference."""
    # both known: a page that was not read up to its title tells nothing
    if not reference or not title:
        return False
    before, now = _words(reference), _words(title)
    return bool(before) and bool(now) and not before & now


def classify(url, answer, reference_title=None):
    """Return the outcome of an answer (fetch.Answer) for a link to `url`."""
    if answer.error:
        if answer.error in _FAILURE_ERRORS:
            return FAILURE
        if answer.error == f.PORT and len(answer.urls) == 1:
            # not checked: a link to an unusual port
            return BLOCKED
        return INCONCLUSIVE
    status = answer.http_status
    if status in _FAILURE_STATUSES:
        return FAILURE
    if status is None or not 200 <= status < 300:
        # 401, 403, 429, 5xx...: the site answers, the page may be there
        return INCONCLUSIVE
    title = answer.title or ''
    if _NOT_FOUND_TITLE_RE.search(title):
        return FAILURE
    if _PARKED_RE.search(answer.text):
        return PARKED
    host = urlsplit(url).hostname or ''
    final_host = urlsplit(answer.final_url).hostname or ''
    if host in SHORTENERS:
        # it leads elsewhere by design: what matters is that it leads somewhere
        return OK
    if not same_site(host, final_host):
        return OFFSITE
    if _SPAM_TITLE_RE.search(title) or title_changed(reference_title, title):
        return SUSPECT
    if _comparable(answer.final_url) != _comparable(url):
        return _redirected_away(url, answer.final_url) or MOVED
    return OK
