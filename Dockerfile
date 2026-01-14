# Используем официальный Python 3.13.5 образ
FROM python:3.13.5-slim

WORKDIR /app

# Создаем директорию для данных
RUN mkdir -p /data

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Используем параметр по умолчанию для деплоя
CMD ["python", "-m", "src.main", "-dep"]
