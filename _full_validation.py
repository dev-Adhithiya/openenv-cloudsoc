import yaml
import graders

print("=" * 70)
print("COMPREHENSIVE VALIDATION TEST")
print("=" * 70)

# Load YAML
with open('openenv.yaml', encoding='utf-8') as f:
    data = yaml.safe_load(f)

tasks = data.get('tasks', [])

print(f"\nFound {len(tasks)} tasks:\n")

# Test each task
all_valid = True
for task_config in tasks:
    task_id = task_config['id']
    grader_ref = task_config['grader']
    
    print(f"Task: {task_id} → {grader_ref}")
    
    # Parse grader reference
    parts = grader_ref.split(':')
    if len(parts) != 2:
        print(f"  ✗ INVALID grader reference format: {grader_ref}")
        all_valid = False
        continue
    
    module_name, func_name = parts
    
    # Map module to actual grader function
    if module_name == "graders":
        if func_name == "grade_easy":
            grader_func = graders.grade_easy
        elif func_name == "grade_medium":
            grader_func = graders.grade_medium
        elif func_name == "grade_hard":
            grader_func = graders.grade_hard
        else:
            print(f"  ✗ Unknown grader function: {func_name}")
            all_valid = False
            continue
    else:
        print(f"  ✗ Unknown module: {module_name}")
        all_valid = False
        continue
    
    # Test the grader with various inputs
    test_inputs = [
        (None, "None"),
        ([], "empty list"),
        (["action"], "single action"),
        (["a", "b", "c"], "multiple actions"),
    ]
    
    task_scores_valid = True
    for trajectory, desc in test_inputs:
        try:
            score = grader_func(trajectory)
            
            # Validate score is strictly between 0 and 1
            if not (0 < score < 1):
                print(f"  ✗ Score out of range: {score} (not strictly between 0 and 1) for {desc}")
                task_scores_valid = False
                all_valid = False
            # Validate score is a number
            elif not isinstance(score, (int, float)):
                print(f"  ✗ Score is not a number: {type(score)} for {desc}")
                task_scores_valid = False
                all_valid = False
        except Exception as e:
            print(f"  ✗ Exception calling grader for {desc}: {e}")
            task_scores_valid = False
            all_valid = False
    
    if task_scores_valid:
        print(f"  ✓ All score tests passed")
    
    print()

print("=" * 70)
if all_valid:
    print("✅ ALL VALIDATION CHECKS PASSED!")
    print("   - 3 tasks found with graders")
    print("   - All grader references valid")
    print("   - All scores strictly in range (0, 1)")
else:
    print("❌ VALIDATION FAILED")

print("=" * 70)
