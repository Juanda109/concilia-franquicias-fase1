FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies from project metadata
COPY pyproject.toml README.md ./
COPY src/ src/
RUN pip install --no-cache-dir .

# Copy application code
COPY main.py .

# Create volume mount point
RUN mkdir -p /mnt/ada_data

# Run the application
CMD ["python", "main.py"]
