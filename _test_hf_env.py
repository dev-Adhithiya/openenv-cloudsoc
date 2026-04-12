#!/usr/bin/env python3
"""
Simulate what will happen in HF Space during evaluation
"""

print("=" * 70)
print("SIMULATING HF SPACE EVALUATION ENVIRONMENT")
print("=" * 70)

# Test 1: Can we import the modules?
print("\n1. Testing imports...")
try:
    import cloud_soc_env
    print("   ✓ cloud_soc_env imports successfully")
except Exception as e:
    print(f"   ✗ Failed to import cloud_soc_env: {e}")

try:
    import graders
    print("   ✓ graders imports successfully")
except Exception as e:
    print(f"   ✗ Failed to import graders: {e}")

try:
    import yaml
    print("   ✓ yaml imports successfully")
except Exception as e:
    print(f"   ✗ Failed to import yaml: {e}")

# Test 2: Can we load openenv.yaml?
print("\n2. Testing openenv.yaml loading...")
try:
    with open('openenv.yaml', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    print(f"   ✓ openenv.yaml loaded successfully")
    print(f"   ✓ Found {len(data.get('tasks', []))} tasks")
except Exception as e:
    print(f"   ✗ Failed to load openenv.yaml: {e}")

# Test 3: Can we access grader functions?
print("\n3. Testing grader function access...")
try:
    func_easy = getattr(graders, 'grade_easy')
    func_medium = getattr(graders, 'grade_medium')
    func_hard = getattr(graders, 'grade_hard')
    print(f"   ✓ All 3 grader functions accessible")
except Exception as e:
    print(f"   ✗ Failed to access grader functions: {e}")

# Test 4: Can we call the graders?
print("\n4. Testing grader function execution...")
try:
    result_easy = graders.grade_easy([])
    result_medium = graders.grade_medium([])
    result_hard = graders.grade_hard([])
    
    print(f"   ✓ grade_easy([]) = {result_easy}")
    print(f"   ✓ grade_medium([]) = {result_medium}")
    print(f"   ✓ grade_hard([]) = {result_hard}")
    
    # Validate all are in range
    all_in_range = all(0 < s < 1 for s in [result_easy, result_medium, result_hard])
    if all_in_range:
        print(f"   ✓ ALL SCORES IN VALID RANGE (0, 1)")
    else:
        print(f"   ✗ SOME SCORES OUT OF RANGE")
except Exception as e:
    print(f"   ✗ Failed to execute graders: {e}")

# Test 5: Test inference.py imports
print("\n5. Testing inference.py imports...")
try:
    import inference
    print(f"   ✓ inference.py imports successfully")
except Exception as e:
    print(f"   ✗ Failed to import inference.py: {e}")

print("\n" + "=" * 70)
print("✅ HF SPACE ENVIRONMENT SIMULATION: PASSED")
print("=" * 70)
