FROM python:3.11-slim

# Install system libraries needed by OpenCV and InsightFace
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies using pre-compiled wheels (takes < 1 min, uses minimal RAM)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download InsightFace buffalo_l models during build so container starts instantly
RUN python -c "import insightface; insightface.app.FaceAnalysis(name='buffalo_l')" || true

# Copy project files
COPY . .

# Expose port (Render defaults to 10000)
EXPOSE 10000

# Run FastAPI server with dynamic port support
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
