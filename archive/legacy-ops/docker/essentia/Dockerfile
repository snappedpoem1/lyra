FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for essentia
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libfftw3-double3 \
        libsamplerate0 \
        libyaml-0-2 \
        libavcodec61 \
        libavformat61 \
        libavutil59 \
        libswresample5 \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY service.py .

EXPOSE 7701

CMD ["uvicorn", "service:app", "--host", "0.0.0.0", "--port", "7701"]
