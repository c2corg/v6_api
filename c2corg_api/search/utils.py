import logging
import re
log = logging.getLogger(__name__)

BBCODE_TAGS = [
    'b', 'i', 'u', 's', 'q', 'c', 'sup', 'ind', 'url', 'email', 'acr(onym)?',
    'colou?r', 'picto', 'p', 'center', 'right', 'left', 'justify',
    'abs(tract)?', 'imp(ortant)?', 'warn(ing)?', 'col', 'img', 'quote'
]
BBCODE_REGEX = \
    [r'\[{0}\]'.format(tag) for tag in BBCODE_TAGS] + \
    [r'\[\/{0}\]'.format(tag) for tag in BBCODE_TAGS] + [
        r'\[url([^\[\]]*?)\]',
        r'\[email([^\[\]]*?)\]',
        r'\[acr(onym)?([^\[\]]*?)\]',
        r'\[colou?r([^\[\]]*?)\]',
        r'\[picto([^\[\]]*?)\]',
        r'\[col([^\[\]]*?)\]',
        r'\[toc([^\[\]]*?)\]',
        r'\[img([^\[\]]*?)\]',
    ]
BBCODE_REGEX_ALL = re.compile('|'.join(BBCODE_REGEX))


def strip_bbcodes(s):
    """Remove all bbcodes from the given text.
    """
    if not s:
        return s
    else:
        return BBCODE_REGEX_ALL.sub(' ', s)


def get_title(title, title_prefix):
    return title_prefix + ' : ' + title if title_prefix else title
