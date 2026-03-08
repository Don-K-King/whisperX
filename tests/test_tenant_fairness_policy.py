import unittest

from evodox.jobs.tenant_fairness import TenantFairnessPolicy


class TenantFairnessPolicyTests(unittest.TestCase):
    def test_backpressure_blocks_when_global_or_tenant_limit_exceeded(self):
        policy = TenantFairnessPolicy(max_inflight_global=2, max_inflight_per_tenant=1)

        self.assertTrue(policy.try_start("tenant-a"))
        self.assertFalse(policy.try_start("tenant-a"))
        self.assertTrue(policy.try_start("tenant-b"))
        self.assertFalse(policy.try_start("tenant-c"))

    def test_round_robin_selection_avoids_starvation(self):
        policy = TenantFairnessPolicy(max_inflight_global=10, max_inflight_per_tenant=10)
        policy.enqueue("tenant-a", "msg-a1")
        policy.enqueue("tenant-a", "msg-a2")
        policy.enqueue("tenant-b", "msg-b1")
        policy.enqueue("tenant-b", "msg-b2")

        picks = [policy.dequeue_next()[0] for _ in range(4)]

        self.assertEqual(picks, ["tenant-a", "tenant-b", "tenant-a", "tenant-b"])


if __name__ == "__main__":
    unittest.main()
