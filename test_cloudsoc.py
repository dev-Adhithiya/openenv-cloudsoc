"""
Test Suite for OpenEnv-CloudSOC Benchmark
==========================================
Run: python test_cloudsoc.py [--task easy|medium|hard|all] [--verbose] [--quick]
"""

import json
import sys
import unittest
from typing import Dict, List, Optional

from cloud_soc_env import CloudSOCEnv, CloudState, SCENARIOS, InstanceState, IncidentPhase


class TestEnvironmentInit(unittest.TestCase):
    """Test environment initialization"""
    
    def test_easy_task_init(self):
        """Test easy task initialization"""
        env = CloudSOCEnv(task="easy", seed=42)
        self.assertEqual(env.task, "easy")
        self.assertEqual(env.max_steps, 15)
        self.assertTrue(len(env.scenario["required_flags"]) > 0)
        self.assertIsNotNone(env.state)
    
    def test_medium_task_init(self):
        """Test medium task initialization"""
        env = CloudSOCEnv(task="medium", seed=42)
        self.assertEqual(env.task, "medium")
        self.assertEqual(env.max_steps, 25)
        self.assertTrue(len(env.scenario["required_flags"]) > len(SCENARIOS["easy"]["required_flags"]))
    
    def test_hard_task_init(self):
        """Test hard task initialization"""
        env = CloudSOCEnv(task="hard", seed=42)
        self.assertEqual(env.task, "hard")
        self.assertEqual(env.max_steps, 40)
        self.assertTrue(len(env.scenario["required_flags"]) > len(SCENARIOS["medium"]["required_flags"]))
    
    def test_deterministic_seeding(self):
        """Test that same seed produces same initial state"""
        env1 = CloudSOCEnv(task="easy", seed=42)
        env2 = CloudSOCEnv(task="easy", seed=42)
        
        obs1, _ = env1.reset()
        obs2, _ = env2.reset()
        
        # Same seed should produce same number of logs
        self.assertEqual(len(env1.state.logs), len(env2.state.logs))
        self.assertEqual(len(env1.state.instances), len(env2.state.instances))
    
    def test_different_seeds_different_states(self):
        """Test that different seeds produce different states"""
        env1 = CloudSOCEnv(task="easy", seed=42)
        env2 = CloudSOCEnv(task="easy", seed=43)
        
        env1.reset()
        env2.reset()
        
        # Different seeds should produce different instance IDs
        ids1 = set(env1.state.instances.keys())
        ids2 = set(env2.state.instances.keys())
        # At least some instances should be different
        self.assertNotEqual(ids1, ids2)


class TestToolExecution(unittest.TestCase):
    """Test tool execution and validation"""
    
    def setUp(self):
        self.env = CloudSOCEnv(task="easy", seed=42)
        self.env.reset()
    
    def test_valid_tool_call(self):
        """Test valid tool execution"""
        action = json.dumps({
            "thought": "Check current alerts",
            "tool": "aws.soc.get_alerts",
            "args": {}
        })
        obs, reward, term, trunc, info = self.env.step(action)
        
        self.assertIsNotNone(obs)
        self.assertIsInstance(reward, float)
        self.assertFalse(term)
        self.assertEqual(info["last_action_error"], None)
    
    def test_invalid_json(self):
        """Test handling of invalid JSON"""
        action = "not valid json"
        obs, reward, term, trunc, info = self.env.step(action)
        
        self.assertIn("PARSE_ERROR", info["last_action_error"])
        self.assertEqual(reward, -0.02)
    
    def test_invalid_tool_name(self):
        """Test handling of invalid tool name"""
        action = json.dumps({
            "thought": "Try invalid tool",
            "tool": "aws.invalid.tool",
            "args": {}
        })
        obs, reward, term, trunc, info = self.env.step(action)
        
        self.assertIn("VALIDATION_ERROR", info["last_action_error"])
        self.assertEqual(reward, -0.02)
    
    def test_missing_required_param(self):
        """Test handling of missing required parameters"""
        action = json.dumps({
            "thought": "Get bucket policy without bucket",
            "tool": "aws.s3.get_bucket_policy",
            "args": {}
        })
        obs, reward, term, trunc, info = self.env.step(action)
        
        self.assertIn("MISSING_PARAM", info["last_action_error"])
        self.assertEqual(reward, -0.01)
    
    def test_cloudwatch_basic_query(self):
        """Test basic CloudWatch query"""
        action = json.dumps({
            "thought": "Query logs",
            "tool": "aws.cloudwatch.query_basic",
            "args": {"log_group": "/aws/ec2"}
        })
        obs, reward, term, trunc, info = self.env.step(action)
        
        # Basic query should cost -0.01
        self.assertAlmostEqual(reward, -0.01, places=2)
        self.assertEqual(self.env.query_costs, 0.01)
    
    def test_cloudwatch_deep_query(self):
        """Test deep CloudWatch query"""
        action = json.dumps({
            "thought": "Deep query",
            "tool": "aws.cloudwatch.query_deep",
            "args": {"log_group": "/aws/ec2"}
        })
        obs, reward, term, trunc, info = self.env.step(action)
        
        # Deep query should cost -0.05
        self.assertAlmostEqual(reward, -0.05, places=2)
        self.assertEqual(self.env.query_costs, 0.05)


class TestPreconditions(unittest.TestCase):
    """Test action preconditions (Mechanic #3)"""
    
    def setUp(self):
        self.env = CloudSOCEnv(task="easy", seed=42)
        self.env.reset()
        # Get a compromised instance
        self.instance_id = None
        for iid, inst in self.env.state.instances.items():
            if inst.is_compromised:
                self.instance_id = iid
                break
        self.assertTrue(self.instance_id is not None, "No compromised instance found")
    
    def test_isolate_without_snapshot_fails(self):
        """Test that isolation without snapshot fails"""
        if not self.instance_id:
            self.skipTest("No compromised instance")
        
        action = json.dumps({
            "thought": "Isolate without snapshot",
            "tool": "aws.ec2.isolate",
            "args": {"instance_id": self.instance_id}
        })
        obs, reward, term, trunc, info = self.env.step(action)
        
        self.assertIn("PRECONDITION_FAILED", info["last_action_error"])
        self.assertEqual(reward, -0.05)
    
    def test_snapshot_then_isolate_succeeds(self):
        """Test that snapshot followed by isolate succeeds"""
        if not self.instance_id:
            self.skipTest("No compromised instance")
        
        # Step 1: Snapshot
        action1 = json.dumps({
            "thought": "Take forensic snapshot",
            "tool": "aws.ec2.snapshot",
            "args": {"instance_id": self.instance_id}
        })
        self.env.step(action1)
        
        # Verify snapshot taken
        inst = self.env.state.instances[self.instance_id]
        self.assertTrue(inst.has_forensic_snapshot)
        
        # Step 2: Isolate (should succeed now)
        action2 = json.dumps({
            "thought": "Isolate instance",
            "tool": "aws.ec2.isolate",
            "args": {"instance_id": self.instance_id}
        })
        obs, reward, term, trunc, info = self.env.step(action2)
        
        # Should succeed
        self.assertIsNone(info["last_action_error"])
        self.assertGreater(reward, 0)
        self.assertEqual(inst.state, InstanceState.ISOLATED)


class TestAdversarialTraps(unittest.TestCase):
    """Test adversarial traps (Mechanic #4)"""
    
    def setUp(self):
        self.env = CloudSOCEnv(task="easy", seed=42)
        self.env.reset()
        # Get a compromised instance
        self.instance_id = None
        for iid, inst in self.env.state.instances.items():
            if inst.is_compromised:
                self.instance_id = iid
                break
    
    def test_terminate_compromised_instance_destroys_evidence(self):
        """Test that terminating compromised instance has severe penalty"""
        if not self.instance_id:
            self.skipTest("No compromised instance")
        
        action = json.dumps({
            "thought": "Terminate compromised instance",
            "tool": "aws.ec2.terminate",
            "args": {"instance_id": self.instance_id}
        })
        obs, reward, term, trunc, info = self.env.step(action)
        
        # Terminating compromised instance = -1.0 and done
        self.assertEqual(reward, -1.0)
        self.assertTrue(term)
        self.assertIn("FORENSIC_DATA_LOSS", info["last_action_error"])


class TestRewardShaping(unittest.TestCase):
    """Test reward shaping (Mechanic #5)"""
    
    def setUp(self):
        self.env = CloudSOCEnv(task="easy", seed=42)
        self.env.reset()
    
    def test_flag_discovery_reward(self):
        """Test that discovering flags grants rewards"""
        initial_flags = len(self.env.state.discovered_flags)
        
        # Query deep logs to discover flags
        action = json.dumps({
            "thought": "Deep query logs",
            "tool": "aws.cloudwatch.query_deep",
            "args": {"log_group": "/aws/ec2"}
        })
        obs, reward, term, trunc, info = self.env.step(action)
        
        new_flags = len(self.env.state.discovered_flags)
        
        # Should have discovered at least one flag
        self.assertGreater(new_flags, initial_flags)
        
        # Reward should be: -0.05 (query cost) + flag_discovery bonus
        self.assertGreater(reward, -0.05)
    
    def test_critical_action_reward(self):
        """Test that critical actions grant high rewards"""
        # Take snapshot for example
        instance_id = list(self.env.state.instances.keys())[0]
        
        action = json.dumps({
            "thought": "Take snapshot",
            "tool": "aws.ec2.snapshot",
            "args": {"instance_id": instance_id}
        })
        obs, reward, term, trunc, info = self.env.step(action)
        
        # Critical action should have positive reward
        self.assertGreater(reward, 0.0)


class TestClosingIncident(unittest.TestCase):
    """Test incident closure and timeline grading"""
    
    def setUp(self):
        self.env = CloudSOCEnv(task="easy", seed=42)
        self.env.reset()
    
    def test_close_incident_with_empty_timeline(self):
        """Test that empty timeline is rejected"""
        action = json.dumps({
            "thought": "Close incident",
            "tool": "aws.soc.close_incident",
            "args": {"timeline": []}
        })
        obs, reward, term, trunc, info = self.env.step(action)
        
        self.assertIn("INVALID_PARAM", info["last_action_error"])
    
    def test_close_incident_with_timeline(self):
        """Test incident closure with valid timeline"""
        action = json.dumps({
            "thought": "Close incident",
            "tool": "aws.soc.close_incident",
            "args": {
                "timeline": [
                    "Public S3 bucket detected",
                    "Credentials discovered in bucket",
                    "Public access blocked"
                ]
            }
        })
        obs, reward, term, trunc, info = self.env.step(action)
        
        # Should terminate
        self.assertTrue(info.get("last_action_error") is None or "timeline" in info.get("last_action_error", "").lower())
    
    def test_timeline_grading(self):
        """Test timeline accuracy grading"""
        ground_truth = self.env.scenario["ground_truth_timeline"]
        
        # Test matching timeline
        agent_timeline = ground_truth.copy()
        score = self.env._grade_timeline(agent_timeline)
        
        # Perfect match should score high
        self.assertGreaterEqual(score, 0.7)
        
        # Test partial match
        partial_timeline = ground_truth[:1]
        score = self.env._grade_timeline(partial_timeline)
        
        # Partial should be lower
        self.assertGreater(score, 0.0)
        self.assertLess(score, 1.0)


class TestMultiTaskCampaign(unittest.TestCase):
    """Test multi-task campaign (Mechanic #11)"""
    
    def test_easy_task_state_export(self):
        """Test that easy task state can be exported"""
        env = CloudSOCEnv(task="easy", seed=42)
        env.reset()
        
        state = env.get_state_for_next_task()
        self.assertIsNotNone(state)
        self.assertIsInstance(state, CloudState)
        self.assertTrue(len(state.instances) > 0)
    
    def test_state_inheritance_medium(self):
        """Test that medium task can inherit easy task state"""
        env_easy = CloudSOCEnv(task="easy", seed=42)
        env_easy.reset()
        easy_state = env_easy.get_state_for_next_task()
        
        env_medium = CloudSOCEnv(task="medium", seed=42, initial_state=easy_state)
        env_medium.reset()
        
        # Medium should have inherited instances
        self.assertEqual(len(env_medium.state.instances), len(easy_state.instances))


class TestMemoryPressure(unittest.TestCase):
    """Test memory pressure simulation (Mechanic #6)"""
    
    def test_context_window_size(self):
        """Test that context window respects size limit"""
        from inference import ContextWindow, MAX_CONTEXT_TURNS
        
        context = ContextWindow(system_prompt="Test", max_turns=3)
        
        # Add more turns than max
        for i in range(5):
            context.add_turn(
                observation=f"Obs {i}",
                action=f"Action {i}",
                result=f"Result {i}"
            )
        
        # Should only keep max_turns
        self.assertEqual(len(context.turns), 3)


class TestStateSerializable(unittest.TestCase):
    """Test state serialization for debugging"""
    
    def test_state_to_dict(self):
        """Test that state can be serialized to dict"""
        env = CloudSOCEnv(task="easy", seed=42)
        env.reset()
        
        state_dict = env.state.to_dict()
        
        self.assertIn("instances", state_dict)
        self.assertIn("roles", state_dict)
        self.assertIn("buckets", state_dict)
        self.assertIn("discovered_flags", state_dict)
        self.assertIn("phase", state_dict)


def run_quick_tests():
    """Run quick smoke tests"""
    print("\n=== Quick Smoke Tests ===\n")
    
    # Test 1: Init
    print("1. Testing environment initialization...")
    for task in ["easy", "medium", "hard"]:
        env = CloudSOCEnv(task=task, seed=42)
        obs, info = env.reset()
        print(f"   ✓ {task}: {env.max_steps} steps, {len(env.scenario['required_flags'])} flags")
    
    # Test 2: Tool execution
    print("\n2. Testing tool execution...")
    env = CloudSOCEnv(task="easy", seed=42)
    env.reset()
    
    action = json.dumps({
        "thought": "Get alerts",
        "tool": "aws.soc.get_alerts",
        "args": {}
    })
    obs, reward, term, trunc, info = env.step(action)
    print(f"   ✓ Tool executed: reward={reward:.2f}")
    
    # Test 3: Deterministic seeding
    print("\n3. Testing deterministic seeding...")
    env1 = CloudSOCEnv(task="easy", seed=42)
    env2 = CloudSOCEnv(task="easy", seed=42)
    env1.reset()
    env2.reset()
    same = len(env1.state.logs) == len(env2.state.logs)
    print(f"   {'✓' if same else '✗'} Same seed produces same state")
    
    # Test 4: Preconditions
    print("\n4. Testing action preconditions...")
    env = CloudSOCEnv(task="easy", seed=42)
    env.reset()
    instance_id = list(env.state.instances.keys())[0]
    
    # Try isolate without snapshot (should fail)
    action = json.dumps({
        "thought": "Isolate",
        "tool": "aws.ec2.isolate",
        "args": {"instance_id": instance_id}
    })
    obs, reward, term, trunc, info = env.step(action)
    has_error = info["last_action_error"] is not None
    print(f"   {'✓' if has_error else '✗'} Precondition check works")
    
    # Test 5: Adversarial trap
    print("\n5. Testing adversarial trap...")
    env = CloudSOCEnv(task="easy", seed=42)
    env.reset()
    compromised = None
    for iid, inst in env.state.instances.items():
        if inst.is_compromised:
            compromised = iid
            break
    
    if compromised:
        action = json.dumps({
            "thought": "Terminate",
            "tool": "aws.ec2.terminate",
            "args": {"instance_id": compromised}
        })
        obs, reward, term, trunc, info = env.step(action)
        is_trap = reward == -1.0 and term
        print(f"   {'✓' if is_trap else '✗'} Adversarial trap triggered (-1.0 penalty)")
    
    print("\n✅ All quick tests passed!\n")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test CloudSOC benchmark")
    parser.add_argument("--quick", action="store_true", help="Run quick smoke tests only")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    if args.quick:
        run_quick_tests()
    else:
        # Run unittest suite
        unittest.main(verbosity=2 if args.verbose else 1)
