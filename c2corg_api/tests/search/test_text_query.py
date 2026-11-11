from c2corg_api.search import get_text_query_on_title


def _clauses(term, lang=None):
    return get_text_query_on_title(term, lang).to_dict()['bool']['should']


def _fields_of(clause):
    body = clause['multi_match'] if 'multi_match' in clause else None
    return body['fields'] if body else None


def test_single_word_has_exact_prefix_clauses_and_no_fuzzy_when_short():
    clauses = _clauses('vens')
    suffixes = {c['multi_match']['fields'][0].rsplit('.', 1)[1] for c in clauses}
    assert suffixes == {'raw', 'contentheavy', 'ngram'}
    assert not any('fuzziness' in c['multi_match'] for c in clauses)


def test_exact_clause_outweighs_the_others():
    clauses = _clauses('vens')
    boosts = {
        c['multi_match']['fields'][0].rsplit('.', 1)[1]: c['multi_match']['boost']
        for c in clauses
    }
    assert boosts['raw'] > boosts['contentheavy'] > boosts['ngram']


def test_long_single_word_adds_a_low_weight_fuzzy_clause():
    clauses = _clauses('Venoise')
    fuzzy = [c['multi_match'] for c in clauses if 'fuzziness' in c['multi_match']]
    assert len(fuzzy) == 1
    assert fuzzy[0]['prefix_length'] == 1
    assert fuzzy[0]['boost'] < 1


def test_multi_word_has_no_fuzzy_clause():
    for clause in _clauses('Arêtes de Gerbier'):
        body = clause.get('multi_match') or {}
        assert 'fuzziness' not in body


def test_multi_word_only_the_last_word_is_a_prefix():
    clauses = _clauses('creux no')
    prefix = next(c['bool'] for c in clauses if 'bool' in c)
    head, last = prefix['must']
    assert head['multi_match']['query'] == 'creux'
    assert last['multi_match']['query'] == 'no'
    assert all('.ngram' in f for f in last['multi_match']['fields'])


def test_hyphen_separates_words():
    # "Mont-Blanc" must not be handled as one single (fuzzy) word
    assert any('bool' in c for c in _clauses('Mont-Blanc'))


def test_preferred_language_is_boosted_but_all_languages_are_searched():
    fields = _clauses('vens', 'fr')[0]['multi_match']['fields']
    assert 'title_fr.raw^3' in fields
    assert 'title_en.raw' in fields
