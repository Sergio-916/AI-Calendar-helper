# Use official lightweight Python image
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Install uv package manager
RUN pip install --no-cache-dir uv

# Copy dependency files first (for caching optimization)
COPY pyproject.toml .
COPY uv.lock .

# Install dependencies using uv (explicitly specifying the lock file)
RUN uv pip install --system --no-cache -r uv.lock

# Copy the rest of the project files
COPY . .

# Set environment variables (optional)
ENV PYTHONUNBUFFERED=1

# Command to run the bot
CMD ["python", "src/bot.py"]
