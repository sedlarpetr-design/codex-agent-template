import unittest

from templates.queue_selection import ready_items


class QueueSelectionTests(unittest.TestCase):
    def setUp(self):
        self.items = [
            {"id": "source", "role": "librarian"},
            {"id": "dependent", "role": "methodologist", "zavisi_na": ["source"]},
            {"id": "independent", "role": "methodologist"},
            {"id": "second-source", "role": "librarian"},
        ]

    def test_waiting_dependency_does_not_block_independent_work(self):
        self.assertEqual(ready_items(self.items, {}, [], 2),
                         [self.items[0], self.items[2]])

    def test_verified_dependency_releases_original_item_in_order(self):
        states = {"source": "SPLNĚNO", "independent": "SPLNĚNO"}
        self.assertEqual(ready_items(self.items, states, [], 2),
                         [self.items[1], self.items[3]])

    def test_unverified_dependency_and_busy_role_are_skipped(self):
        self.assertEqual(ready_items(self.items, {"source": "NEOVĚŘENO"}, ["librarian"], 1),
                         [self.items[2]])

    def test_stop_or_no_capacity_selects_nothing(self):
        self.assertEqual(ready_items(self.items, {}, [], 2, stopped=True), [])
        self.assertEqual(ready_items(self.items, {}, [], 0), [])
