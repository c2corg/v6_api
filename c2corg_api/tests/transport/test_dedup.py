from c2corg_api.transport import dedup


class TestNames:
    def test_name_tokens(self):
        assert dedup.name_tokens('Annecy, Gare Routière') == {
            'annecy',
            'gare',
            'routiere',
        }
        # case, accents, punctuation and little words
        assert dedup.name_tokens("L'Hôtel de Ville (Chamonix)") == {
            'hotel',
            'ville',
            'chamonix',
        }
        assert dedup.name_tokens('') == set()
        assert dedup.name_tokens(None) == set()
        assert dedup.name_tokens('Arrêt') == set()

    def test_names_that_look_alike(self):
        # one contains the other
        assert dedup.names_similar('Gare Routière', 'Annecy, Gare Routière')
        assert dedup.names_similar('Gare', 'Gare SNCF Annecy')
        assert dedup.names_similar('MAIRIE', 'Mairie')
        # half of the words
        assert dedup.names_similar('Pont Neuf Nord', 'Pont Neuf Sud')

    def test_names_that_do_not_look_alike(self):
        assert not dedup.names_similar('Mairie', 'Poste')
        assert not dedup.names_similar('Gare Routière', 'Annecy, Gare')
        assert not dedup.names_similar('', 'Mairie')
        assert not dedup.names_similar('Arrêt', 'Arrêt')


def stop(name, departures, *codes):
    return {'name': name, 'departures': departures, 'codes': set(codes)}


class TestClusterStops:
    def test_same_place_whatever_the_name(self):
        stops = {1: stop('Gare', 100), 2: stop('Poste', 10)}

        assert dedup.cluster_stops(stops, [(1, 2, 10)]) == {1: 1, 2: 1}

    def test_near_with_the_same_name(self):
        stops = {1: stop('Gare Routière', 100), 2: stop('Annecy Gare Routière', 10)}

        assert dedup.cluster_stops(stops, [(1, 2, 30)]) == {1: 1, 2: 1}

    def test_near_with_the_same_line(self):
        stops = {1: stop('Gare', 100, '12', 'y62'), 2: stop('Poste', 10, 'y62')}

        assert dedup.cluster_stops(stops, [(1, 2, 30)]) == {1: 1, 2: 1}

    def test_near_but_not_alike(self):
        stops = {1: stop('Gare', 100, '12'), 2: stop('Poste', 10, '3')}

        assert dedup.cluster_stops(stops, [(1, 2, 30)]) == {1: 1, 2: 2}

    def test_too_far(self):
        stops = {1: stop('Gare', 100, '12'), 2: stop('Gare', 10, '12')}

        assert dedup.cluster_stops(stops, [(1, 2, 60)]) == {1: 1, 2: 2}
        # not even in the pairs
        assert dedup.cluster_stops(stops, []) == {1: 1, 2: 2}

    def test_the_anchor_has_the_most_departures(self):
        stops = {2: stop('Gare', 10), 10: stop('Gare', 50)}

        assert dedup.cluster_stops(stops, [(2, 10, 5)]) == {10: 10, 2: 10}

    def test_the_anchor_is_the_first_stop_when_equal(self):
        stops = {2: stop('Gare', 10), 10: stop('Gare', 10)}

        assert dedup.cluster_stops(stops, [(2, 10, 5)]) == {2: 2, 10: 2}

    def test_a_cluster_does_not_follow_the_street(self):
        # 2 is near 1 (14 m), 3 is near 2 (14 m) but 28 m from 1, and they
        # do not look alike: 3 is not of the cluster of 1
        stops = {1: stop('Gare', 100), 2: stop('Gare', 50), 3: stop('Poste', 10)}
        pairs = [(1, 2, 14), (2, 3, 14), (1, 3, 28)]

        assert dedup.cluster_stops(stops, pairs) == {1: 1, 2: 1, 3: 3}

    def test_a_stop_goes_to_one_cluster(self):
        stops = {1: stop('Gare', 100), 2: stop('Gare', 90), 3: stop('Gare', 10)}
        pairs = [(1, 3, 12), (2, 3, 5), (1, 2, 200)]

        clusters = dedup.cluster_stops(stops, pairs)

        # 3 is near both, it follows the first anchor
        assert clusters == {1: 1, 2: 2, 3: 1}

    def test_no_stop(self):
        assert dedup.cluster_stops({}, []) == {}


def line(trips, length=1000):
    return {'trips': trips, 'length': length}


class TestDuplicateLines:
    def test_lines_that_cover_each_other(self):
        lines = {1: line(10), 2: line(40)}

        # the one with the most trips is kept
        assert dedup.duplicate_lines(lines, [(1, 2, 0.95, 0.92)]) == {1: 2}

    def test_a_short_line_in_a_long_one_is_not_a_duplicate(self):
        lines = {1: line(10, 500), 2: line(40, 5000)}

        assert dedup.duplicate_lines(lines, [(1, 2, 1.0, 0.1)]) == {}

    def test_the_paths_must_overlap_enough(self):
        lines = {1: line(10), 2: line(40)}

        assert dedup.duplicate_lines(lines, [(1, 2, 0.89, 0.95)]) == {}

    def test_the_longest_is_kept_with_as_many_trips(self):
        lines = {1: line(10, 900), 2: line(10, 1000)}

        assert dedup.duplicate_lines(lines, [(1, 2, 1.0, 1.0)]) == {1: 2}

    def test_the_first_is_kept_when_all_is_equal(self):
        lines = {1: line(10), 2: line(10)}

        assert dedup.duplicate_lines(lines, [(1, 2, 1.0, 1.0)]) == {2: 1}

    def test_a_line_in_three_feeds(self):
        lines = {1: line(10), 2: line(30), 3: line(20)}
        pairs = [(1, 2, 1.0, 1.0), (2, 3, 0.95, 0.95)]

        assert dedup.duplicate_lines(lines, pairs) == {1: 2, 3: 2}

    def test_no_pair(self):
        assert dedup.duplicate_lines({1: line(1)}, []) == {}
