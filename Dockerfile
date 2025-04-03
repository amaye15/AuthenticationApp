# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Set the working directory in the container
WORKDIR /code

# Copy the requirements file into the container
COPY ./requirements.txt /code/requirements.txt

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the application code (Backend API and Streamlit app)
COPY ./app /code/app
COPY ./streamlit_app.py /code/streamlit_app.py # Add streamlit app file

# Make port 7860 available (Streamlit default is 8501, but HF uses specified port)
EXPOSE 7860

# Command to run the Streamlit application
# Use --server.port to match EXPOSE and HF config
# Use --server.address to bind correctly inside container
CMD ["streamlit", "run", "streamlit_app.py", "--server.port=7860", "--server.address=0.0.0.0"]