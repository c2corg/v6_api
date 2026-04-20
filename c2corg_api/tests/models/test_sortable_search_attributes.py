import pytest
import unittest

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

            # Convert snake_case to CapWords to match enum class names
            capwords_key = ''.join(
                word.capitalize() for word in original_attribute_key.split('_')
            )

            if capwords_key not in attributes.__dict__:
                pytest.fail('{0} not found in {1}'.format(capwords_key, attributes))

            self._check_values(sortable_attribute_key, capwords_key)

    def _check_values(self, sortable_attribute_key, original_attribute_key):
        sortable_attribute = sortable_search_attributes.__dict__[sortable_attribute_key]
        original_attribute = attributes.__dict__[original_attribute_key]

        used_numbers = set()
        for val in original_attribute:
            if val not in sortable_attribute:
                pytest.fail(
                    '{0} defined on {1} but not on {2}'.format(
                        val, original_attribute_key, sortable_attribute_key
                    )
                )
            num = sortable_attribute[val]
            if num in used_numbers:
                pytest.fail(
                    '{0} is used twice in {1}'.format(num, sortable_attribute_key)
                )
            used_numbers.add(num)
