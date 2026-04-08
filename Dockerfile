FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements first for caching
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY cloud_soc_env.py .
COPY inference.py .
COPY openenv.yaml .

# Environment variables (defaults)
# Using HF's new router.huggingface.co endpoint
ENV API_BASE_URL="https://router.huggingface.co/v1"
ENV MODEL_NAME="Qwen/Qwen2.5-3B-Instruct"
ENV HF_TOKEN=""

# Run inference - default task is 'easy'
CMD ["python", "inference.py", "--task", "easy"]
