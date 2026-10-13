import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import database
import refund_service


class RefundServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        database.initialize_database(self.db_path)
        self.connect_patch = patch("refund_service.connect", lambda: database.connect(self.db_path))
        self.connect_patch.start()

    def tearDown(self):
        self.connect_patch.stop()
        self.temp_dir.cleanup()

    def test_get_order_normalizes_id(self):
        self.assertEqual(refund_service.get_order("ord-1001")["order_id"], "ORD-1001")

    def test_cancelled_before_shipping_is_eligible(self):
        result = refund_service.check_refund_eligibility(refund_service.get_order("ORD-1021"))
        self.assertEqual(result["decision"], "ELIGIBLE")

    def test_lost_order_is_eligible(self):
        result = refund_service.check_refund_eligibility(refund_service.get_order("ORD-1017"))
        self.assertEqual(result["decision"], "ELIGIBLE")

    def test_in_transit_needs_review(self):
        result = refund_service.check_refund_eligibility(refund_service.get_order("ORD-1009"))
        self.assertEqual(result["decision"], "NEEDS_REVIEW")

    def test_unverified_damage_needs_review(self):
        order = refund_service.get_order("ORD-1013")
        order["claim_type"] = "DAMAGED"
        result = refund_service.check_refund_eligibility(order)
        self.assertEqual(result["reason"], "DAMAGED_CLAIM_UNVERIFIED")

    def test_process_refund_updates_order_and_logs_interaction(self):
        result = refund_service.process_refund("ORD-1017")
        self.assertTrue(result["success"])
        self.assertEqual(refund_service.get_order("ORD-1017")["refunded"], 1)
        with database.connect(self.db_path) as connection:
            log = connection.execute("SELECT * FROM interactions").fetchone()
        self.assertEqual(log["result"], "SIMULATED_REFUND_COMPLETED")

    def test_refund_cannot_be_processed_twice(self):
        refund_service.process_refund("ORD-1017")
        result = refund_service.process_refund("ORD-1017")
        self.assertFalse(result["success"])
        self.assertEqual(result["reason"], "ALREADY_REFUNDED")


if __name__ == "__main__":
    unittest.main()
