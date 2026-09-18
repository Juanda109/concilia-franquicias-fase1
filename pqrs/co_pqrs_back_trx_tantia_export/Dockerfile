FROM python:3.11-slim

WORKDIR /app

# Dependencias desde metadata del proyecto
COPY pyproject.toml README.md ./
COPY main.py ./
RUN pip install --no-cache-dir .

# Punto de montaje del PVC de Tantia
RUN mkdir -p /mnt/ada_data

CMD ["python", "main.py"]
