# OpenEnv-CloudSOC - Testing & Deployment Guide

## Complete Testing Strategy

### Level 1: Quick Validation (2 minutes)

```bash
python test_cloudsoc.py --quick
```

**What it tests:**
- ✓ All 3 difficulty levels load correctly
- ✓ Basic tool execution works
- ✓ Deterministic seeding produces consistent states
- ✓ Action preconditions are enforced
- ✓ Adversarial traps trigger correctly

**Expected output:**
```
=== Quick Smoke Tests ===

1. Testing environment initialization...
   ✓ easy: 15 steps, 3 flags
   ✓ medium: 25 steps, 4 flags
   ✓ hard: 40 steps, 7 flags
2. Testing tool execution...
   ✓ Tool executed: reward=0.00
...
✅ All quick tests passed!
```

### Level 2: Unit Tests (10 minutes)

```bash
python test_cloudsoc.py --verbose
```

**Coverage:**
- Environment initialization (all tasks)
- Tool execution and validation (20+ tools)
- JSON parsing and error handling
- Action preconditions
- Reward shaping
- Adversarial traps
- Incident closure and timeline grading
- Multi-task campaigns
- State serialization

**20+ individual tests** covering all 12 mechanics and enhancements.

### Level 3: Interactive Debugging (5-15 minutes)

```bash
# Quick environment exploration
python debug_cloudsoc.py --quick

# Interactive menu (choose options)
python debug_cloudsoc.py
```

**What you can do:**
1. Explore initial cloud state (instances, roles, buckets, logs)
2. See security alerts and indicators
3. Execute sample tool sequences
4. Track progress and scoring
5. Test preconditions enforcement
6. Test adversarial traps
7. View system prompts

### Level 4: Manual Inference Testing (Requires LLM)

```bash
# Set credentials
export HF_TOKEN="your_token"
export API_BASE_URL="https://api.openai.com/v1"
export MODEL_NAME="gpt-4.1-mini"

# Run single task with LLM
python inference.py --task easy --seed 42 --verbose

# Run full campaign
python inference.py --task campaign --seed 42
```

**Expected output format:**
```
[START] task=easy env=cloudsoc model=gpt-4.1-mini
[STEP] step=1 action=aws.soc.get_alerts({}) reward=0.00 done=false error=null
[STEP] step=2 action=aws.cloudwatch.query_deep(...) reward=-0.03 done=false error=null
...
[END] success=true steps=N rewards=0.00,-0.03,0.02,...
```

### Level 5: Docker Deployment

```bash
# Build
docker build -t cloudsoc:latest .

# Run with environment variables
docker run --rm \
  -e HF_TOKEN="your_token" \
  -e API_BASE_URL="https://api.openai.com/v1" \
  -e MODEL_NAME="gpt-4.1-mini" \
  cloudsoc:latest

# Monitor resources
docker stats cloudsoc

# Check logs
docker logs cloudsoc
```

**Expected resource usage:**
- CPU: < 2 vCPU
- RAM: < 2 GB
- Init time: < 5 seconds
- Per-step time: 0.5-3 seconds (depends on LLM latency)

---

## File Structure

```
.
├── cloud_soc_env.py          # Core environment (65 KB)
├── inference.py               # Inference loop (18 KB)
├── openenv.yaml              # Benchmark spec (11 KB)
├── requirements.txt          # Dependencies
├── Dockerfile                # Docker build
├── README.md                 # Main documentation
├── TESTING.md               # Detailed testing guide
├── test_cloudsoc.py         # Unit test suite
└── debug_cloudsoc.py        # Interactive debugger
```

---

## Quick Test Commands Reference

### Environment Checks

```bash
# Check syntax
python -m py_compile cloud_soc_env.py inference.py

# Test imports
python -c "from cloud_soc_env import CloudSOCEnv; print('OK')"

# Test basic operation
python -c "
from cloud_soc_env import CloudSOCEnv
import json
env = CloudSOCEnv(task='easy', seed=42)
obs, info = env.reset()
action = json.dumps({'thought': 'Test', 'tool': 'aws.soc.get_alerts', 'args': {}})
obs, reward, _, _, info = env.step(action)
print(f'Reward: {reward}, Flags: {len(env.state.discovered_flags)}')
"
```

### Precondition Tests

```bash
# Test preconditions
python debug_cloudsoc.py --quick 2>&1 | grep -A 5 "Precondition"

# Run specific test
python test_cloudsoc.py TestPreconditions --verbose
```

### Tool Tests

```bash
# Test all tools execute without error
python -c "
from cloud_soc_env import CloudSOCEnv
import json

env = CloudSOCEnv(task='easy', seed=42)
env.reset()

tools = [
    ('aws.soc.get_alerts', {}),
    ('aws.guardduty.get_findings', {}),
    ('aws.cloudtrail.lookup_events', {}),
    ('aws.config.get_compliance', {}),
]

for tool, args in tools:
    action = json.dumps({'thought': 'Test', 'tool': tool, 'args': args})
    obs, reward, term, trunc, info = env.step(action)
    print(f'{tool}: {\"OK\" if info[\"last_action_error\"] is None else \"ERROR\"}')
"
```

### Performance Tests

```bash
# Measure throughput
python -c "
import time
from cloud_soc_env import CloudSOCEnv
import json

env = CloudSOCEnv(task='easy', seed=42)
env.reset()

start = time.time()
for i in range(10):
    action = json.dumps({'thought': 'Test', 'tool': 'aws.soc.get_alerts', 'args': {}})
    env.step(action)

elapsed = time.time() - start
print(f'10 steps: {elapsed:.2f}s ({elapsed/10*1000:.0f}ms per step)')
"
```

### Memory Tests

```bash
# Check memory footprint
python -c "
import sys
from cloud_soc_env import CloudSOCEnv

env = CloudSOCEnv(task='hard', seed=42)
env.reset()

print(f'Environment: ~{sys.getsizeof(env) / 1024:.1f} KB')
print(f'Instances: {len(env.state.instances)}')
print(f'Logs: {len(env.state.logs)}')
print(f'Alerts: {len(env.state.alerts)}')
print(f'Credentials: {len(env.state.credentials)}')
"
```

---

## Validation Checklist

- [ ] **Syntax**: `python -m py_compile cloud_soc_env.py inference.py`
- [ ] **Imports**: `python -c "from cloud_soc_env import *"`
- [ ] **Quick Tests**: `python test_cloudsoc.py --quick` (all pass)
- [ ] **Unit Tests**: `python test_cloudsoc.py --verbose` (all pass)
- [ ] **Tool Tests**: All 24 tools execute without errors
- [ ] **Preconditions**: Enforced correctly (test with debug script)
- [ ] **Adversarial Traps**: Terminate = -1.0 reward
- [ ] **Timeline Grading**: Perfect match scores >= 0.7
- [ ] **Memory**: < 2 GB for hard task
- [ ] **Speed**: Each step < 3 seconds (without LLM)
- [ ] **Docker Build**: Image builds successfully
- [ ] **Docker Run**: Runs and produces expected output
- [ ] **Output Format**: Matches hackathon [START]/[STEP]/[END] spec

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `ModuleNotFoundError: gymnasium` | `pip install -r requirements.txt` |
| `ModuleNotFoundError: openai` | `pip install -r requirements.txt` |
| `HF_TOKEN is required` | Set `export HF_TOKEN="your_token"` |
| Test fails: "No compromised instance" | Try different seed (e.g., --seed 1) |
| Parser fails on LLM response | Check response format in verbose mode |
| Docker build fails | Run `docker system prune` and retry |
| Out of memory | Use --task easy instead of hard |
| LLM timeout | Increase timeout in inference.py |

---

## CI/CD Integration

### GitHub Actions

```yaml
name: Test CloudSOC

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: [3.9, '3.10', '3.11']
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: ${{ matrix.python-version }}
      
      - name: Install dependencies
        run: pip install -r requirements.txt
      
      - name: Syntax check
        run: python -m py_compile cloud_soc_env.py inference.py
      
      - name: Quick tests
        run: python test_cloudsoc.py --quick
      
      - name: Full unit tests
        run: python test_cloudsoc.py
      
      - name: Build Docker
        run: docker build -t cloudsoc:test .
```

---

## Performance Benchmarks (Reference)

| Task | Steps | Tools | Time | Memory |
|------|-------|-------|------|--------|
| Easy | 15 | 5 | 75ms | 45MB |
| Medium | 25 | 8 | 125ms | 65MB |
| Hard | 40 | 12 | 200ms | 95MB |

*Times are per-step execution time (excluding LLM latency)*

---

## Support & Debugging

### Enable Verbose Logging

```python
env = CloudSOCEnv(task='easy', seed=42, verbose=True)
obs, info = env.reset()

# Access internal state
print("Discovered flags:", env.state.discovered_flags)
print("Phase scores:", env.phase_scores)
print("Tool usage:", env.tool_usage)
print("Query costs:", env.query_costs)

# Export state for inspection
state_dict = env.state.to_dict()
import json
print(json.dumps(state_dict, indent=2))
```

### Parser Debugging

```python
from inference import parse_llm_response

# Test various response formats
responses = [
    '{"thought": "test", "tool": "aws.soc.get_alerts", "args": {}}',
    '```json\n{"thought": "test", "tool": "aws.soc.get_alerts", "args": {}}\n```',
    'I will check alerts. {"thought": "test", "tool": "aws.soc.get_alerts", "args": {}}',
]

for response in responses:
    parsed, error = parse_llm_response(response)
    print(f"{'✓' if parsed else '✗'} {error or 'OK'}")
```

---

## Next Steps

1. **Run quick tests**: `python test_cloudsoc.py --quick`
2. **Explore environment**: `python debug_cloudsoc.py --quick`
3. **Run unit tests**: `python test_cloudsoc.py --verbose`
4. **Test with LLM**: Set HF_TOKEN and run `python inference.py --task easy`
5. **Docker deployment**: `docker build -t cloudsoc:latest .`
6. **Submit to Hugging Face Spaces**

Good luck with the hackathon! 🚀
