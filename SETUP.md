# Setup Guide for OpenEnv-CloudSOC

## For Local Testing

### Prerequisites
- Python 3.11+
- Together AI API key (free, get one at https://www.together.ai - no credit card required)

### Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export API_BASE_URL="https://api.together.xyz/v1"
export MODEL_NAME="meta-llama/Qwen2.5-3B-Instruct"
export HF_TOKEN="your_together_ai_key"

# Run inference
python inference.py --task easy --seed 42
```

## For Hugging Face Space Deployment

### Prerequisites
- GitHub account with this repository forked
- Hugging Face account
- Hugging Face API token (create at https://huggingface.co/settings/tokens)

### Deployment Steps

1. **Create a New Space**
   - Go to https://huggingface.co/new-space
   - Space name: `openenv-cloudsoc` (or your preferred name)
   - SDK: Select **Docker**
   - Repository: Paste URL of your GitHub fork
   - Click "Create space"

2. **Add HF_TOKEN Secret (Together AI API Key)**
   - Space will start building automatically
   - Navigate to **Settings** → **Repository** → **Secrets**
   - Click "Add secret"
   - Key: `HF_TOKEN`
   - Value: Paste your Together AI API key from https://www.together.ai/settings/api-keys
   - Click "Add secret"

3. **Restart the Space**
   - After adding the secret, the Space should rebuild
   - Monitor the build status in the **Logs** tab
   - Once **Status: Running**, the benchmark is live

### Verification

Once deployed with Together AI token, you should see output like:
```
[START] task=easy env=cloudsoc model=meta-llama/Qwen2.5-3B-Instruct
[STEP] step=1 action=aws.soc.get_alerts({}) reward=0.02 done=false error=null
...
[END] success=true steps=8 rewards=0.02,0.02,0.10,0.05,0.10,0.05,0.25,0.10
```

## For Hackathon Submission

When submitting to the OpenEnv RL Challenge:

1. Ensure your HF Space is in **Running** state
2. The evaluator will:
   - Trigger inference via the Space API
   - Provide HF_TOKEN as an environment variable
   - Collect [START]/[STEP]/[END] output
3. Your submission must:
   - Use OpenAI Client (✅ we do)
   - Have `inference.py` in root (✅ we do)
   - Support required env vars (✅ we do)
   - Output hackathon format (✅ we do)

## Resource Constraints

Your solution will run in:
- **2 vCPU**
- **8 GB RAM**
- **15-40 second timeout per task**

Current optimizations:
- ✅ Qwen2.5-3B-Instruct (lightweight 3B model)
- ✅ MAX_TOKENS: 512 (smaller outputs)
- ✅ MAX_CONTEXT_TURNS: 4 (reduced context window)
- ✅ Timeout: 45 seconds

## Troubleshooting

### Error: "HF_TOKEN environment variable is required"

**Solution**: Add `HF_TOKEN` as a Space Secret
1. Go to Space Settings → Repository → Secrets
2. Add `HF_TOKEN` with your token value
3. Restart the Space

### Error: "Connection timeout"

**Cause**: Qwen2.5-3B model cold start or API latency
**Solution**: The timeout is set to 45 seconds. Retries use exponential backoff.

### Space stuck building

**Cause**: Multiple active Spaces consuming resources
**Solution**: Stop unnecessary Spaces at https://huggingface.co/settings/spaces

## Getting Your API Token (Together AI)

1. Go to https://www.together.ai
2. Sign up (free account, no credit card required)
3. Navigate to https://www.together.ai/settings/api-keys
4. Copy your API key
5. Add to Space Secrets as `HF_TOKEN` (variable name remains HF_TOKEN for compatibility)

## Support

For issues:
1. Check Space Logs tab
2. Verify HF_TOKEN is set and valid
3. Ensure Space is in **Running** state
4. Check this README for environment variable documentation
