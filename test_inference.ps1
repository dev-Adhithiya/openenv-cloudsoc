# Test inference with proper environment setup

# Set environment variables using PowerShell syntax
# Replace YOUR_HF_TOKEN_HERE with your actual token from https://huggingface.co/settings/tokens
$env:HF_TOKEN = "YOUR_HF_TOKEN_HERE"
$env:MODEL_NAME = "gpt-4o-mini"
$env:API_BASE_URL = "https://api.openai.com/v1"

Write-Host "===========================================" -ForegroundColor Green
Write-Host "Environment Variables Set" -ForegroundColor Green
Write-Host "===========================================" -ForegroundColor Green
Write-Host "HF_TOKEN: $($env:HF_TOKEN.Substring(0,10))..." 
Write-Host "MODEL_NAME: $env:MODEL_NAME"
Write-Host "API_BASE_URL: $env:API_BASE_URL"
Write-Host ""

# Run inference
Write-Host "Running inference test (easy task)..." -ForegroundColor Cyan
Write-Host "===========================================" -ForegroundColor Cyan
python inference.py --task easy --seed 42
