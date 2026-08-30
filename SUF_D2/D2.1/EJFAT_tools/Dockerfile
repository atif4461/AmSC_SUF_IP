FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends g++ && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY cpp ./cpp

RUN mkdir -p /app/bin && g++ -O3 -std=c++17 -pthread /app/cpp/lb_dataplane.cpp -o /app/bin/lb_dataplane

ENV PYTHONPATH=/app/src

EXPOSE 18080/tcp 18020/udp 19020/udp

CMD ["python", "-m", "ejfat_emulator.main"]
