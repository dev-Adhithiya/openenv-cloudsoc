# HOW TO TEST - Quick Start Guide

## 🚀 3-Step Testing

### 1️⃣ Quick Smoke Test (2 minutes)
```bash
python test_cloudsoc.py --quick
```
✓ Validates all 3 difficulty levels
✓ Tests basic tool execution
✓ Checks preconditions & traps
✓ Confirms everything works

### 2️⃣ Full Unit Tests (10 minutes)
```bash
python test_cloudsoc.py --verbose
```
✓ 20+ comprehensive tests
✓ Tests all 12 mechanics
✓ Covers 24 tools
✓ Full feature validation

### 3️⃣ Interactive Debugging (5-15 minutes)
```bash
python debug_cloudsoc.py --quick
```
✓ Explore cloud infrastructure
✓ View alerts and logs
✓ See discovered flags
✓ Execute sample actions
✓ Check scoring details

---

## 📋 Test Coverage

| Test Level | Time | Coverage | File |
|-----------|------|----------|------|
| Quick | 2m | Core mechanics | `test_cloudsoc.py --quick` |
| Full | 10m | All features | `test_cloudsoc.py --verbose` |
| Debug | 5-15m | Interactive | `debug_cloudsoc.py --quick` |
| Manual | varies | With LLM | `inference.py` |
| Docker | 5m | Deployment | `docker build .` |

---

## 🎯 What Gets Tested

### ✅ Mechanics (All 12)
1. Deceptive Environment → Mixed logs with noise
2. Partial Observability → Query costs tracked
3. Strict Preconditions → Snapshot/isolate dependencies
4. Adversarial Traps → Terminate = -1.0, game over
5. Gradient Rewards → +0.02 per flag
6. Memory Pressure → 6-turn sliding window
7. Tool Abstraction → Pydantic JSON schema
8. Rich Scoring → 4-phase breakdown
9. Deterministic Seeds → Reproducible states
10. CoT Prompting → thought/tool/args format
11. Multi-Task Campaign → Easy→Medium→Hard state transfer
12. Timeline Reconstruction → Jaccard + order scoring

### ✅ Tools (24 Available)
```
aws.cloudwatch.query_basic     aws.cloudwatch.query_deep
aws.ec2.describe               aws.ec2.isolate
aws.ec2.snapshot               aws.ec2.terminate
aws.iam.describe_role          aws.iam.detach_role
aws.iam.revoke_credentials     aws.iam.list_policies
aws.s3.get_bucket_policy       aws.s3.block_public_access
aws.s3.list_objects            aws.rds.rotate_credentials
aws.security_group.modify      aws.investigate
aws.soc.get_alerts             aws.soc.close_incident
aws.guardduty.get_findings     aws.cloudtrail.lookup_events
aws.config.get_compliance      aws.ssm.run_command
aws.lambda.list_functions      aws.sts.get_caller_identity
```

### ✅ Scenarios (3 Difficulty Levels)

| Task | Steps | Flags | Tools | Complexity |
|------|-------|-------|-------|-----------|
| Easy | 15 | 3 | 5+ | Straightforward S3 discovery |
| Medium | 25 | 4 | 8+ | Credential tracing & revocation |
| Hard | 40 | 7 | 12+ | Full ransomware IR |

---

## 📊 Example Test Output

```
=== Quick Smoke Tests ===

1. Testing environment initialization...
   ✓ easy: 15 steps, 3 flags
   ✓ medium: 25 steps, 4 flags
   ✓ hard: 40 steps, 7 flags

2. Testing tool execution...
   ✓ Tool executed: reward=0.00

3. Testing deterministic seeding...
   ✓ Same seed produces same state

4. Testing action preconditions...
   ✓ Precondition check works

5. Testing adversarial trap...
   ✓ Adversarial trap triggered (-1.0 penalty)

✅ All quick tests passed!
```

---

## 🔍 Manual Test Examples

### Test Preconditions
```bash
python -c "
from cloud_soc_env import CloudSOCEnv
import json

env = CloudSOCEnv(task='easy', seed=42)
env.reset()
instance = list(env.state.instances.keys())[0]

# Try isolate without snapshot (should fail)
action = json.dumps({
    'thought': 'Isolate',
    'tool': 'aws.ec2.isolate',
    'args': {'instance_id': instance}
})
obs, reward, term, trunc, info = env.step(action)
print(f'Error: {info[\"last_action_error\"]}')  # Should have PRECONDITION_FAILED
"
```

### Test Tool Execution
```bash
python -c "
from cloud_soc_env import CloudSOCEnv
import json

env = CloudSOCEnv(task='easy', seed=42)
env.reset()

# Execute 5 sample tools
for tool in ['aws.soc.get_alerts', 'aws.guardduty.get_findings', 
             'aws.cloudwatch.query_basic', 'aws.ec2.describe']:
    action = json.dumps({'thought': 'Test', 'tool': tool, 'args': {}})
    obs, reward, _, _, info = env.step(action)
    print(f'{tool}: reward={reward:.2f}')
"
```

### Test Reward Shaping
```bash
python -c "
from cloud_soc_env import CloudSOCEnv
import json

env = CloudSOCEnv(task='easy', seed=42)
env.reset()

# Query deep logs - should discover flags and get reward
action = json.dumps({
    'thought': 'Deep query',
    'tool': 'aws.cloudwatch.query_deep',
    'args': {'log_group': '/aws/ec2'}
})
obs, reward, _, _, info = env.step(action)
print(f'Reward: {reward:.2f} (includes -0.05 cost + flag discovery)')
print(f'Flags discovered: {len(env.state.discovered_flags)}')
"
```

---

## 🐳 Docker Testing

```bash
# Build
docker build -t cloudsoc:test .

# Run with environment variables
docker run --rm \
  -e HF_TOKEN="test_token" \
  -e API_BASE_URL="https://api.openai.com/v1" \
  -e MODEL_NAME="gpt-4.1-mini" \
  cloudsoc:test

# Check resource usage
docker stats cloudsoc  # Should be < 2GB RAM
```

---

## ⚡ Performance Benchmarks

```
Environment Init:  < 100ms
Per Step (no LLM): < 3ms
Per Step (with LLM): 0.5-3s (depends on LLM latency)
Memory Usage:      < 2GB for hard task
```

---

## ✨ Files Overview

| File | Size | Purpose |
|------|------|---------|
| `cloud_soc_env.py` | 65KB | Core Gymnasium environment |
| `inference.py` | 18KB | LLM evaluation loop |
| `test_cloudsoc.py` | 18KB | Unit test suite |
| `debug_cloudsoc.py` | 13KB | Interactive debugger |
| `openenv.yaml` | 11KB | Benchmark specification |
| `TESTING.md` | 10KB | Detailed testing guide |
| `DEPLOYMENT.md` | 10KB | Deployment checklist |
| `README.md` | 3KB | Project overview |

---

## 🎓 What Each Test Does

### Quick Smoke Test
```python
python test_cloudsoc.py --quick
```
- Loads all 3 difficulty levels ✓
- Executes sample tool calls ✓
- Checks precondition enforcement ✓
- Tests adversarial trap triggering ✓
- Verifies deterministic seeding ✓

### Full Unit Test Suite
```python
python test_cloudsoc.py --verbose
```
- 20+ individual test methods
- Tests all major features
- Covers error handling
- Validates all tools
- Tests multi-task campaigns

### Interactive Debug
```python
python debug_cloudsoc.py --quick
```
- Shows initial cloud state
- Displays all alerts and logs
- Executes sample action sequence
- Tracks progress and flags
- Shows scoring breakdown
- Previews system prompt

---

## 🚨 Common Issues & Fixes

| Issue | Fix |
|-------|-----|
| `ModuleNotFoundError: gymnasium` | `pip install -r requirements.txt` |
| No test output | Make sure you're in the project directory |
| "No compromised instance" error | Try different seed: `--seed 42` |
| Parser fails on LLM response | Check verbose output with `--verbose` |
| Docker out of memory | Use `--task easy` instead of hard |

---

## 📈 Scoring Verification

After running tests, you should see:

✅ **Easy Task**
- 3 required flags discoverable
- Completion in < 15 steps typical
- Timeline accuracy scoring working

✅ **Medium Task**
- 4 required flags 
- Requires credential revocation
- State inheritance from Easy task

✅ **Hard Task**
- 7 required flags
- Full incident response required
- Forensic evidence preservation critical

---

## 🏁 Quick Verification Checklist

Run these in order:

```bash
# 1. Syntax check (instant)
python -m py_compile cloud_soc_env.py inference.py

# 2. Quick tests (2 minutes)
python test_cloudsoc.py --quick

# 3. Interactive exploration (5 minutes)
python debug_cloudsoc.py --quick

# 4. Full tests (10 minutes)
python test_cloudsoc.py --verbose

# 5. Docker build (5 minutes)
docker build -t cloudsoc:test .
```

**Total time: ~25 minutes for complete validation** ✅

---

## 🎉 Success Criteria

- [ ] All quick tests pass ✓
- [ ] All unit tests pass ✓
- [ ] Interactive debug shows proper cloud state ✓
- [ ] Tools execute with correct rewards ✓
- [ ] Preconditions enforced ✓
- [ ] Adversarial trap triggers (-1.0) ✓
- [ ] Timeline grading works ✓
- [ ] Docker builds successfully ✓
- [ ] Memory usage < 2GB ✓
- [ ] All 3 difficulty levels load ✓

**If all pass → Ready for hackathon submission! 🚀**

---

## Need Help?

1. **See what's happening**: Run with `--verbose` flag
2. **Explore environment**: Use `debug_cloudsoc.py`
3. **Check specific test**: Run individual test class
4. **Review docs**: See `TESTING.md` and `DEPLOYMENT.md`

Good luck! 🏆
