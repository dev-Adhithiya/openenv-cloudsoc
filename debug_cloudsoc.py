#!/usr/bin/env python
"""
Debug Script for OpenEnv-CloudSOC
==================================
Interactive debugging and exploration tool

Usage:
    python debug_cloudsoc.py [--task easy|medium|hard] [--seed 42]
"""

import json
import sys
from cloud_soc_env import CloudSOCEnv, InstanceState


def print_section(title):
    """Print a formatted section header"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def explore_environment(task="easy", seed=42):
    """Interactively explore the environment"""
    
    print_section(f"CloudSOC Environment: {task.upper()}")
    
    env = CloudSOCEnv(task=task, seed=seed)
    obs, info = env.reset()
    
    print(f"Scenario: {env.scenario['name']}")
    print(f"Description: {env.scenario['description']}")
    print(f"Max Steps: {env.max_steps}")
    print(f"Difficulty Multiplier: {env.scenario['difficulty_multiplier']}")
    print()
    
    # =========================================================================
    # SECTION: INITIAL STATE
    # =========================================================================
    print_section("Initial Cloud State")
    
    # Instances
    print(f"EC2 Instances ({len(env.state.instances)}):")
    for iid, inst in env.state.instances.items():
        print(f"  {iid}")
        print(f"    State: {inst.state.value}")
        print(f"    Compromised: {inst.is_compromised}")
        print(f"    Roles: {inst.attached_roles}")
        print(f"    Has Snapshot: {inst.has_forensic_snapshot}")
    print()
    
    # IAM Roles
    print(f"IAM Roles ({len(env.state.roles)}):")
    for name, role in env.state.roles.items():
        print(f"  {name}")
        print(f"    Policies: {', '.join(role.policies[:2])}...")
        print(f"    Compromised: {role.is_compromised}")
        print(f"    Detached: {role.is_detached}")
        print(f"    Has Backdoor: {role.has_backdoor}")
    print()
    
    # S3 Buckets
    print(f"S3 Buckets ({len(env.state.buckets)}):")
    for name, bucket in env.state.buckets.items():
        print(f"  {name}")
        print(f"    Public: {bucket.is_public}")
        print(f"    Contains Credentials: {bucket.contains_credentials}")
        print(f"    Public Access Blocked: {bucket.public_access_blocked}")
    print()
    
    # =========================================================================
    # SECTION: ALERTS AND LOGS
    # =========================================================================
    print_section("Security Alerts and Indicators")
    
    print(f"SOC Alerts ({len(env.state.alerts)}):")
    for i, alert in enumerate(env.state.alerts[:5], 1):
        print(f"  [{i}] {alert.alert_id}: {alert.title}")
        print(f"      Severity: {alert.severity} | Source: {alert.source}")
        print(f"      True Positive: {alert.is_true_positive}")
    print()
    
    print(f"CloudWatch Logs ({len(env.state.logs)} total):")
    
    # Categorize logs
    attack_logs = [log for log in env.state.logs if log.is_attack_indicator]
    red_herrings = [log for log in env.state.logs if log.is_red_herring]
    noise = [log for log in env.state.logs if log.is_noise]
    
    print(f"  Attack Indicators: {len(attack_logs)}")
    for log in attack_logs[:3]:
        print(f"    [{log.timestamp}] {log.message}")
    print()
    
    print(f"  Red Herrings: {len(red_herrings)}")
    for log in red_herrings[:2]:
        print(f"    [{log.timestamp}] {log.message}")
    print()
    
    print(f"  Noise: {len(noise)}")
    print(f"    (Normal operational logs and benign activity)")
    print()
    
    # =========================================================================
    # SECTION: INCIDENT RESPONSE OBJECTIVES
    # =========================================================================
    print_section("Incident Response Objectives")
    
    print(f"Phase Weights:")
    for phase, weight in env.scenario["phase_weights"].items():
        print(f"  {phase}: {weight:.0%}")
    print()
    
    print(f"Required Flags ({len(env.scenario['required_flags'])} to discover):")
    for flag in env.scenario["required_flags"]:
        print(f"  • {flag}")
    print()
    
    print(f"Ground Truth Timeline:")
    for i, event in enumerate(env.scenario["ground_truth_timeline"], 1):
        print(f"  {i}. {event}")
    print()
    
    if "mitre_techniques" in env.scenario:
        print(f"MITRE ATT&CK Techniques:")
        for tech in env.scenario["mitre_techniques"]:
            print(f"  • {tech}")
        print()
    
    # =========================================================================
    # SECTION: INTERACTIVE TOOL TESTING
    # =========================================================================
    print_section("Interactive Tool Testing")
    
    test_sequence = [
        ("Get SOC Alerts", "aws.soc.get_alerts", {}),
        ("Query CloudWatch Basic", "aws.cloudwatch.query_basic", {"log_group": "/aws/ec2"}),
        ("Describe EC2 Instances", "aws.ec2.describe", {}),
        ("Check S3 Bucket Policy", "aws.s3.get_bucket_policy", {"bucket_name": "company-backup-2024"}),
    ]
    
    print("Executing test sequence...\n")
    
    total_reward = 0
    for i, (description, tool, args) in enumerate(test_sequence, 1):
        action = json.dumps({
            "thought": f"Test: {description}",
            "tool": tool,
            "args": args
        })
        
        obs, reward, term, trunc, info = env.step(action)
        total_reward += reward
        
        print(f"Step {i}: {description}")
        print(f"  Tool: {tool}")
        print(f"  Reward: {reward:+.2f}")
        print(f"  Cumulative: {total_reward:+.2f}")
        if info.get("last_action_error"):
            print(f"  Error: {info['last_action_error']}")
        print()
    
    # =========================================================================
    # SECTION: PROGRESS TRACKING
    # =========================================================================
    print_section("Progress Tracking")
    
    print(f"Discovered Flags: {len(env.state.discovered_flags)}/{len(env.scenario['required_flags'])}")
    if env.state.discovered_flags:
        for flag in env.state.discovered_flags:
            print(f"  ✓ {flag}")
    print()
    
    print(f"Tool Usage Analytics:")
    for tool, count in sorted(env.tool_usage.items(), key=lambda x: x[1], reverse=True):
        print(f"  {tool}: {count} calls")
    print()
    
    print(f"Resource Costs:")
    print(f"  Query Costs: {env.query_costs:.2f}")
    print(f"  Total Reward: {total_reward:.2f}")
    print()
    
    print(f"Phase Scores:")
    for phase, score in env.phase_scores.items():
        print(f"  {phase}: {score:.2f}")
    print()
    
    # =========================================================================
    # SECTION: FINAL SCORING
    # =========================================================================
    print_section("Final Scoring Breakdown")
    
    final_scores = env.calculate_final_score()
    for key, value in final_scores.items():
        if key == "weighted_total":
            print(f"\n{'FINAL SCORE': ^40} {value:.3f}")
        else:
            print(f"  {key:20s}: {value:.3f}")
    print()
    
    # =========================================================================
    # SECTION: SYSTEM PROMPT PREVIEW
    # =========================================================================
    print_section("LLM System Prompt (Preview)")
    
    prompt = env.get_system_prompt()
    lines = prompt.split('\n')
    print('\n'.join(lines[:30]))
    print(f"\n... ({len(lines)} lines total)\n")
    
    env.close()


def test_preconditions(task="easy", seed=42):
    """Test action precondition checking"""
    
    print_section("Testing Action Preconditions")
    
    env = CloudSOCEnv(task=task, seed=seed)
    env.reset()
    
    # Find a compromised instance
    instance_id = None
    for iid, inst in env.state.instances.items():
        if inst.is_compromised:
            instance_id = iid
            break
    
    if not instance_id:
        print("No compromised instance found!")
        return
    
    print(f"Using instance: {instance_id}")
    print()
    
    # TEST 1: Isolate without snapshot
    print("TEST 1: Try to isolate without snapshot")
    print("-" * 40)
    action = json.dumps({
        "thought": "Isolate instance",
        "tool": "aws.ec2.isolate",
        "args": {"instance_id": instance_id}
    })
    obs, reward, term, trunc, info = env.step(action)
    print(f"Reward: {reward}")
    print(f"Error: {info['last_action_error']}")
    print(f"Instance still has snapshot: {not env.state.instances[instance_id].has_forensic_snapshot}")
    print()
    
    # Reset for next test
    env = CloudSOCEnv(task=task, seed=seed)
    env.reset()
    
    # TEST 2: Snapshot then isolate
    print("TEST 2: Snapshot followed by isolate (should succeed)")
    print("-" * 40)
    
    # Step 1: Snapshot
    action = json.dumps({
        "thought": "Create forensic snapshot",
        "tool": "aws.ec2.snapshot",
        "args": {"instance_id": instance_id}
    })
    obs, reward1, term1, trunc1, info1 = env.step(action)
    print(f"Snapshot: reward={reward1}, error={info1['last_action_error']}")
    
    # Step 2: Isolate
    action = json.dumps({
        "thought": "Isolate instance",
        "tool": "aws.ec2.isolate",
        "args": {"instance_id": instance_id}
    })
    obs, reward2, term2, trunc2, info2 = env.step(action)
    print(f"Isolate: reward={reward2}, error={info2['last_action_error']}")
    print(f"Instance state: {env.state.instances[instance_id].state.value}")
    print()
    
    env.close()


def test_adversarial_trap(task="easy", seed=42):
    """Test adversarial trap - terminating compromised instance"""
    
    print_section("Testing Adversarial Trap: Instance Termination")
    
    env = CloudSOCEnv(task=task, seed=seed)
    env.reset()
    
    # Find a compromised instance
    instance_id = None
    for iid, inst in env.state.instances.items():
        if inst.is_compromised:
            instance_id = iid
            break
    
    if not instance_id:
        print("No compromised instance found!")
        return
    
    print(f"Compromised instance: {instance_id}")
    print()
    
    print("Attempting to terminate compromised instance...")
    print("-" * 40)
    
    action = json.dumps({
        "thought": "Terminate the compromised instance",
        "tool": "aws.ec2.terminate",
        "args": {"instance_id": instance_id}
    })
    
    obs, reward, term, trunc, info = env.step(action)
    
    print(f"Reward: {reward} (EXPECTED: -1.0)")
    print(f"Terminated: {term} (EXPECTED: true)")
    print(f"Error: {info['last_action_error']}")
    print(f"Instance state: {env.state.instances[instance_id].state.value}")
    print()
    
    if reward == -1.0 and term:
        print("✓ ADVERSARIAL TRAP TRIGGERED!")
        print("  The agent made a critical error by destroying forensic evidence.")
    else:
        print("✗ Trap not triggered as expected")
    
    env.close()


def main():
    """Main debug menu"""
    
    if len(sys.argv) > 1 and sys.argv[1] == "--quick":
        explore_environment(task="easy", seed=42)
        return
    
    while True:
        print("\n" + "="*60)
        print("  CloudSOC Debug Menu")
        print("="*60)
        print("\n1. Explore Environment (Easy)")
        print("2. Explore Environment (Medium)")
        print("3. Explore Environment (Hard)")
        print("4. Test Preconditions")
        print("5. Test Adversarial Trap")
        print("6. Exit")
        
        choice = input("\nSelect option (1-6): ").strip()
        
        if choice == "1":
            explore_environment(task="easy", seed=42)
        elif choice == "2":
            explore_environment(task="medium", seed=42)
        elif choice == "3":
            explore_environment(task="hard", seed=42)
        elif choice == "4":
            test_preconditions(task="easy", seed=42)
        elif choice == "5":
            test_adversarial_trap(task="easy", seed=42)
        elif choice == "6":
            print("\nGoodbye!")
            break
        else:
            print("Invalid option!")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--quick":
        explore_environment(task="easy", seed=42)
    else:
        main()
