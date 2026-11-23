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

    def test_handoff_releases_librarian_during_verification(self):
        from templates.queue_selection import verified_dependencies

        reports = {("archived-source-list", "verified-source"):
                   {"overeni": {"verdikt": "SPLNĚNO"}}}
        states = verified_dependencies({"old-source": ("archived-source-list", "verified-source")}, reports)
        items = [{"id": "next-source", "role": "librarian"},
                 {"id": "new-scenario", "role": "methodologist", "zavisi_na": ["old-source"]}]
        self.assertEqual(ready_items(items, states, ["verifier"], 2), items)

    def test_missing_or_negative_report_cannot_release_followup(self):
        from templates.queue_selection import verified_dependencies

        items = [{"id": "followup", "role": "methodologist", "zavisi_na": ["source"]},
                 {"id": "independent", "role": "librarian"}]
        references = {"source": ("closed-list", "source")}
        for reports in ({}, {("closed-list", "source"): {"overeni": {"verdikt": "NEOVĚŘENO"}}}):
            states = verified_dependencies(references, reports)
            self.assertEqual(ready_items(items, states, [], 2), [items[1]])

    def test_scans_past_a_group_of_busy_role_items(self):
        items = [{"id": number, "role": ("librarian" if number <= 10 else
                                        "methodologist" if number <= 15 else "ux")}
                 for number in range(1, 19)]
        self.assertEqual([item["id"] for item in ready_items(items, {}, [], 3)], [1, 11, 16])
        self.assertEqual([item["id"] for item in ready_items(items, {}, ["librarian"], 3)], [11, 16])

    def test_selection_scales_with_registered_role_capacity(self):
        items = [{"id": number, "role": f"role-{number // 20}"} for number in range(1000)]
        selected = ready_items(items, {}, [], 50)
        self.assertEqual([item["id"] for item in selected], list(range(0, 1000, 20)))
