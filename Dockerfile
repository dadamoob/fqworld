FROM python:3.11-slim

# FFmpeg pour le montage vidéo, streamlink installé via pip (requirements.txt)
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Par défaut : l'UI. Le service "brain" du docker-compose surcharge cette commande.
EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
