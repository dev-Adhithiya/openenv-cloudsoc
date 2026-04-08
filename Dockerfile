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

COPY dummy_server.py .

# Environment variables (defaults)
# Using HF's new router.huggingface.co endpoint
ENV API_BASE_URL="https://router.huggingface.co/v1"
ENV MODEL_NAME="Qwen/Qwen2.5-Coder-32B-Instruct"
ENV HF_TOKEN=""

# Run a dummy HTTP server to keep the Hugging Face Space in the "Running" state
# The evaluation system will exec into this container to run inference.py
CMD ["python", "dummy_server.py"]
