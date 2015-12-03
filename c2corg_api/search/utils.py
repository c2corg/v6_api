import re

BBCODE_TAGS = [
    'b', 'i', 'u', 's', 'q', 'c', 'sup', 'ind', 'url', 'email', 'acr(onym)?',
    'colou?r', 'picto', 'p', 'center', 'right', 'left', 'justify',
    'abs(tract)?', 'imp(ortant)?', 'warn(ing)?', 'col', 'img', 'quote'
]
BBCODE_REGEX = \
    ['\[{0}\]'.format(tag) for tag in BBCODE_TAGS] + \
    ['\[\/{0}\]'.format(tag) for tag in BBCODE_TAGS] + [
        '\[url([^\[\]]*?)\]',
        '\[email([^\[\]]*?)\]',
        '\[acr(onym)?([^\[\]]*?)\]',
        '\[colou?r([^\[\]]*?)\]',
        '\[picto([^\[\]]*?)\]',
        '\[col([^\[\]]*?)\]',
        '\[toc([^\[\]]*?)\]',
        '\[img([^\[\]]*?)\]',
    ]
BBCODE_REGEX_ALL = re.compile('|'.join(BBCODE_REGEX))


def strip_bbcodes(s):
    """Remove all bbcodes from the given text.
    """
    if not s:
        return s
    else:
        return BBCODE_REGEX_ALL.sub(' ', s)
