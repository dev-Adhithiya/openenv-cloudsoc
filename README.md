---
title: OpenEnv-CloudSOC
emoji: 🔒
colorFrom: blue
colorTo: indigo
sdk: docker
app_file: inference.py
pinned: false
---

# OpenEnv-CloudSOC Benchmark

A production-ready benchmark environment for evaluating LLM agents on cloud security incident response tasks.

## Architecture

**Zero-DB Design**: Entire cloud state managed via in-memory Python dictionaries and Pydantic models. No external databases required.

**Hardware Target**: 2 vCPU / 8 GB RAM Docker container

## Features (12+ Core Mechanics)

| # | Mechanic | Description |
|---|----------|-------------|
| 1 | Deceptive Environment | Logs contain noise, red herrings, and real attack indicators |
| 2 | Partial Observability | Query costs: basic=-0.01, deep=-0.05 |
| 3 | Strict Preconditions | Must snapshot before isolate, detach before rotate |
| 4 | Adversarial Traps | Terminating compromised instances destroys evidence (-1.0) |
| 5 | Gradient Rewards | +0.02 per new flag discovered |
| 6 | Memory Pressure | Sliding context window (last 6 turns) |
| 7 | Tool Abstraction | Strict JSON schema with Pydantic validation |
| 8 | Rich Scoring | Breakdown by IR phase (investigation/containment/eradication/recovery) |
| 9 | Deterministic Seeds | 100% reproducible benchmarks |
| 10 | CoT Prompting | Required thought/tool/args format with dynamic hints |
| 11 | Multi-Task Campaign | Easy→Medium→Hard with shared state |
| 12 | Timeline Reconstruction | Jaccard similarity + order preservation scoring |

### Additional Enhancements
- **24 Tools**: Expanded tool set including aws.config, aws.ssm, aws.lambda, aws.sts
- **MITRE ATT&CK Mapping**: Scenarios tagged with technique IDs
- **Adaptive Temperature**: Retry logic with increasing temperature for diversity
- **Robust JSON Parsing**: Multi-strategy parser with recovery for malformed responses
- **State Serialization**: Full state export for debugging and checkpointing
- **Progress Hints**: Dynamic hints based on agent progress

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### Single Task
```bash
python inference.py --task easy --seed 42
```

### Full Campaign
```bash
python inference.py --task campaign --seed 42
```

### Verbose Mode (for debugging)
```bash
python inference.py --task easy --verbose
```

### Environment Variables
```bash
export API_BASE_URL="https://api.openai.com/v1"
export MODEL_NAME="gpt-4.1-mini"
export HF_TOKEN="your_token_here"
```

## Files

| File | Size | Description |
|------|------|-------------|
| `cloud_soc_env.py` | ~65KB | Gymnasium environment with state engine and grader |
| `inference.py` | ~18KB | LLM evaluation loop with hackathon-compliant output |
| `openenv.yaml` | ~11KB | Benchmark metadata specification |
| `requirements.txt` | - | Dependencies (gymnasium, pydantic, openai) |
| `Dockerfile` | - | Docker build for 2 vCPU/8GB constraint |

## Scenarios

### Easy: Leaky S3 Bucket Discovery
- **Steps**: 15 max
- **Flags**: s3_public_identified, credentials_found, public_access_blocked
- **MITRE**: T1530 (Data from Cloud Storage Object)

### Medium: Credential Compromise Response
- **Steps**: 25 max
- **Flags**: leaked_creds_identified, compromised_role_found, role_detached, credentials_rotated
- **MITRE**: T1078, T1552 (Valid Accounts, Credentials in Files)

### Hard: Full Incident Response - Ransomware
- **Steps**: 40 max
- **Flags**: ransomware_detected, backdoor_identified, forensic_snapshot_taken, instance_isolated, backdoor_removed, all_creds_rotated, systems_verified
- **MITRE**: T1486, T1098, T1078 (Data Encrypted, Account Manipulation)

## Output Format

```
[START] task=easy env=cloudsoc model=gpt-4.1-mini
[STEP] step=1 action=aws.soc.get_alerts({}) reward=0.00 done=false error=null
[STEP] step=2 action=aws.s3.get_bucket_policy({"bucket_name":"company-backup-2024"}) reward=0.02 done=false error=null
...
[END] success=true steps=8 rewards=0.00,0.02,0.02,0.10,0.05,0.10,0.05,0.25
```

## Scoring

Final score is a weighted average across IR phases:

```python
score = (
    investigation * phase_weights["investigation"] +
    containment * phase_weights["containment"] +
    eradication * phase_weights["eradication"] +
    recovery * phase_weights["recovery"]
)
```

Timeline accuracy uses Jaccard similarity with order preservation bonus.

## License

MIT
