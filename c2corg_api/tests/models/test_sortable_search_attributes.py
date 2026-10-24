import pytest

from c2corg_api.models.common import attributes, sortable_search_attributes


class TestSortableSearchAttributes:
    def test_check_search_attributes(self):
        """Check that all values used in `sortable_search_attributes` have
        a corresponding value in `attributes`.
        """
        for sortable_attribute_key in [
            key
            for key in sortable_search_attributes.__dict__
            if key.startswith('sortable_')
        ]:
            original_attribute_key = sortable_attribute_key.replace('sortable_', '')

            if original_attribute_key not in attributes.__dict__:
                pytest.fail(f'{original_attribute_key} not found in {attributes}')

            self._check_values(sortable_attribute_key, original_attribute_key)

    def _check_values(self, sortable_attribute_key, original_attribute_key):
        sortable_attribute = sortable_search_attributes.__dict__[sortable_attribute_key]
        original_attribute = attributes.__dict__[original_attribute_key]

        used_numbers = set()
        for val in original_attribute:
            if val not in sortable_attribute:
                pytest.fail(
                    f'{val} defined on {original_attribute_key} but not on '
                    f'{sortable_attribute_key}'
                )
            num = sortable_attribute[val]
            if num in used_numbers:
                pytest.fail(f'{num} is used twice in {sortable_attribute_key}')
            used_numbers.add(num)
