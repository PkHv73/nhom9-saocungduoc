FROM python:3.12-slim

WORKDIR /app

# Cài dependencies trước (tận dụng Docker layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY agent.py main.py ./

EXPOSE 8080

# Biến môi trường mặc định (override khi deploy trên GreenNode)
ENV LLM_MODEL=minimax/minimax-m2.5 \
    MAX_TOKENS=1500 \
    LOG_LEVEL=INFO \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

CMD ["python", "main.py"]
