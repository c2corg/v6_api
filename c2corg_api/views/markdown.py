from c2c_markdown import parse_code, configure_parsers

configure_parsers({'api_url': 'https://api.camptocamp.org/'})

# this is locale property, but they must not be cooked by markdown parser
NOT_MARKDOWN_PROPERTY = {
    'lang',
    'version',
    'title',
    'slope',
    'conditions_levels',
    'topic_id',
    'participants'
}


def cook(data):
    result = {}
    for key in data:
        if key not in NOT_MARKDOWN_PROPERTY and data[key]:
            result[key] = parse_code(data[key])
        else:
            result[key] = data[key]

    return result
