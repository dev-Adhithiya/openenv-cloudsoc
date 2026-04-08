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
ENV API_BASE_URL="https://api.openai.com/v1"
ENV MODEL_NAME="gpt-4.1-mini"

# Run inference
CMD ["python", "inference.py", "--task", "easy"]
