import yaml
import graders

# Check YAML tasks
with open('openenv.yaml', encoding='utf-8') as f:
    data = yaml.safe_load(f)
    tasks = data.get('tasks', [])

print("=" * 50)
print("TASKS WITH GRADERS")
print("=" * 50)
print(f"Total tasks: {len(tasks)}\n")

for i, task in enumerate(tasks, 1):
    task_id = task.get('id', 'UNKNOWN')
    grader_ref = task.get('grader', 'NONE')
    print(f"Task {i}: id={task_id}, grader={grader_ref}")

# Test score ranges
print("\n" + "=" * 50)
print("SCORE RANGE TESTS")
print("=" * 50)

test_cases = [
    ([], "empty trajectory"),
    (None, "None trajectory"),
    (["get_alerts"], "basic action"),
    (["get_alerts", "describe_instances", "isolate_instance"], "all easy actions"),
]

for trajectory, desc in test_cases:
    try:
        easy_score = graders.grade_easy(trajectory)
        medium_score = graders.grade_medium(trajectory)
        hard_score = graders.grade_hard(trajectory)
        
        # Verify scores are in valid range
        valid_easy = 0.01 <= easy_score <= 0.99
        valid_medium = 0.01 <= medium_score <= 0.99
        valid_hard = 0.01 <= hard_score <= 0.99
        
        print(f"\n{desc}: {trajectory}")
        print(f"  easy:   {easy_score} {'✓' if valid_easy else '✗ OUT OF RANGE'}")
        print(f"  medium: {medium_score} {'✓' if valid_medium else '✗ OUT OF RANGE'}")
        print(f"  hard:   {hard_score} {'✓' if valid_hard else '✗ OUT OF RANGE'}")
    except Exception as e:
        print(f"\n{desc}: ERROR - {e}")

print("\n" + "=" * 50)
