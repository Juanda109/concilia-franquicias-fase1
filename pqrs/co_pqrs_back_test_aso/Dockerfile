FROM python:3.11-slim

# Evita que Python genere archivos .pyc y que el log se quede en el buffer
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_DIR=/app

WORKDIR ${APP_DIR}

# 1. Instalamos dependencias del sistema mínimas (solo si son necesarias)
# Si no necesitas 'make', no lo instales.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \ 
    && rm -rf /var/lib/apt/lists/*

# 2. Gestión inteligente de dependencias
# Copiamos primero solo el archivo de requerimientos para aprovechar la caché de Docker
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. Usuario no root por seguridad
RUN useradd -m appuser
USER appuser

# 4. Copiamos el resto del código
COPY . .

CMD ["python", "main.py"]