# filepath: /Users/lontray/Documents/repos/DutchPal/Dockerfile
FROM python:3.10-slim

# Set the working directory
WORKDIR /app

# Copy the requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .

# Expose the port FastAPI will run on
EXPOSE 40001

# Command to run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "40001"]