import os
from app.models import db, Weather
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_PATH = os.path.join(BASE_DIR, "app", "static")

def load_weather_data():
    # 从数据库中获取最近7天的天气数据
    seven_days_ago = datetime.now() - timedelta(days=7)
    weather_records = Weather.query.filter(Weather.date >= seven_days_ago).order_by(Weather.date).all()
    return weather_records

def basic_stats():
    records = load_weather_data()
    if not records:
        return {
            "max_temp": 0,
            "min_temp": 0,
            "avg_temp": 0,
            "avg_humidity": 0
        }
    
    temperatures = [record.temperature for record in records]
    humidities = [record.humidity for record in records]
    
    max_temp = max(temperatures)
    min_temp = min(temperatures)
    avg_temp = round(sum(temperatures) / len(temperatures), 2)
    avg_humidity = round(sum(humidities) / len(humidities), 1)
    
    return {
        "max_temp": max_temp,
        "min_temp": min_temp,
        "avg_temp": avg_temp,
        "avg_humidity": avg_humidity
    }

def temp_trend():
    # 简化处理，创建一个简单的文本文件表示趋势
    records = load_weather_data()
    with open(os.path.join(STATIC_PATH, "temp.txt"), "w", encoding="utf-8") as f:
        f.write("温度趋势数据\n")
        for record in records:
            f.write(f"{record.date}: {record.temperature}°C\n")

def humidity_trend():
    # 简化处理，创建一个简单的文本文件表示趋势
    records = load_weather_data()
    with open(os.path.join(STATIC_PATH, "humidity.txt"), "w", encoding="utf-8") as f:
        f.write("湿度趋势数据\n")
        for record in records:
            f.write(f"{record.date}: {record.humidity}%\n")

def combined_trend():
    # 简化处理，创建一个简单的文本文件表示趋势
    records = load_weather_data()
    with open(os.path.join(STATIC_PATH, "combined.txt"), "w", encoding="utf-8") as f:
        f.write("温度和湿度趋势数据\n")
        for record in records:
            f.write(f"{record.date}: 温度={record.temperature}°C, 湿度={record.humidity}%\n")

