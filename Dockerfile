FROM python:3.11-slim

# Install system libraries needed by OpenCV and InsightFace
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir onnxruntime insightface "setuptools<70.0.0"

# Pre-download InsightFace buffalo_l models during build so container starts instantly
RUN python -c "import insightface; insightface.app.FaceAnalysis(name='buffalo_l')" || true

# Copy project files
COPY . .

# Expose port
EXPOSE 8000

# Run FastAPI server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
