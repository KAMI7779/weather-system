from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    create_time = db.Column(db.DateTime, default=datetime.utcnow)
    role = db.Column(db.String(20), default='user')  # user或admin

class Weather(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    city = db.Column(db.String(100), nullable=False, index=True)
    temperature = db.Column(db.Float, nullable=False)
    humidity = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(200), nullable=True)
    wind_speed = db.Column(db.String(50), nullable=True)
    wind_dir = db.Column(db.String(50), nullable=True)
    visibility = db.Column(db.String(50), nullable=True)
    pressure = db.Column(db.String(50), nullable=True)
    feels_like = db.Column(db.Float, nullable=True)
    aqi = db.Column(db.Integer, nullable=True)  # 空气质量指数
    pm25 = db.Column(db.Float, nullable=True)  # PM2.5
    pm10 = db.Column(db.Float, nullable=True)  # PM10
    o3 = db.Column(db.Float, nullable=True)  # 臭氧
    no2 = db.Column(db.Float, nullable=True)  # 二氧化氮
    so2 = db.Column(db.Float, nullable=True)  # 二氧化硫
    co = db.Column(db.Float, nullable=True)  # 一氧化碳
    date = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class City(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    is_default = db.Column(db.Boolean, default=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref=db.backref('cities', lazy='dynamic'))

class Warning(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    city = db.Column(db.String(100), nullable=False, index=True)
    warning_type = db.Column(db.String(100), nullable=False)  # 温度异常或湿度异常
    message = db.Column(db.String(200), nullable=False)
    severity = db.Column(db.String(50), nullable=False)  # 低、中、高
    date = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    is_read = db.Column(db.Boolean, default=False, index=True)

