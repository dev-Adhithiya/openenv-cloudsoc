import graders

# Test all maximum score cases
test_cases = [
    # Easy: all 3 actions = 0.3 + 0.3 + 0.4 = 1.0
    (["get_alerts", "describe_instances", "isolate_instance"], "easy_max"),
    # Medium: all 4 actions = 0.1 + 0.3 + 0.3 + 0.3 = 1.0
    (["get_alerts", "cloudtrail", "revoke_role", "isolate_instance"], "medium_max"),
    # Hard: fatal error (should be 0.02, not 0.01)
    (["terminate_db"], "hard_fatal"),
    # Hard: max without fatal = 0.1 + 0.1 + 0.4 + 0.4 = 1.0
    (["get_alerts", "cloudtrail", "block_ip", "isolate_instance"], "hard_max"),
]

print("=" * 60)
print("EDGE CASE SCORE TESTS")
print("=" * 60)

for trajectory, desc in test_cases:
    easy = graders.grade_easy(trajectory)
    medium = graders.grade_medium(trajectory)
    hard = graders.grade_hard(trajectory)
    
    # Check all are strictly between 0 and 1
    for score, func_name in [(easy, "easy"), (medium, "medium"), (hard, "hard")]:
        in_range = 0 < score < 1
        symbol = "✓" if in_range else "✗ OUT OF RANGE"
        print(f"{desc:20} {func_name:8} = {score:6.2f} {symbol}")
        if not in_range:
            print(f"  ERROR: Score {score} is not strictly between 0 and 1!")

print("=" * 60)
