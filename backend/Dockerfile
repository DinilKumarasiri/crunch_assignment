# 1. Start from an official image that already has Python 3.12 installed.
#    "slim" = a smaller Debian Linux without extra tools → faster downloads.
FROM python:3.12-slim

# 2. Environment settings:
#    - don't write .pyc files (keeps the folder clean)
#    - print logs immediately (otherwise Python buffers them and you see nothing)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 3. All following commands run inside /app in the container.
WORKDIR /app

# 4. Copy ONLY requirements first, then install.
#    Docker caches each layer. If requirements.txt hasn't changed,
#    the slow pip install is skipped on rebuilds. (Important trick!)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy the rest of the code.
COPY . .

# 6. Document that the app listens on 8000.
EXPOSE 8000

# 7. Default command when the container starts.
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]