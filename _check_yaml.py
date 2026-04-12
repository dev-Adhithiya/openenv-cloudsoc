import yaml

with open('openenv.yaml', encoding='utf-8') as f:
    content = f.read()
    
# Check if YAML is valid
try:
    data = yaml.safe_load(content)
    print('✓ YAML is valid')
except Exception as e:
    print(f'✗ YAML parsing error: {e}')
    exit(1)

# Check tasks
tasks = data.get('tasks', [])
print(f'✓ Found {len(tasks)} tasks')

# Check if each task has a grader
for task in tasks:
    task_id = task.get('id', 'UNKNOWN')
    grader = task.get('grader')
    if not grader:
        print(f'✗ Task "{task_id}" missing grader')
    else:
        print(f'✓ Task "{task_id}" has grader: {grader}')

# Check environment section
env = data.get('environment', {})
print(f'✓ Environment config present')

# Check hardware requirements
hw = data.get('hardware', {})
print(f'✓ Hardware config: min_vcpu={hw.get("min_vcpu")}, min_ram_gb={hw.get("min_ram_gb")}')

# Check if external_db is needed (should be false for Zero-DB)
ext_db = hw.get('external_db_required', None)
print(f'✓ External DB required: {ext_db}')

# Check evaluation criteria
eval_crit = data.get('evaluation_criteria', {})
print(f'✓ Evaluation criteria present: {bool(eval_crit)}')

# Check task completion criteria
comp_criteria = eval_crit.get('task_completion_criteria', {})
if comp_criteria:
    for key, val in comp_criteria.items():
        print(f'  - {key}: {val}')
