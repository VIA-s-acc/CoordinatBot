# Используем официальный Python 3.13.5 образ
FROM python:3.13.5-slim

WORKDIR /app

# Копируем requirements и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь проект
COPY . .

# Создаем точку монтирования volume для постоянных данных
VOLUME ["/app_data"]

# Используем параметр по умолчанию для деплоя
CMD ["python", "-m", "src.main", "-dep"]
