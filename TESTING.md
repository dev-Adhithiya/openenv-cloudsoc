# Testing Guide for OpenEnv-CloudSOC

## Quick Start Testing

### 1. Quick Smoke Tests (2 minutes)
```bash
python test_cloudsoc.py --quick
```

Tests:
- Environment initialization for all 3 tasks
- Tool execution
- Deterministic seeding
- Action preconditions
- Adversarial traps

### 2. Full Unit Test Suite (10 minutes)
```bash
python test_cloudsoc.py --verbose
```

Runs 20+ unit tests covering:
- Task initialization
- Tool execution
- Validation
- Preconditions
- Reward shaping
- Adversarial traps
- Incident closure
- Timeline grading
- Multi-task campaigns
- State serialization

### 3. Single Task Manual Test (5-10 minutes per task)
```bash
# Test easy task
python -c "
from cloud_soc_env import CloudSOCEnv
import json

env = CloudSOCEnv(task='easy', seed=42)
obs, info = env.reset()

print('Task:', env.scenario['name'])
print('Max steps:', env.max_steps)
print('Required flags:', env.scenario['required_flags'])
print()

# Execute a sequence of tools
tools_to_test = [
    ('aws.soc.get_alerts', {}),
    ('aws.cloudwatch.query_basic', {'log_group': '/aws/ec2'}),
    ('aws.s3.get_bucket_policy', {'bucket_name': 'company-backup-2024'}),
]

for tool, args in tools_to_test:
    action = json.dumps({'thought': f'Test {tool}', 'tool': tool, 'args': args})
    obs, reward, term, trunc, info = env.step(action)
    print(f'{tool}: reward={reward:.2f}, error={info[\"last_action_error\"]}')
    if term:
        break

env.close()
"
```

## Advanced Manual Testing

### Test with Mock LLM Responses

```bash
# Create mock_test.py
python -c "
from cloud_soc_env import CloudSOCEnv
import json

env = CloudSOCEnv(task='easy', seed=42)
env.reset()

# Simulate agent actions
agent_actions = [
    {'thought': 'Check current alerts', 'tool': 'aws.soc.get_alerts', 'args': {}},
    {'thought': 'Query CloudWatch logs', 'tool': 'aws.cloudwatch.query_deep', 'args': {'log_group': '/aws/ec2'}},
    {'thought': 'Check S3 bucket policy', 'tool': 'aws.s3.get_bucket_policy', 'args': {'bucket_name': 'company-backup-2024'}},
    {'thought': 'List S3 objects', 'tool': 'aws.s3.list_objects', 'args': {'bucket_name': 'company-backup-2024'}},
    {'thought': 'Block public access', 'tool': 'aws.s3.block_public_access', 'args': {'bucket_name': 'company-backup-2024'}},
    {'thought': 'Close incident', 'tool': 'aws.soc.close_incident', 'args': {'timeline': ['Bucket detected', 'Creds found', 'Access blocked']}},
]

total_reward = 0
for i, action_dict in enumerate(agent_actions, 1):
    action_str = json.dumps(action_dict)
    obs, reward, term, trunc, info = env.step(action_str)
    total_reward += reward
    
    print(f'Step {i}: {action_dict[\"tool\"]}')
    print(f'  Reward: {reward:.2f}, Total: {total_reward:.2f}')
    print(f'  Flags: {len(env.state.discovered_flags)}/{len(env.scenario[\"required_flags\"])}')
    print(f'  Error: {info[\"last_action_error\"]}')
    print()
    
    if term:
        print('Episode terminated')
        break

print(f'Final: Total reward={total_reward:.2f}, Flags={len(env.state.discovered_flags)}/{len(env.scenario[\"required_flags\"])}')
"
```

### Test Preconditions

```bash
# Test: Isolate without snapshot should fail
python -c "
from cloud_soc_env import CloudSOCEnv
import json

env = CloudSOCEnv(task='easy', seed=42)
env.reset()

instance_id = list(env.state.instances.keys())[0]

# Try isolate without snapshot
action = json.dumps({
    'thought': 'Try isolate without snapshot',
    'tool': 'aws.ec2.isolate',
    'args': {'instance_id': instance_id}
})

obs, reward, term, trunc, info = env.step(action)
print('Isolate without snapshot:')
print(f'  Reward: {reward}')
print(f'  Error: {info[\"last_action_error\"]}')
print(f'  Expected: PRECONDITION_FAILED')
"
```

### Test Adversarial Trap

```bash
# Test: Terminate compromised instance
python -c "
from cloud_soc_env import CloudSOCEnv
import json

env = CloudSOCEnv(task='easy', seed=42)
env.reset()

# Find compromised instance
compromised = None
for iid, inst in env.state.instances.items():
    if inst.is_compromised:
        compromised = iid
        break

if compromised:
    action = json.dumps({
        'thought': 'Terminate compromised instance',
        'tool': 'aws.ec2.terminate',
        'args': {'instance_id': compromised}
    })
    
    obs, reward, term, trunc, info = env.step(action)
    print('Terminate compromised instance:')
    print(f'  Reward: {reward} (expected: -1.0)')
    print(f'  Terminated: {term} (expected: true)')
    print(f'  Error: {info[\"last_action_error\"]}')
else:
    print('No compromised instance found')
"
```

### Test Timeline Grading

```bash
# Test: Timeline accuracy grading
python -c "
from cloud_soc_env import CloudSOCEnv

env = CloudSOCEnv(task='easy', seed=42)
env.reset()

ground_truth = env.scenario['ground_truth_timeline']
print('Ground truth:', ground_truth)
print()

test_cases = [
    ground_truth,  # Perfect match
    ground_truth[:1],  # Partial
    ['Wrong event'],  # Wrong
    ground_truth + ['Extra event'],  # Extra
]

for i, timeline in enumerate(test_cases, 1):
    score = env._grade_timeline(timeline)
    print(f'Test {i}: {score:.2f}')
    print(f'  Timeline: {timeline}')
"
```

## Inference Testing

### Test Inference Loop (Requires HF_TOKEN)

```bash
# Set environment variables first
export API_BASE_URL="https://api.openai.com/v1"
export MODEL_NAME="gpt-4.1-mini"
export HF_TOKEN="your_token_here"

# Run single task
python inference.py --task easy --seed 42 --verbose

# Run full campaign
python inference.py --task campaign --seed 42 --verbose
```

### Expected Output Format

```
[START] task=easy env=cloudsoc model=gpt-4.1-mini
[STEP] step=1 action=aws.soc.get_alerts({}) reward=0.00 done=false error=null
[STEP] step=2 action=aws.cloudwatch.query_deep(...) reward=-0.05 done=false error=null
...
[END] success=true steps=N rewards=0.00,-0.05,0.02,...
```

## Docker Testing

### Build Docker Image

```bash
# Build
docker build -t cloudsoc:latest .

# Run
docker run --rm \
  -e API_BASE_URL="https://api.openai.com/v1" \
  -e MODEL_NAME="gpt-4.1-mini" \
  -e HF_TOKEN="your_token_here" \
  cloudsoc:latest

# Run with custom task
docker run --rm \
  -e HF_TOKEN="your_token_here" \
  cloudsoc:latest \
  python inference.py --task medium
```

### Check Resource Usage

```bash
# Monitor during run
docker stats cloudsoc

# Expected: <2 vCPU, <2GB RAM
```

## Performance Testing

### Measure Execution Time

```bash
python -c "
import time
from cloud_soc_env import CloudSOCEnv
import json

env = CloudSOCEnv(task='easy', seed=42)
start = time.time()
env.reset()

for i in range(5):
    action = json.dumps({
        'thought': 'Test',
        'tool': 'aws.soc.get_alerts',
        'args': {}
    })
    env.step(action)

elapsed = time.time() - start
print(f'5 steps in {elapsed:.2f}s ({elapsed/5:.3f}s per step)')
"
```

### Memory Usage

```bash
python -c "
import sys
from cloud_soc_env import CloudSOCEnv

env = CloudSOCEnv(task='hard', seed=42)
env.reset()

print(f'Environment size: ~{sys.getsizeof(env) / 1024:.1f} KB')
print(f'Instances: {len(env.state.instances)}')
print(f'Logs: {len(env.state.logs)}')
print(f'Alerts: {len(env.state.alerts)}')
"
```

## Debugging Tips

### Enable Verbose Logging

```python
env = CloudSOCEnv(task='easy', seed=42, verbose=True)
obs, info = env.reset()

# Check discovered flags
print('Flags:', env.state.discovered_flags)

# Check phase scores
print('Scores:', env.phase_scores)

# Check tool usage
print('Tools used:', env.tool_usage)

# Check query costs
print('Query costs:', env.query_costs)
```

### Inspect State

```python
from cloud_soc_env import CloudSOCEnv
import json

env = CloudSOCEnv(task='easy', seed=42)
env.reset()

# Export state to dict for inspection
state_dict = env.state.to_dict()
print(json.dumps(state_dict, indent=2))

# Check specific instance
instance_id = list(env.state.instances.keys())[0]
inst = env.state.instances[instance_id]
print(f'Instance {instance_id}:')
print(f'  Compromised: {inst.is_compromised}')
print(f'  Has snapshot: {inst.has_forensic_snapshot}')
print(f'  State: {inst.state.value}')
```

### Test Parser

```python
from inference import parse_llm_response
import json

test_responses = [
    # Clean JSON
    json.dumps({'thought': 'Test', 'tool': 'aws.soc.get_alerts', 'args': {}}),
    
    # Markdown code block
    '```json\n{"thought": "Test", "tool": "aws.soc.get_alerts", "args": {}}\n```',
    
    # Embedded in text
    'I will check alerts. {"thought": "Test", "tool": "aws.soc.get_alerts", "args": {}}',
    
    # Malformed JSON
    '{"thought": "Test", "tool": "aws.soc.get_alerts"',
]

for i, response in enumerate(test_responses, 1):
    parsed, error = parse_llm_response(response)
    print(f'Test {i}: {"✓" if parsed else "✗"} {error}')
```

## Continuous Integration

### GitHub Actions Example

```yaml
name: Test CloudSOC

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: 3.11
      
      - name: Install dependencies
        run: pip install -r requirements.txt
      
      - name: Run tests
        run: python test_cloudsoc.py --quick
      
      - name: Build Docker
        run: docker build -t cloudsoc:latest .
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| ModuleNotFoundError: gymnasium | `pip install gymnasium` |
| ModuleNotFoundError: openai | `pip install openai` |
| HF_TOKEN environment variable is required | Set `export HF_TOKEN="your_token"` |
| API timeout | Increase timeout in inference.py call_llm() |
| Out of memory | Use --task easy instead of hard |
| LLM response parsing fails | Check verbose output with --verbose flag |

## Test Coverage

- ✅ Unit tests: 20+ tests covering all mechanics
- ✅ Integration tests: End-to-end scenarios
- ✅ Performance tests: Time and memory profiling
- ✅ Docker tests: Container build and runtime
- ✅ Output format: Hackathon compliance validation

Run: `python test_cloudsoc.py --verbose` for full coverage report.
