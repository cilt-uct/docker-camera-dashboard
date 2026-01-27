FROM python:3.12-slim

WORKDIR /app

# Set Timezone for Docker Container
RUN apt-get update && apt-get install -y tzdata
ENV TZ=Africa/Johannesburg
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Install dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy application code
COPY . .

CMD ["python", "main.py"]