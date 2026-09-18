FROM python:3.14-slim

ARG BUILD_HTTP_PROXY=
ARG BUILD_HTTPS_PROXY=
ARG BUILD_NO_PROXY=localhost,127.0.0.1,host.containers.internal

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN python -m pip install --no-cache-dir uv

COPY pyproject.toml ./
RUN uv pip install --system --no-cache .

COPY . .

EXPOSE 8501

CMD ["streamlit", "run", "main.py", "--server.address=0.0.0.0", "--server.port=8501"]
