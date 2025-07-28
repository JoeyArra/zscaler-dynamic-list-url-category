# Dockerfile

# Use an official, lightweight Python image
FROM python:3.9-slim

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file first (this improves build caching)
COPY requirements.txt .

# Install the dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy your script into the container's working directory
COPY multi-url-category-sync.py .

# This command isn't strictly necessary for a cron-triggered script,
# but it's good practice to have a default command.
CMD [ "python3", "./multi-url-category-sync.py" ]