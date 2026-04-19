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

# 气象站表
class WeatherStation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    station_id = db.Column(db.String(100), unique=True, nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    altitude = db.Column(db.Float, nullable=True)
    station_type = db.Column(db.String(100), nullable=False)  # 自动站、手动站等
    status = db.Column(db.String(50), default='active')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# 气象站观测数据表
class StationObservation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    station_id = db.Column(db.String(100), db.ForeignKey('weather_station.station_id'), nullable=False, index=True)
    timestamp = db.Column(db.DateTime, nullable=False, index=True)
    temperature = db.Column(db.Float, nullable=True)  # 温度
    humidity = db.Column(db.Float, nullable=True)  # 湿度
    pressure = db.Column(db.Float, nullable=True)  # 气压
    wind_speed = db.Column(db.Float, nullable=True)  # 风速
    wind_direction = db.Column(db.Float, nullable=True)  # 风向
    precipitation = db.Column(db.Float, nullable=True)  # 降水量
    visibility = db.Column(db.Float, nullable=True)  # 能见度
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    station = db.relationship('WeatherStation', backref=db.backref('observations', lazy='dynamic'))

# 卫星云图表
class SatelliteImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    image_type = db.Column(db.String(100), nullable=False)  # 红外、可见光等
    timestamp = db.Column(db.DateTime, nullable=False, index=True)
    image_url = db.Column(db.String(500), nullable=False)
    resolution = db.Column(db.String(50), nullable=True)
    description = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# 雷达回波图表
class RadarEcho(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    radar_id = db.Column(db.String(100), nullable=False, index=True)
    timestamp = db.Column(db.DateTime, nullable=False, index=True)
    image_url = db.Column(db.String(500), nullable=False)
    max_echo = db.Column(db.Float, nullable=True)  # 最大回波强度
    coverage_area = db.Column(db.String(200), nullable=True)
    description = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# 数值预报模式数据表
class NumericalForecast(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    model_name = db.Column(db.String(100), nullable=False, index=True)  # ECMWF、GFS等
    run_time = db.Column(db.DateTime, nullable=False, index=True)  # 模式运行时间
    forecast_time = db.Column(db.DateTime, nullable=False, index=True)  # 预报时间
    variable = db.Column(db.String(100), nullable=False)  # 温度、降水等变量
    value = db.Column(db.Float, nullable=False)  # 变量值
    level = db.Column(db.String(50), nullable=True)  # 高度层
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# 数据源配置表
class DataSource(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, unique=True)
    source_type = db.Column(db.String(100), nullable=False)  # 地面站、卫星、数值预报等
    url = db.Column(db.String(500), nullable=True)
    api_key = db.Column(db.String(500), nullable=True)
    status = db.Column(db.String(50), default='active')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# 数据接入日志表
class DataAccessLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data_source = db.Column(db.String(200), nullable=False)
    data_type = db.Column(db.String(100), nullable=False)
    record_count = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(50), nullable=False)
    message = db.Column(db.String(500), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)

# 数据质量控制表
class DataQuality(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data_id = db.Column(db.Integer, nullable=False)  # 关联的原始数据ID
    data_type = db.Column(db.String(100), nullable=False)  # 数据类型
    check_time = db.Column(db.DateTime, default=datetime.utcnow)
    is_valid = db.Column(db.Boolean, default=True)  # 是否有效
    error_type = db.Column(db.String(100), nullable=True)  # 错误类型
    error_message = db.Column(db.String(500), nullable=True)  # 错误信息
    corrected_value = db.Column(db.Float, nullable=True)  # 修正后的值

# 数据预处理记录表
class DataPreprocessing(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data_id = db.Column(db.Integer, nullable=False)  # 关联的原始数据ID
    data_type = db.Column(db.String(100), nullable=False)  # 数据类型
    preprocess_time = db.Column(db.DateTime, default=datetime.utcnow)
    preprocess_type = db.Column(db.String(100), nullable=False)  # 预处理类型
    original_value = db.Column(db.Float, nullable=True)  # 原始值
    processed_value = db.Column(db.Float, nullable=True)  # 处理后的值
    parameters = db.Column(db.Text, nullable=True)  # 预处理参数

# 山洪风险指数表
class FlashFloodRisk(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    location = db.Column(db.String(200), nullable=False, index=True)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    risk_level = db.Column(db.Integer, nullable=False)  # 1-5级
    rainfall_forecast = db.Column(db.Float, nullable=False)  # 预测降雨量
    soil_moisture = db.Column(db.Float, nullable=True)  # 土壤湿度
    terrain_factor = db.Column(db.Float, nullable=True)  # 地形因子
    timestamp = db.Column(db.DateTime, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# 极端天气事件表
class ExtremeWeatherEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_type = db.Column(db.String(100), nullable=False, index=True)  # 暴雨、大风等
    location = db.Column(db.String(200), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    intensity = db.Column(db.Float, nullable=False)  # 事件强度
    description = db.Column(db.String(500), nullable=True)
    recurrence_period = db.Column(db.Float, nullable=True)  # 重现期（年）
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# 用户行为分析表
class UserBehavior(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    query_type = db.Column(db.String(100), nullable=False)  # 城市查询、参数查询等
    query_content = db.Column(db.String(500), nullable=False)  # 查询内容
    timestamp = db.Column(db.DateTime, nullable=False, index=True)
    ip_address = db.Column(db.String(100), nullable=True)
    user_agent = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('behaviors', lazy='dynamic'))

# 算法模型参数表
class AlgorithmModel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    model_name = db.Column(db.String(200), nullable=False, unique=True)
    version = db.Column(db.String(50), nullable=False)
    parameters = db.Column(db.Text, nullable=False)  # JSON格式存储参数
    accuracy = db.Column(db.Float, nullable=True)  # 模型准确率
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# 预警规则表
class WarningRule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rule_name = db.Column(db.String(200), nullable=False, unique=True)
    parameter = db.Column(db.String(100), nullable=False)  # 预警参数
    operator = db.Column(db.String(10), nullable=False)  # 运算符
    threshold = db.Column(db.Float, nullable=False)  # 阈值
    level = db.Column(db.String(50), nullable=False)  # 预警级别
    message = db.Column(db.String(500), nullable=False)  # 预警消息
    status = db.Column(db.String(50), default='active')  # 状态
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# 预警记录表
class WarningRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rule_id = db.Column(db.Integer, db.ForeignKey('warning_rule.id'), nullable=False)
    station_id = db.Column(db.String(100), nullable=True)
    location = db.Column(db.String(200), nullable=False)
    value = db.Column(db.Float, nullable=False)  # 实际值
    threshold = db.Column(db.Float, nullable=False)  # 阈值
    level = db.Column(db.String(50), nullable=False)  # 预警级别
    message = db.Column(db.String(500), nullable=False)  # 预警消息
    status = db.Column(db.String(50), default='active')  # 状态
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# 推送记录表
class PushRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    warning_id = db.Column(db.Integer, db.ForeignKey('warning_record.id'), nullable=False)
    push_type = db.Column(db.String(50), nullable=False)  # 推送类型
    recipient = db.Column(db.String(200), nullable=False)  # 接收人
    message = db.Column(db.String(500), nullable=False)  # 推送消息
    status = db.Column(db.String(50), nullable=False)  # 推送状态
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

