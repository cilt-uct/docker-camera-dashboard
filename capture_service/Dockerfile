FROM python:3.12-slim

WORKDIR /app

# Set Timezone for Docker Container
RUN apt-get update && apt-get install -y tzdata
ENV TZ=Africa/Johannesburg
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Install dependencies
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy scripts
COPY . .

# Set permissions for scripts
RUN chmod +x ./scripts/capture_images.sh
RUN chmod +x ./scripts/generate_timelapse.sh

CMD ["python", "scheduler.py"]