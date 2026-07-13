FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir "fastapi>=0.110.0" "uvicorn[standard]>=0.29.0" "PyJWT>=2.8.0" "email-validator>=2.1.0"
COPY main.py index.html API.md ./
EXPOSE 8003
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8003/', timeout=3)"
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8003", "--no-server-header"]
