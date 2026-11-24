from c2corg_api.partners.shapes import diff, shape
from c2corg_api.tests.contract import shape as contract_shape

SAMPLE = {
    'b': [{'x': 1, 'y': None}, {'x': 2.5, 'z': 'a'}],
    'a': {'ok': True, 'n': 3, 'items': []},
}


def test_scalars():
    assert shape(None) == 'null'
    assert shape(True) == 'bool'
    assert shape(1) == 'int'
    assert shape(1.5) == 'float'
    assert shape('a') == 'str'


def test_nested_lists_and_dicts():
    assert shape(SAMPLE) == {
        'a': {'items': [], 'n': 'int', 'ok': 'bool'},
        'b': [
            {
                'x': {'any_of': ['"float"', '"int"']},
                'y': 'null',
                'z': 'str',
            }
        ],
    }
    assert list(shape(SAMPLE)) == ['a', 'b']


def test_same_as_contract_shape():
    values = [SAMPLE, [[1], ['a'], []], {'k': [{'a': [1]}, {'a': []}]}, []]
    for value in values:
        assert shape(value) == contract_shape(value)


def test_diff_identical():
    assert diff(shape(SAMPLE), shape(SAMPLE)) == []


def test_diff_added_removed_changed():
    old = shape({'a': 1, 'b': {'c': 'x', 'd': 1}, 'l': [{'p': 1}]})
    new = shape({'a': 'one', 'b': {'c': 'x', 'e': True}, 'l': [{'p': 1, 'q': None}]})
    assert diff(old, new) == [
        '~ a: int -> str',
        '- b.d',
        '+ b.e: bool',
        '+ l[].q: null',
    ]


def test_diff_empty_containers():
    old = shape({'a': [], 'b': {}})
    new = shape({'a': [1], 'b': {'x': 1}})
    assert diff(old, new) == ['- a', '+ a[]: int', '- b', '+ b.x: int']


def test_diff_root_level_and_any_of():
    assert diff('int', 'str') == ['~ .: int -> str']
    assert diff(shape([1, 1.5]), shape([1])) == ['~ []: float|int -> int']
