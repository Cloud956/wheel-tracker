# Use Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements and install using the file
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the code
COPY . .

# Run the API
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]