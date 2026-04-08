# Model Selection Guide for CloudSOC Testing

## Quick Recommendation

**For testing: Start with `gpt-3.5-turbo` or local `Llama 2` via Ollama**

| Model | Cost | Speed | Quality | Setup |
|-------|------|-------|---------|-------|
| **gpt-3.5-turbo** ⭐ | $0.50/1M tokens | Fast | Good | 1 min |
| **gpt-4o-mini** | $0.15/1M tokens | Very Fast | Better | 1 min |
| **Llama 2 (Local)** | Free | Slow | Fair | 10 min |
| **Mistral (Local)** | Free | Medium | Good | 10 min |
| gpt-4-turbo | $10/1M tokens | Medium | Excellent | 1 min |

---

## Option 1: Cloud Models (Easiest) ⭐ **RECOMMENDED**

### Setup (1 minute)

1. Get API key from [platform.openai.com](https://platform.openai.com/api-keys)

2. Set environment variables:
```bash
# Windows PowerShell
$env:HF_TOKEN = "sk-..."  # Your OpenAI API key
$env:API_BASE_URL = "https://api.openai.com/v1"
$env:MODEL_NAME = "gpt-3.5-turbo"  # or gpt-4o-mini
```

3. Run test:
```bash
python inference.py --task easy --seed 42 --max_steps 10
```

### Cost Estimates (Easy Task, ~10-15 steps)
- **gpt-3.5-turbo**: $0.01-0.05 per run
- **gpt-4o-mini**: $0.003-0.01 per run
- **gpt-4-turbo**: $0.20-0.50 per run

### Why gpt-3.5-turbo?
✅ Cheap ($0.50 per 1M input tokens)  
✅ Fast (1-2 sec per action)  
✅ Good at JSON parsing  
✅ Reliable  
❌ Sometimes verbose/redundant

### Why gpt-4o-mini?
✅ Cheaper than 3.5 ($0.15 per 1M)  
✅ Better reasoning  
✅ Better JSON quality  
✅ Faster overall  
✅ **BEST for testing**

---

## Option 2: Local Models via Ollama (Free but Slow)

### Setup (10 minutes)

1. Install Ollama from [ollama.ai](https://ollama.ai)

2. Pull a model:
```bash
ollama pull mistral      # Fast, ~7B params (recommended)
ollama pull llama2       # Slower, ~7B params
ollama pull neural-chat  # Medium, ~7B params
```

3. Start Ollama server:
```bash
ollama serve  # Runs on http://localhost:11434
```

4. Set environment variables:
```bash
$env:HF_TOKEN = "dummy-token"  # Can be anything
$env:API_BASE_URL = "http://localhost:11434/v1"
$env:MODEL_NAME = "mistral"  # or llama2
```

5. Run test:
```bash
python inference.py --task easy --seed 42 --max_steps 5
```

### Pros & Cons
✅ FREE (no API costs)  
✅ Private (no data to OpenAI)  
✅ 100% offline  
❌ SLOW (10-30 sec per action)  
❌ Lower reasoning quality  
❌ RAM intensive (~8GB for 7B model)

### Local Model Recommendations
| Model | Size | Speed | Quality | RAM |
|-------|------|-------|---------|-----|
| **Mistral** | 7B | ⭐⭐⭐ | ⭐⭐ | 8GB |
| **Llama 2** | 7B | ⭐⭐ | ⭐⭐ | 8GB |
| **Neural Chat** | 7B | ⭐⭐⭐ | ⭐⭐ | 8GB |
| Phi 2 | 2.7B | ⭐⭐⭐⭐ | ⭐ | 4GB |

---

## Option 3: Hugging Face Inference API

### Setup (2 minutes)

1. Get Hugging Face token from [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)

2. Set environment:
```bash
$env:HF_TOKEN = "hf_XXX..."
$env:API_BASE_URL = "https://api-inference.huggingface.co/v1"
$env:MODEL_NAME = "meta-llama/Llama-2-7b-chat-hf"  # or another model
```

3. Run test:
```bash
python inference.py --task easy --seed 42
```

### Available Models
- `meta-llama/Llama-2-7b-chat-hf`
- `mistralai/Mistral-7B-Instruct-v0.1`
- `NousResearch/Nous-Hermes-2-Mixtral-8x7B-DPO`

### Pros & Cons
✅ Free tier available  
✅ No GPU needed  
✅ Wide model selection  
❌ Rate limited  
❌ Variable speed (depends on queue)  
❌ Less reliable than OpenAI

---

## Quick Start Decision Tree

```
Do you have an OpenAI API key?
├─ YES → Use gpt-4o-mini (cheapest, fastest, best)
└─ NO
   ├─ Do you want to pay for inference?
   │  ├─ YES → Get OpenAI key, use gpt-4o-mini
   │  └─ NO
   │     └─ Do you have 8GB+ RAM free?
   │        ├─ YES → Use Ollama + Mistral (free, offline)
   │        └─ NO → Use Hugging Face Inference API (free tier)
```

---

## Testing Strategy (Recommended)

### Phase 1: Validation (Free/Cheap)
```bash
# Test with gpt-4o-mini (cheapest, $0.003-0.01 per run)
python test_cloudsoc.py --quick                    # Validates env ✓
python inference.py --task easy --seed 42 --max_steps 5   # Quick test
```
**Cost:** ~$0.01  
**Time:** 2 min  

### Phase 2: Medium Testing ($0.05-0.20)
```bash
# Run all 3 difficulty levels
for task in easy medium hard:
  python inference.py --task $task --seed 42 --max_steps 50
```
**Cost:** ~$0.15  
**Time:** 30 min  

### Phase 3: Production (Scale Up)
```bash
# Deploy to Hugging Face Spaces with gpt-4o or gpt-4-turbo
# (if budget allows for better quality)
```

---

## Testing Commands by Model

### gpt-4o-mini (Cloud - RECOMMENDED)
```bash
$env:HF_TOKEN = "sk-..."
$env:MODEL_NAME = "gpt-4o-mini"
$env:API_BASE_URL = "https://api.openai.com/v1"

python inference.py --task easy --seed 42 --max_steps 10
```

### gpt-3.5-turbo (Cloud - Budget)
```bash
$env:HF_TOKEN = "sk-..."
$env:MODEL_NAME = "gpt-3.5-turbo"

python inference.py --task easy --seed 42
```

### Mistral (Local - Free)
```bash
# Terminal 1: Start Ollama
ollama serve

# Terminal 2: Run test
$env:HF_TOKEN = "dummy"
$env:API_BASE_URL = "http://localhost:11434/v1"
$env:MODEL_NAME = "mistral"

python inference.py --task easy --seed 42 --max_steps 5
```

---

## Expected Output (Each Model)

All should produce hackathon-compliant format:
```
[START] task=easy env=cloudsoc model=gpt-4o-mini
[STEP] step=1 action=aws.soc.get_alerts({}) reward=0.00 done=false error=null
[STEP] step=2 action=aws.cloudwatch.query_basic(...) reward=-0.01 done=false error=null
...
[END] success=true steps=N rewards=0.00,-0.01,...
```

---

## My Recommendation

1. **First time / Testing?** → **gpt-4o-mini** (cheapest, best quality)
2. **Budget conscious?** → **gpt-3.5-turbo** (still cheap, good)
3. **Want free?** → **Ollama + Mistral** (free, but slow)
4. **Production quality?** → **gpt-4-turbo** (expensive, best reasoning)

---

## Troubleshooting

### "API key invalid"
→ Check your API key is correct  
→ Make sure you're using the right env var name (HF_TOKEN, not OPENAI_API_KEY)

### "Model not found"
→ Check model name spelling  
→ Verify it's available on your provider

### "Connection refused"
→ For local: Make sure `ollama serve` is running  
→ For cloud: Check internet connection

### "Rate limited"
→ Wait a few seconds and retry  
→ Consider upgrading to paid tier  
→ Use local model instead

### Model gives bad JSON
→ Try `--temperature 0.2` (more deterministic)  
→ Switch to gpt-4o-mini (better JSON)  
→ Use simpler task (easy instead of hard)

---

## Cost Comparison (Easy Task, 15 steps)

| Model | Per Run | 100 Runs | Notes |
|-------|---------|----------|-------|
| gpt-4o-mini | $0.01 | $1.00 | Best value ⭐ |
| gpt-3.5-turbo | $0.03 | $3.00 | Good value |
| Mistral (local) | $0.00 | $0.00 | Free, slow |
| gpt-4-turbo | $0.30 | $30.00 | Overkill for dev |

---

**TL;DR: Start with gpt-4o-mini ($0.01 per test), or free Ollama locally if you have 8GB RAM.**
