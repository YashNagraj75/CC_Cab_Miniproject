# 1. Use an official Python runtime as a parent image
FROM python:3.10-slim

# 2. Set the working directory in the container
WORKDIR /app

# 3. Copy the requirements file into the container at /app
COPY requirements.txt .

# 4. Install any needed packages specified in requirements.txt
# --no-cache-dir: Disables the cache to keep image size down
# --upgrade pip: Ensures pip is up-to-date
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 5. Copy the rest of the application code into the container at /app
COPY main.py .
COPY schema.py .
COPY data.db .

# 6. Make port 8000 available to the world outside this container
EXPOSE 8080

# 7. Define the command to run your app using uvicorn
#    --host 0.0.0.0 makes the server accessible from outside the container
#    main:app tells uvicorn where to find the FastAPI app instance
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
