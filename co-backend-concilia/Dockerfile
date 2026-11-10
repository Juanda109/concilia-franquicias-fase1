FROM python:3.12-slim
WORKDIR /app
ENV PYTHONPATH=/app/src
# setuptools viene con la imagen base, no con requirements.txt - sin este
# upgrade queda una versión vieja con CVE conocido aunque el requirements
# esté limpio.
RUN pip install --no-cache-dir --upgrade pip setuptools
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src ./src
CMD ["uvicorn","app.api.main:app","--host","0.0.0.0","--port","8080"]
