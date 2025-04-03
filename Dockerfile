# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Set the working directory in the container
WORKDIR /code

# Copy the requirements file into the container
COPY ./requirements.txt /code/requirements.txt

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
COPY ./app /code/app
# COPY ./.env /code/.env # Copy .env file - for Hugging Face, use Secrets instead

# Make port 7860 available to the world outside this container (Gradio default)
EXPOSE 7860

# Explicitly create the /data directory where the SQLite DB will live
# Running as root by default, so permissions should be okay initially
# RUN mkdir -p /data

# Command to run the application using uvicorn
# It will run the FastAPI app instance created in app/main.py
# Host 0.0.0.0 is important to accept connections from outside the container
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]