# PowerShell Environment Variable Fix

## Problem
You used the old DOS `set` command:
```powershell
set HF_TOKEN=hf_...  # WRONG - doesn't work in PowerShell
```

## Solution
Use PowerShell's `$env:` syntax:
```powershell
$env:HF_TOKEN = "REDACTED"
$env:MODEL_NAME = "gpt-4o-mini"
```

---

## Method 1: PowerShell Command (Session-Only)
Use this for immediate testing (variables expire when you close PowerShell):

```powershell
$env:HF_TOKEN = "REDACTED"
$env:MODEL_NAME = "gpt-4o-mini"
$env:API_BASE_URL = "https://api.openai.com/v1"

python inference.py --task easy --seed 42
```

✅ **This is what you should use for testing**

---

## Method 2: PowerShell Script (Recommended for Testing)
Create a `.ps1` file with environment variables + command:

```powershell
# File: run_inference.ps1
$env:HF_TOKEN = "REDACTED"
$env:MODEL_NAME = "gpt-4o-mini"

python inference.py --task easy --seed 42
```

Run it:
```powershell
powershell -ExecutionPolicy Bypass -File run_inference.ps1
```

A ready-to-use script is already created:
```powershell
powershell -ExecutionPolicy Bypass -File test_inference.ps1
```

---

## Method 3: Permanent (System-Wide)
If you want variables to persist across sessions:

```powershell
# Permanent for current user
[Environment]::SetEnvironmentVariable("HF_TOKEN", "REDACTED", "User")

# Then restart PowerShell or refresh:
$env:HF_TOKEN = [Environment]::GetEnvironmentVariable("HF_TOKEN", "User")
```

Or via GUI:
1. Windows Start → "Edit environment variables"
2. Click "New" under "User variables"
3. Variable name: `HF_TOKEN`
4. Variable value: `hf_...`
5. Click OK & restart PowerShell

---

## Quick Comparison

| Method | Duration | Use Case |
|--------|----------|----------|
| `$env:HF_TOKEN = "..."` | Session only | Quick testing |
| PowerShell script (`.ps1`) | Session only | Repeatable testing |
| `[Environment]::SetEnvironmentVariable()` | Permanent | Production |
| GUI Environment Variables | Permanent | Preferred for Windows |

---

## Test Commands

### Single Command (One-Liner)
```powershell
$env:HF_TOKEN="REDACTED"; $env:MODEL_NAME="gpt-4o-mini"; cd "F:\Meta Hackathon V2"; python inference.py --task easy --seed 42
```

### Using the Script
```powershell
cd "F:\Meta Hackathon V2"
powershell -ExecutionPolicy Bypass -File test_inference.ps1
```

### Verify Variables Are Set
```powershell
Write-Host "HF_TOKEN: $env:HF_TOKEN"
Write-Host "MODEL_NAME: $env:MODEL_NAME"
```

---

## Expected Output

When working correctly, you'll see:
```
[START] task=easy env=cloudsoc model=gpt-4o-mini
[STEP] step=1 action=aws.soc.get_alerts({}) reward=0.00 done=false error=null
[STEP] step=2 action=aws.cloudwatch.query_basic(...) reward=-0.01 done=false error=null
...
[END] success=false steps=15 rewards=0.00,-0.01,...
```

If you see:
```
ValueError: HF_TOKEN environment variable is required
```

→ Your environment variable is NOT set. Use Method 1 or 2 above.

---

## Tip: Create a Batch File

If you use Command Prompt (cmd.exe) instead of PowerShell:

**File: run_test.bat**
```batch
@echo off
set HF_TOKEN=REDACTED
set MODEL_NAME=gpt-4o-mini
set API_BASE_URL=https://api.openai.com/v1

cd F:\Meta Hackathon V2
python inference.py --task easy --seed 42
```

Run:
```batch
run_test.bat
```

---

## Summary

✅ **For PowerShell:** Use `$env:VARIABLE = "value"`  
✅ **For Command Prompt:** Use `set VARIABLE=value`  
✅ **Test Script:** Already created as `test_inference.ps1`  
✅ **Recommended:** Use `test_inference.ps1` for repeatable testing  

Your code is working perfectly! Just use the right environment variable syntax for your shell. 🚀
