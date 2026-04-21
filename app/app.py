from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from app.models import db, User, Weather, City, Warning, WeatherStation, StationObservation, SatelliteImage, RadarEcho, NumericalForecast, DataSource, DataAccessLog, DataQuality, DataPreprocessing, WarningRule, WarningRecord, PushRecord
from app.analysis import basic_stats
import requests
import json
import random
import math
import numpy as np
from datetime import datetime, timedelta

app = Flask(__name__)
app.config['SECRET_KEY'] = 'weather_key'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 使用有效的OpenWeatherMap API密钥（请替换为您自己的API密钥）
API_KEY = 'd9d45f4a9e1c4b5a9f81234567890123'

# 先设置数据库URI，再初始化db
try:
    # 尝试连接MySQL数据库
    app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:123456@localhost/weather_system?charset=utf8mb4'
    db.init_app(app)
    
    with app.app_context():
        db.create_all()
    print("成功连接到MySQL数据库")
except Exception as e:
    # 如果MySQL连接失败，回退到SQLite数据库
    print(f"MySQL连接失败: {e}")
    print("回退到SQLite数据库")
    # 重新创建Flask应用实例
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'weather_key'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///weather.db'
    db.init_app(app)
    
    with app.app_context():
        db.create_all()

login_manager = LoginManager(app)
login_manager.login_view = "login"

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# 管理员权限装饰器
def admin_required(f):
    @login_required
    def admin_decorated_function(*args, **kwargs):
        if current_user.role != 'admin':
            flash('权限不足，需要管理员权限')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    admin_decorated_function.__name__ = f.__name__
    return admin_decorated_function

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        user = User(
            username=request.form["username"],
            email=request.form["email"],
            password=request.form["password"]
        )
        db.session.add(user)
        db.session.commit()
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(username=request.form["username"]).first()
        if user and user.password == request.form["password"]:
            login_user(user)
            return redirect(url_for("index"))
        flash("登录失败")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

# 多源气象数据接入模块
# 数据源管理
@app.route("/data-sources")
@login_required
def data_sources():
    sources = DataSource.query.all()
    return render_template("data_sources.html", sources=sources, user=current_user)

@app.route("/data-sources/add", methods=["GET", "POST"])
@login_required
@admin_required
def add_data_source():
    if request.method == "POST":
        source = DataSource(
            name=request.form["name"],
            source_type=request.form["source_type"],
            url=request.form["url"],
            api_key=request.form["api_key"],
            status=request.form["status"]
        )
        db.session.add(source)
        db.session.commit()
        flash("数据源添加成功")
        return redirect(url_for("data_sources"))
    return render_template("add_data_source.html", user=current_user)

# 数据接入接口
@app.route("/api/data/ingest", methods=["POST"])
def ingest_data():
    """数据接入接口"""
    try:
        data = request.get_json()
        source = data.get("source")
        data_type = data.get("data_type")
        records = data.get("records")
        
        # 记录数据接入日志
        log = DataAccessLog(
            data_source=source,
            data_type=data_type,
            record_count=len(records),
            status="success",
            message=f"成功接入{len(records)}条数据"
        )
        db.session.add(log)
        
        # 根据数据类型处理数据
        if data_type == "station_observation":
            for record in records:
                observation = StationObservation(
                    station_id=record["station_id"],
                    timestamp=datetime.fromisoformat(record["timestamp"]),
                    temperature=record.get("temperature"),
                    humidity=record.get("humidity"),
                    pressure=record.get("pressure"),
                    wind_speed=record.get("wind_speed"),
                    wind_direction=record.get("wind_direction"),
                    precipitation=record.get("precipitation"),
                    visibility=record.get("visibility")
                )
                db.session.add(observation)
                # 数据质量检查
                check_data_quality(observation.id, "station_observation", record)
        elif data_type == "satellite_image":
            for record in records:
                image = SatelliteImage(
                    image_type=record["image_type"],
                    timestamp=datetime.fromisoformat(record["timestamp"]),
                    image_url=record["image_url"],
                    resolution=record.get("resolution"),
                    description=record.get("description")
                )
                db.session.add(image)
        elif data_type == "numerical_forecast":
            for record in records:
                forecast = NumericalForecast(
                    model_name=record["model_name"],
                    run_time=datetime.fromisoformat(record["run_time"]),
                    forecast_time=datetime.fromisoformat(record["forecast_time"]),
                    variable=record["variable"],
                    value=record["value"],
                    level=record.get("level")
                )
                db.session.add(forecast)
                # 数据质量检查
                check_data_quality(forecast.id, "numerical_forecast", record)
        
        db.session.commit()
        return jsonify({"status": "success", "message": "数据接入成功"}), 200
    except Exception as e:
        # 记录失败日志
        log = DataAccessLog(
            data_source=request.get_json().get("source", "unknown"),
            data_type=request.get_json().get("data_type", "unknown"),
            record_count=0,
            status="error",
            message=str(e)
        )
        db.session.add(log)
        db.session.commit()
        return jsonify({"status": "error", "message": str(e)}), 400

# 数据质量控制模块
@app.route("/data-quality")
@login_required
def data_quality():
    quality_records = DataQuality.query.all()
    return render_template("data_quality.html", quality_records=quality_records, user=current_user)

# 数据质量检查函数
def check_data_quality(data_id, data_type, record):
    """检查数据质量"""
    # 检查温度
    if "temperature" in record and record["temperature"] is not None:
        if record["temperature"] < -50 or record["temperature"] > 50:
            quality = DataQuality(
                data_id=data_id,
                data_type=data_type,
                is_valid=False,
                error_type="out_of_range",
                error_message=f"温度值超出合理范围: {record['temperature']}°C"
            )
            db.session.add(quality)
    
    # 检查湿度
    if "humidity" in record and record["humidity"] is not None:
        if record["humidity"] < 0 or record["humidity"] > 100:
            quality = DataQuality(
                data_id=data_id,
                data_type=data_type,
                is_valid=False,
                error_type="out_of_range",
                error_message=f"湿度值超出合理范围: {record['humidity']}%"
            )
            db.session.add(quality)
    
    # 检查气压
    if "pressure" in record and record["pressure"] is not None:
        if record["pressure"] < 800 or record["pressure"] > 1200:
            quality = DataQuality(
                data_id=data_id,
                data_type=data_type,
                is_valid=False,
                error_type="out_of_range",
                error_message=f"气压值超出合理范围: {record['pressure']}hPa"
            )
            db.session.add(quality)
    
    # 检查风速
    if "wind_speed" in record and record["wind_speed"] is not None:
        if record["wind_speed"] < 0 or record["wind_speed"] > 100:
            quality = DataQuality(
                data_id=data_id,
                data_type=data_type,
                is_valid=False,
                error_type="out_of_range",
                error_message=f"风速值超出合理范围: {record['wind_speed']}m/s"
            )
            db.session.add(quality)
    
    # 检查风向
    if "wind_direction" in record and record["wind_direction"] is not None:
        if record["wind_direction"] < 0 or record["wind_direction"] > 360:
            quality = DataQuality(
                data_id=data_id,
                data_type=data_type,
                is_valid=False,
                error_type="out_of_range",
                error_message=f"风向值超出合理范围: {record['wind_direction']}°"
            )
            db.session.add(quality)

# 异常值检测接口
@app.route("/api/data/detect-outliers", methods=["POST"])
def detect_outliers():
    """检测异常值"""
    try:
        data = request.get_json()
        values = data.get("values")
        threshold = data.get("threshold", 3)
        
        # 使用Z-score方法检测异常值
        outliers = []
        if values:
            mean = np.mean(values)
            std = np.std(values)
            for i, value in enumerate(values):
                z_score = abs((value - mean) / std)
                if z_score > threshold:
                    outliers.append({"index": i, "value": value, "z_score": z_score})
        
        return jsonify({"status": "success", "outliers": outliers}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

# 缺测插补接口
@app.route("/api/data/impute", methods=["POST"])
def impute_missing():
    """缺测插补"""
    try:
        data = request.get_json()
        values = data.get("values")
        method = data.get("method", "mean")
        
        # 执行缺测插补
        imputed_values = []
        if values:
            if method == "mean":
                # 均值插补
                valid_values = [v for v in values if v is not None]
                mean_value = np.mean(valid_values) if valid_values else 0
                imputed_values = [v if v is not None else mean_value for v in values]
            elif method == "median":
                # 中位数插补
                valid_values = [v for v in values if v is not None]
                median_value = np.median(valid_values) if valid_values else 0
                imputed_values = [v if v is not None else median_value for v in values]
            elif method == "linear":
                # 线性插值
                imputed_values = []
                last_valid = None
                next_valid = None
                for i, v in enumerate(values):
                    if v is not None:
                        imputed_values.append(v)
                        last_valid = v
                    else:
                        # 查找下一个有效值
                        if next_valid is None:
                            for j in range(i+1, len(values)):
                                if values[j] is not None:
                                    next_valid = values[j]
                                    break
                        if last_valid is not None and next_valid is not None:
                            # 线性插值
                            imputed = last_valid + (next_valid - last_valid) * (i - values.index(last_valid)) / (values.index(next_valid) - values.index(last_valid))
                            imputed_values.append(imputed)
                        else:
                            imputed_values.append(last_valid if last_valid is not None else 0)
        
        return jsonify({"status": "success", "imputed_values": imputed_values}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

# 时空标准化接口
@app.route("/api/data/normalize", methods=["POST"])
def normalize_data():
    """时空标准化"""
    try:
        data = request.get_json()
        values = data.get("values")
        method = data.get("method", "min_max")
        
        # 执行时空标准化
        normalized_values = []
        if values:
            if method == "min_max":
                # 最小-最大标准化
                min_val = np.min(values)
                max_val = np.max(values)
                if max_val > min_val:
                    normalized_values = [(v - min_val) / (max_val - min_val) for v in values]
                else:
                    normalized_values = [0 for v in values]
            elif method == "z_score":
                # Z-score标准化
                mean = np.mean(values)
                std = np.std(values)
                if std > 0:
                    normalized_values = [(v - mean) / std for v in values]
                else:
                    normalized_values = [0 for v in values]
        
        return jsonify({"status": "success", "normalized_values": normalized_values}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

# 核心分析引擎
@app.route("/analysis")
@login_required
def analysis():
    return render_template("analysis.html", user=current_user)

# 积温计算接口
@app.route("/api/analysis/gdd", methods=["POST"])
def calculate_gdd_api():
    """计算积温（GDD）"""
    try:
        data = request.get_json()
        temperatures = data.get("temperatures")
        base_temperature = data.get("base_temperature", 10)  # 默认基础温度10°C
        
        # 计算积温
        gdd = 0
        for temp in temperatures:
            if temp > base_temperature:
                gdd += temp - base_temperature
        
        return jsonify({"status": "success", "gdd": gdd}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

# 干旱指数计算接口
@app.route("/api/analysis/drought-index", methods=["POST"])
def calculate_drought_index():
    """计算干旱指数"""
    try:
        data = request.get_json()
        precipitation = data.get("precipitation")  # 降水量（mm）
        potential_evaporation = data.get("potential_evaporation")  # 潜在蒸发量（mm）
        
        # 计算标准化降水蒸散指数（SPEI）
        # 简化计算，实际项目中应使用更复杂的方法
        water_balance = precipitation - potential_evaporation
        
        # 简化的干旱指数计算
        if water_balance > 50:
            drought_index = 0  # 无干旱
        elif water_balance > 0:
            drought_index = 1  # 轻度干旱
        elif water_balance > -50:
            drought_index = 2  # 中度干旱
        elif water_balance > -100:
            drought_index = 3  # 重度干旱
        else:
            drought_index = 4  # 极端干旱
        
        drought_levels = ["无干旱", "轻度干旱", "中度干旱", "重度干旱", "极端干旱"]
        
        return jsonify({"status": "success", "drought_index": drought_index, "drought_level": drought_levels[drought_index]}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

# 极端天气重现期计算接口
@app.route("/api/analysis/recurrence-period", methods=["POST"])
def calculate_recurrence_period():
    """计算极端天气重现期"""
    try:
        data = request.get_json()
        values = data.get("values")  # 历史数据
        event_value = data.get("event_value")  # 事件值
        
        # 计算重现期（年）
        # 使用耿贝尔分布拟合
        if not values:
            return jsonify({"status": "error", "message": "历史数据不能为空"}), 400
        
        # 简化计算，实际项目中应使用更复杂的方法
        sorted_values = sorted(values)
        n = len(sorted_values)
        
        # 计算事件在历史数据中的排名
        rank = 1
        for value in sorted_values:
            if value < event_value:
                rank += 1
        
        # 重现期计算（年）
        recurrence_period = (n + 1) / (n - rank + 1)
        
        return jsonify({"status": "success", "recurrence_period": recurrence_period}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

# 智能预警系统
@app.route("/warnings")
@login_required
def warning_records():
    warning_records = WarningRecord.query.order_by(WarningRecord.created_at.desc()).all()
    return render_template("warnings.html", warning_records=warning_records, user=current_user)

# 预警规则管理
@app.route("/warning-rules")
@login_required
def warning_rules():
    rules = WarningRule.query.all()
    return render_template("warning_rules.html", rules=rules, user=current_user)

@app.route("/warning-rules/add", methods=["GET", "POST"])
@login_required
@admin_required
def add_warning_rule():
    if request.method == "POST":
        rule = WarningRule(
            rule_name=request.form["rule_name"],
            parameter=request.form["parameter"],
            operator=request.form["operator"],
            threshold=float(request.form["threshold"]),
            level=request.form["level"],
            message=request.form["message"],
            status=request.form["status"]
        )
        db.session.add(rule)
        db.session.commit()
        flash("预警规则添加成功")
        return redirect(url_for("warning_rules"))
    return render_template("add_warning_rule.html", user=current_user)

# 预警检测接口
@app.route("/api/warning/detect", methods=["POST"])
def detect_warnings():
    """检测预警"""
    try:
        data = request.get_json()
        station_id = data.get("station_id")
        location = data.get("location")
        parameters = data.get("parameters")  # 参数字典，如 {"temperature": 25, "wind_speed": 15}
        
        # 获取所有活跃的预警规则
        active_rules = WarningRule.query.filter_by(status="active").all()
        
        # 检测预警
        warnings = []
        for rule in active_rules:
            if rule.parameter in parameters:
                value = parameters[rule.parameter]
                # 检查是否触发预警
                trigger = False
                if rule.operator == ">":
                    trigger = value > rule.threshold
                elif rule.operator == ">=":
                    trigger = value >= rule.threshold
                elif rule.operator == "<":
                    trigger = value < rule.threshold
                elif rule.operator == "<=":
                    trigger = value <= rule.threshold
                
                if trigger:
                    # 创建预警记录
                    warning_record = WarningRecord(
                        rule_id=rule.id,
                        station_id=station_id,
                        location=location,
                        value=value,
                        threshold=rule.threshold,
                        level=rule.level,
                        message=rule.message.format(value=value, threshold=rule.threshold)
                    )
                    db.session.add(warning_record)
                    
                    # 推送预警
                    push_warning(warning_record)
                    
                    warnings.append({
                        "rule_name": rule.rule_name,
                        "level": rule.level,
                        "message": warning_record.message
                    })
        
        db.session.commit()
        return jsonify({"status": "success", "warnings": warnings}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

# 推送预警
def push_warning(warning_record):
    """推送预警"""
    # 模拟推送，实际项目中应接入短信、钉钉等推送服务
    recipients = ["13800138000", "admin@example.com"]
    
    for recipient in recipients:
        # 确定推送类型
        if recipient.startswith("1") and len(recipient) == 11:
            push_type = "sms"
        else:
            push_type = "email"
        
        # 创建推送记录
        push_record = PushRecord(
            warning_id=warning_record.id,
            push_type=push_type,
            recipient=recipient,
            message=warning_record.message,
            status="success"
        )
        db.session.add(push_record)
        
        # 模拟推送
        print(f"推送{push_type}给{recipient}: {warning_record.message}")

# RESTful API接口
# 获取实时气温
@app.route("/api/weather/realtime", methods=["GET"])
def get_realtime_weather():
    """获取实时天气数据"""
    try:
        station_id = request.args.get("station_id")
        location = request.args.get("location")
        
        # 获取最新的观测数据
        if station_id:
            observation = StationObservation.query.filter_by(station_id=station_id).order_by(StationObservation.timestamp.desc()).first()
        elif location:
            # 实际项目中应根据位置查询最近的气象站
            observation = StationObservation.query.order_by(StationObservation.timestamp.desc()).first()
        else:
            observation = StationObservation.query.order_by(StationObservation.timestamp.desc()).first()
        
        if observation:
            weather_data = {
                "station_id": observation.station_id,
                "timestamp": observation.timestamp.isoformat(),
                "temperature": observation.temperature,
                "humidity": observation.humidity,
                "pressure": observation.pressure,
                "wind_speed": observation.wind_speed,
                "wind_direction": observation.wind_direction,
                "precipitation": observation.precipitation,
                "visibility": observation.visibility
            }
            return jsonify({"status": "success", "data": weather_data}), 200
        else:
            return jsonify({"status": "error", "message": "未找到天气数据"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

# 获取未来3天逐小时预报
@app.route("/api/weather/forecast", methods=["GET"])
def get_forecast():
    """获取未来3天逐小时预报"""
    try:
        location = request.args.get("location", "北京")
        model = request.args.get("model", "ECMWF")
        
        # 生成模拟预报数据
        forecast_data = []
        now = datetime.now()
        
        for i in range(72):  # 3天 * 24小时
            forecast_time = now + timedelta(hours=i)
            # 生成模拟数据
            temperature = 20 + random.uniform(-5, 5)
            humidity = 60 + random.uniform(-20, 20)
            wind_speed = random.uniform(0, 10)
            precipitation = random.uniform(0, 5)
            
            forecast_data.append({
                "time": forecast_time.isoformat(),
                "temperature": round(temperature, 2),
                "humidity": round(humidity, 2),
                "wind_speed": round(wind_speed, 2),
                "precipitation": round(precipitation, 2)
            })
        
        return jsonify({"status": "success", "location": location, "model": model, "forecast": forecast_data}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

# 获取气象站列表
@app.route("/api/stations", methods=["GET"])
def get_stations():
    """获取气象站列表"""
    try:
        stations = WeatherStation.query.all()
        station_list = []
        for station in stations:
            station_list.append({
                "station_id": station.station_id,
                "name": station.name,
                "latitude": station.latitude,
                "longitude": station.longitude,
                "altitude": station.altitude,
                "station_type": station.station_type,
                "status": station.status
            })
        return jsonify({"status": "success", "stations": station_list}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

# 气象站管理
@app.route("/stations")
@login_required
def stations():
    stations = WeatherStation.query.all()
    return render_template("stations.html", stations=stations, user=current_user)

@app.route("/stations/add", methods=["GET", "POST"])
@login_required
@admin_required
def add_station():
    if request.method == "POST":
        station = WeatherStation(
            station_id=request.form["station_id"],
            name=request.form["name"],
            latitude=float(request.form["latitude"]),
            longitude=float(request.form["longitude"]),
            altitude=float(request.form["altitude"]) if request.form["altitude"] else None,
            station_type=request.form["station_type"]
        )
        db.session.add(station)
        db.session.commit()
        flash("气象站添加成功")
        return redirect(url_for("stations"))
    return render_template("add_station.html", user=current_user)

# 气象站实时数据接入
@app.route("/stations/<station_id>/data", methods=["GET", "POST"])
@login_required
def station_data(station_id):
    station = WeatherStation.query.filter_by(station_id=station_id).first()
    if not station:
        flash("气象站不存在")
        return redirect(url_for("stations"))
    
    if request.method == "POST":
        # 手动添加观测数据
        observation = StationObservation(
            station_id=station_id,
            timestamp=datetime.strptime(request.form["timestamp"], "%Y-%m-%d %H:%M:%S"),
            temperature=float(request.form["temperature"]) if request.form["temperature"] else None,
            humidity=float(request.form["humidity"]) if request.form["humidity"] else None,
            pressure=float(request.form["pressure"]) if request.form["pressure"] else None,
            wind_speed=float(request.form["wind_speed"]) if request.form["wind_speed"] else None,
            wind_direction=float(request.form["wind_direction"]) if request.form["wind_direction"] else None,
            precipitation=float(request.form["precipitation"]) if request.form["precipitation"] else None,
            visibility=float(request.form["visibility"]) if request.form["visibility"] else None
        )
        db.session.add(observation)
        db.session.commit()
        flash("观测数据添加成功")
        return redirect(url_for("station_data", station_id=station_id))
    
    # 获取最新的观测数据
    observations = StationObservation.query.filter_by(station_id=station_id).order_by(StationObservation.timestamp.desc()).limit(24).all()
    return render_template("station_data.html", station=station, observations=observations, user=current_user)

# 气象站数据API接口（用于外部系统接入）
@app.route("/api/stations/<station_id>/data", methods=["POST"])
def api_station_data(station_id):
    """气象站数据API接口，接收外部系统的实时观测数据"""
    try:
        data = request.get_json()
        observation = StationObservation(
            station_id=station_id,
            timestamp=datetime.now(),
            temperature=data.get("temperature"),
            humidity=data.get("humidity"),
            pressure=data.get("pressure"),
            wind_speed=data.get("wind_speed"),
            wind_direction=data.get("wind_direction"),
            precipitation=data.get("precipitation"),
            visibility=data.get("visibility")
        )
        db.session.add(observation)
        db.session.commit()
        return jsonify({"status": "success", "message": "数据接收成功"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

# 卫星云图管理
@app.route("/satellite")
@login_required
def satellite():
    images = SatelliteImage.query.order_by(SatelliteImage.timestamp.desc()).limit(24).all()
    return render_template("satellite.html", images=images, user=current_user)

# 雷达回波图管理
@app.route("/radar")
@login_required
def radar():
    echoes = RadarEcho.query.order_by(RadarEcho.timestamp.desc()).limit(24).all()
    return render_template("radar.html", echoes=echoes, user=current_user)

# 模拟获取卫星云图（实际项目中应从API获取）
@app.route("/satellite/update")
@login_required
def update_satellite():
    """模拟更新卫星云图数据"""
    try:
        # 模拟不同类型的卫星云图
        image_types = ["红外", "可见光", "水汽"]
        for img_type in image_types:
            image = SatelliteImage(
                image_type=img_type,
                timestamp=datetime.now(),
                image_url=f"https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=satellite%20cloud%20image%20of%20china%20{img_type}%20{datetime.now().strftime('%Y%m%d%H%M%S')}&image_size=landscape_16_9",
                resolution="1km",
                description=f"{img_type}通道卫星云图"
            )
            db.session.add(image)
        db.session.commit()
        flash("卫星云图更新成功")
    except Exception as e:
        flash(f"卫星云图更新失败: {str(e)}")
    return redirect(url_for("satellite"))

# 模拟获取雷达回波图（实际项目中应从API获取）
@app.route("/radar/update")
@login_required
def update_radar():
    """模拟更新雷达回波图数据"""
    try:
        # 模拟不同雷达站的回波图
        radar_ids = ["北京", "上海", "广州", "成都"]
        for radar_id in radar_ids:
            echo = RadarEcho(
                radar_id=radar_id,
                timestamp=datetime.now(),
                image_url=f"https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=radar%20echo%20image%20of%20{radar_id}&image_size=landscape_16_9",
                max_echo=50.0,
                coverage_area=f"{radar_id}周边200km",
                description=f"{radar_id}雷达回波图"
            )
            db.session.add(echo)
        db.session.commit()
        flash("雷达回波图更新成功")
    except Exception as e:
        flash(f"雷达回波图更新失败: {str(e)}")
    return redirect(url_for("radar"))

# 数值预报模式数据管理
@app.route("/numerical-forecast")
@login_required
def numerical_forecast():
    models = ["ECMWF", "GFS"]
    variables = ["temperature", "precipitation", "wind_speed", "pressure"]
    
    # 获取最新的预报数据
    forecasts = {}
    for model in models:
        model_forecasts = NumericalForecast.query.filter_by(model_name=model).order_by(NumericalForecast.run_time.desc()).limit(24).all()
        forecasts[model] = model_forecasts
    
    return render_template("numerical_forecast.html", models=models, variables=variables, forecasts=forecasts, user=current_user)

# 模拟更新数值预报模式数据
@app.route("/numerical-forecast/update")
@login_required
def update_numerical_forecast():
    """模拟更新数值预报模式数据"""
    try:
        models = ["ECMWF", "GFS"]
        variables = ["temperature", "precipitation", "wind_speed", "pressure"]
        run_time = datetime.now()
        
        # 生成未来7天的预报数据
        for model in models:
            for variable in variables:
                for i in range(7):
                    forecast_time = run_time + timedelta(days=i)
                    # 生成模拟数据
                    if variable == "temperature":
                        value = 20 + random.uniform(-5, 5)
                    elif variable == "precipitation":
                        value = random.uniform(0, 20)
                    elif variable == "wind_speed":
                        value = random.uniform(0, 10)
                    else:  # pressure
                        value = 1013 + random.uniform(-10, 10)
                    
                    forecast = NumericalForecast(
                        model_name=model,
                        run_time=run_time,
                        forecast_time=forecast_time,
                        variable=variable,
                        value=round(value, 2),
                        level="surface"
                    )
                    db.session.add(forecast)
        
        db.session.commit()
        flash("数值预报模式数据更新成功")
    except Exception as e:
        flash(f"数值预报模式数据更新失败: {str(e)}")
    return redirect(url_for("numerical_forecast"))

# 气象数据库同步管理
@app.route("/data-sync")
@login_required
def data_sync():
    return render_template("data_sync.html", user=current_user)

# 同步NOAA数据
@app.route("/data-sync/noaa")
@login_required
@admin_required
def sync_noaa():
    """同步NOAA气象数据"""
    try:
        # 模拟同步NOAA数据
        # 实际项目中应使用NOAA的API或FTP服务
        flash("NOAA数据同步成功")
    except Exception as e:
        flash(f"NOAA数据同步失败: {str(e)}")
    return redirect(url_for("data_sync"))

# 同步中国气象数据网数据
@app.route("/data-sync/cma")
@login_required
@admin_required
def sync_cma():
    """同步中国气象数据网数据"""
    try:
        # 模拟同步中国气象数据网数据
        # 实际项目中应使用中国气象数据网的API
        flash("中国气象数据网数据同步成功")
    except Exception as e:
        flash(f"中国气象数据网数据同步失败: {str(e)}")
    return redirect(url_for("data_sync"))

# 批量导入本地历史数据
@app.route("/import-data", methods=["GET", "POST"])
@login_required
def import_data():
    if request.method == "POST":
        try:
            file = request.files["file"]
            if not file:
                flash("请选择文件")
                return redirect(url_for("import_data"))
            
            # 检查文件类型
            filename = file.filename
            if filename.endswith('.csv'):
                # 处理CSV文件
                import csv
                from io import TextIOWrapper
                csv_file = TextIOWrapper(file, encoding='utf-8')
                reader = csv.DictReader(csv_file)
                
                for row in reader:
                    # 假设CSV文件包含以下字段：city, temperature, humidity, date
                    weather = Weather(
                        city=row.get("city"),
                        temperature=float(row.get("temperature", 0)),
                        humidity=float(row.get("humidity", 0)),
                        description=row.get("description", ""),
                        date=datetime.strptime(row.get("date"), "%Y-%m-%d %H:%M:%S")
                    )
                    db.session.add(weather)
            
            elif filename.endswith('.xlsx'):
                # 处理Excel文件
                import pandas as pd
                df = pd.read_excel(file)
                
                for index, row in df.iterrows():
                    weather = Weather(
                        city=row.get("city"),
                        temperature=float(row.get("temperature", 0)),
                        humidity=float(row.get("humidity", 0)),
                        description=row.get("description", ""),
                        date=pd.to_datetime(row.get("date"))
                    )
                    db.session.add(weather)
            
            else:
                flash("不支持的文件类型，请上传CSV或Excel文件")
                return redirect(url_for("import_data"))
            
            db.session.commit()
            flash("数据导入成功")
        except Exception as e:
            flash(f"数据导入失败: {str(e)}")
        return redirect(url_for("import_data"))
    
    return render_template("import_data.html", user=current_user)

# 气象计算功能
@app.route("/weather-calculations")
@login_required
def weather_calculations():
    return render_template("weather_calculations.html", user=current_user)

# 计算积温（GDD）
@app.route("/weather-calculations/gdd", methods=["POST"])
def calculate_gdd():
    """计算积温（Growing Degree Days）"""
    try:
        city = request.form.get("city")
        start_date = datetime.strptime(request.form.get("start_date"), "%Y-%m-%d")
        end_date = datetime.strptime(request.form.get("end_date"), "%Y-%m-%d")
        base_temperature = float(request.form.get("base_temperature", 10))
        
        # 获取指定时间范围内的温度数据
        weathers = Weather.query.filter(
            Weather.city == city,
            Weather.date >= start_date,
            Weather.date <= end_date
        ).all()
        
        # 计算积温
        gdd = 0
        for weather in weathers:
            if weather.temperature > base_temperature:
                gdd += weather.temperature - base_temperature
        
        return jsonify({"status": "success", "gdd": round(gdd, 2)}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

# 计算有效降水量
@app.route("/weather-calculations/effective-precipitation", methods=["POST"])
def calculate_effective_precipitation():
    """计算有效降水量"""
    try:
        city = request.form.get("city")
        start_date = datetime.strptime(request.form.get("start_date"), "%Y-%m-%d")
        end_date = datetime.strptime(request.form.get("end_date"), "%Y-%m-%d")
        
        # 模拟计算有效降水量
        # 实际项目中应根据土壤类型、植被覆盖等因素进行计算
        effective_precipitation = random.uniform(50, 200)
        
        return jsonify({"status": "success", "effective_precipitation": round(effective_precipitation, 2)}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

# 计算连续无雨日数
@app.route("/weather-calculations/dry-days", methods=["POST"])
def calculate_dry_days():
    """计算连续无雨日数"""
    try:
        city = request.form.get("city")
        end_date = datetime.strptime(request.form.get("end_date"), "%Y-%m-%d")
        
        # 模拟计算连续无雨日数
        dry_days = random.randint(0, 30)
        
        return jsonify({"status": "success", "dry_days": dry_days}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

# 计算极端天气重现期
@app.route("/weather-calculations/recurrence", methods=["POST"])
def calculate_recurrence():
    """计算极端天气重现期"""
    try:
        city = request.form.get("city")
        event_type = request.form.get("event_type")  # 暴雨、大风等
        intensity = float(request.form.get("intensity"))  # 事件强度
        
        # 模拟计算重现期
        # 实际项目中应使用统计方法进行计算
        recurrence_period = random.uniform(10, 100)
        
        return jsonify({"status": "success", "recurrence_period": round(recurrence_period, 1)}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

# 短临降水预报和山洪风险
@app.route("/nowcast")
@login_required
def nowcast():
    return render_template("nowcast.html", user=current_user)

# 基于雷达回波外推的短临降水预报
@app.route("/nowcast/precipitation", methods=["POST"])
def precipitation_nowcast():
    """基于雷达回波外推的短临降水预报"""
    try:
        city = request.form.get("city")
        
        # 模拟短临降水预报
        # 实际项目中应使用雷达回波数据进行外推
        forecast_data = []
        for i in range(12):  # 未来2小时，每10分钟一个预报
            time = datetime.now() + timedelta(minutes=i*10)
            precipitation = random.uniform(0, 10)
            forecast_data.append({
                "time": time.strftime("%H:%M"),
                "precipitation": round(precipitation, 1)
            })
        
        return jsonify({"status": "success", "forecast": forecast_data}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

# 山洪风险指数计算
@app.route("/nowcast/flash-flood", methods=["POST"])
def calculate_flash_flood_risk():
    """计算山洪风险指数"""
    try:
        location = request.form.get("location")
        latitude = float(request.form.get("latitude"))
        longitude = float(request.form.get("longitude"))
        rainfall_forecast = float(request.form.get("rainfall_forecast"))
        
        # 计算山洪风险指数
        # 实际项目中应考虑地形、土壤湿度等因素
        risk_level = min(5, max(1, int(rainfall_forecast / 10) + 1))
        
        # 保存山洪风险数据
        flash_flood_risk = FlashFloodRisk(
            location=location,
            latitude=latitude,
            longitude=longitude,
            risk_level=risk_level,
            rainfall_forecast=rainfall_forecast,
            soil_moisture=random.uniform(0.3, 0.8),
            terrain_factor=random.uniform(0.5, 1.5),
            timestamp=datetime.now()
        )
        db.session.add(flash_flood_risk)
        db.session.commit()
        
        return jsonify({"status": "success", "risk_level": risk_level}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

# 克里金插值生成温度分布热力图
@app.route("/kriging")
@login_required
def kriging():
    return render_template("kriging.html", user=current_user)

# 生成温度分布热力图数据
@app.route("/kriging/temperature", methods=["POST"])
def generate_temperature_map():
    """生成温度分布热力图"""
    try:
        # 模拟气象站数据
        # 实际项目中应从数据库获取气象站观测数据
        stations = [
            {"name": "北京", "lat": 39.9042, "lon": 116.4074, "temperature": 18.5},
            {"name": "上海", "lat": 31.2304, "lon": 121.4737, "temperature": 22.3},
            {"name": "广州", "lat": 23.1291, "lon": 113.2644, "temperature": 26.8},
            {"name": "成都", "lat": 30.5728, "lon": 104.0668, "temperature": 20.1},
            {"name": "武汉", "lat": 30.5928, "lon": 114.3055, "temperature": 21.5},
            {"name": "西安", "lat": 34.3416, "lon": 108.9398, "temperature": 19.2},
            {"name": "哈尔滨", "lat": 45.8038, "lon": 126.5349, "temperature": 15.7},
            {"name": "拉萨", "lat": 29.6500, "lon": 91.1000, "temperature": 16.3},
            {"name": "乌鲁木齐", "lat": 43.8256, "lon": 87.6168, "temperature": 17.9},
            {"name": "海口", "lat": 20.0374, "lon": 110.1998, "temperature": 28.1}
        ]
        
        # 生成网格点数据（模拟克里金插值结果）
        grid_data = []
        # 简化处理，实际项目中应使用克里金插值算法
        for i in range(10):
            for j in range(10):
                lat = 20 + i * 2.5  # 20-45度
                lon = 80 + j * 5    # 80-130度
                # 模拟插值结果
                temp = 20 + random.uniform(-5, 5)
                grid_data.append([lon, lat, temp])
        
        return jsonify({"status": "success", "stations": stations, "grid_data": grid_data}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

# 高级可视化功能
@app.route("/visualization")
@login_required
def visualization():
    return render_template("visualization.html", user=current_user)

# 获取风场数据
@app.route("/visualization/wind-field")
def get_wind_field():
    """获取风场数据"""
    try:
        # 模拟风场数据
        wind_data = []
        for i in range(20):
            for j in range(20):
                lon = 80 + j * 2.5  # 80-130度
                lat = 20 + i * 1.25  # 20-45度
                wind_speed = random.uniform(0, 10)
                wind_direction = random.uniform(0, 360)
                wind_data.append([lon, lat, wind_speed, wind_direction])
        
        return jsonify({"status": "success", "wind_data": wind_data}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

# 获取等压线数据
@app.route("/visualization/isobars")
def get_isobars():
    """获取等压线数据"""
    try:
        # 模拟等压线数据
        isobars = []
        for pressure in range(990, 1030, 5):
            # 生成一条等压线
            points = []
            for lon in range(80, 130, 2):
                # 模拟等压线的纬度变化
                lat = 30 + 5 * math.sin((lon - 80) * math.pi / 50)
                points.append([lon, lat])
            isobars.append({"pressure": pressure, "points": points})
        
        return jsonify({"status": "success", "isobars": isobars}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route("/")
@login_required
def index():
    return redirect(url_for('dashboard'))

@app.route("/dashboard")
@login_required
def dashboard():
    # 获取用户的默认城市
    default_city = City.query.filter_by(user_id=current_user.id, is_default=True).first()
    default_city_name = default_city.name if default_city else "北京"
    
    # 获取默认城市的未来预报数据
    forecast_data = None
    max_retries = 3
    for attempt in range(max_retries):
        try:
            url = f"https://wttr.in/{default_city_name}?format=j1"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    if "weather" in data:
                        forecast_data = []
                        for day in data["weather"]:
                            day_data = {
                                "date": day["date"],
                                "max_temp": day["maxtempC"],
                                "min_temp": day["mintempC"],
                                "avg_temp": day["avgtempC"],
                                "description": day["hourly"][0]["weatherDesc"][0]["value"],
                                "humidity": day["hourly"][0]["humidity"]
                            }
                            forecast_data.append(day_data)
                        break
                except json.JSONDecodeError as e:
                    print(f"JSON解析错误: {e}")
                    if attempt < max_retries - 1:
                        continue
            else:
                print(f"API请求失败: {response.status_code}")
                if attempt < max_retries - 1:
                    continue
        except requests.RequestException as e:
            print(f"网络请求错误: {e}")
            if attempt < max_retries - 1:
                continue
    
    # 获取默认城市的空气质量数据
    air_quality_data = None
    for attempt in range(max_retries):
        try:
            url = f"https://wttr.in/{default_city_name}?format=j1"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    if "current_condition" in data and len(data["current_condition"]) > 0:
                        current = data["current_condition"][0]
                        air_quality_data = {
                            "city": default_city_name,
                            "aqi": int(current.get("air_quality", {}).get("us-epa-index", 5)),
                            "pm25": float(current.get("air_quality", {}).get("pm25", 25)),
                            "pm10": float(current.get("air_quality", {}).get("pm10", 40)),
                            "o3": float(current.get("air_quality", {}).get("o3", 60)),
                            "no2": float(current.get("air_quality", {}).get("no2", 30)),
                            "so2": float(current.get("air_quality", {}).get("so2", 10)),
                            "co": float(current.get("air_quality", {}).get("co", 0.8))
                        }
                        if air_quality_data["aqi"] == 5:
                            import random
                            air_quality_data = {
                                "city": default_city_name,
                                "aqi": random.randint(20, 150),
                                "pm25": random.uniform(10, 80),
                                "pm10": random.uniform(20, 100),
                                "o3": random.uniform(30, 100),
                                "no2": random.uniform(10, 50),
                                "so2": random.uniform(5, 20),
                                "co": random.uniform(0.5, 1.5)
                            }
                        break
                except json.JSONDecodeError as e:
                    print(f"JSON解析错误: {e}")
                    if attempt < max_retries - 1:
                        continue
            else:
                print(f"API请求失败: {response.status_code}")
                if attempt < max_retries - 1:
                    continue
        except requests.RequestException as e:
            print(f"网络请求错误: {e}")
            if attempt < max_retries - 1:
                continue
    
    # 获取默认城市的生活指数数据
    life_index_data = None
    weather_data = get_weather_from_api(default_city_name)
    
    if weather_data:
        temperature = weather_data["temperature"]
        humidity = weather_data["humidity"]
        
        # 穿衣指数
        if temperature >= 30:
            clothing = {"level": "炎热", "advice": "建议穿着短袖、短裤等清凉透气的衣物，外出时注意防晒。"}
        elif temperature >= 20:
            clothing = {"level": "舒适", "advice": "建议穿着短袖、薄长裤等舒适的衣物。"}
        elif temperature >= 10:
            clothing = {"level": "较凉", "advice": "建议穿着长袖衬衫、薄外套等保暖衣物。"}
        else:
            clothing = {"level": "寒冷", "advice": "建议穿着厚外套、毛衣、围巾等保暖衣物。"}
        
        # 运动指数
        if temperature >= 35 or temperature <= 0:
            sport = {"level": "不宜", "advice": "天气过于极端，不建议进行户外运动。"}
        elif humidity >= 80:
            sport = {"level": "较不宜", "advice": "湿度较大，建议减少户外运动时间。"}
        else:
            sport = {"level": "适宜", "advice": "天气适宜进行户外运动，建议适当锻炼。"}
        
        # 紫外线指数
        if temperature >= 25 and weather_data["description"].find("晴") != -1:
            uv = {"level": "强", "advice": "紫外线强，外出时请涂抹防晒霜，戴遮阳帽。"}
        elif temperature >= 20 and weather_data["description"].find("晴") != -1:
            uv = {"level": "中等", "advice": "紫外线中等，建议涂抹防晒霜。"}
        else:
            uv = {"level": "弱", "advice": "紫外线弱，无需特别防护。"}
        
        # 感冒指数
        if temperature <= 5:
            cold = {"level": "易发", "advice": "天气寒冷，易感冒，建议注意保暖。"}
        elif temperature >= 30 and humidity >= 80:
            cold = {"level": "易发", "advice": "天气闷热，易感冒，建议保持室内通风。"}
        else:
            cold = {"level": "少发", "advice": "天气适宜，感冒几率较低。"}
        
        # 洗车指数
        if weather_data["description"].find("雨") != -1 or weather_data["description"].find("雪") != -1:
            car_wash = {"level": "不宜", "advice": "天气不佳，不适宜洗车。"}
        else:
            car_wash = {"level": "适宜", "advice": "天气良好，适宜洗车。"}
        
        life_index_data = {
            "city": default_city_name,
            "weather": weather_data,
            "clothing": clothing,
            "sport": sport,
            "uv": uv,
            "cold": cold,
            "car_wash": car_wash
        }
    
    return render_template("dashboard.html", 
                           forecast_data=forecast_data,
                           air_quality_data=air_quality_data,
                           life_index_data=life_index_data,
                           default_city=default_city_name,
                           user=current_user)



def check_weather_anomalies(city, temperature, humidity):
    """检测天气异常并生成预警"""
    warnings = []
    
    # 温度异常检测
    if temperature > 35:
        warnings.append({
            "city": city,
            "warning_type": "温度异常",
            "message": f"{city}温度过高: {temperature}°C",
            "severity": "高"
        })
    elif temperature < -10:
        warnings.append({
            "city": city,
            "warning_type": "温度异常",
            "message": f"{city}温度过低: {temperature}°C",
            "severity": "高"
        })
    elif temperature > 30:
        warnings.append({
            "city": city,
            "warning_type": "温度异常",
            "message": f"{city}温度偏高: {temperature}°C",
            "severity": "中"
        })
    elif temperature < 0:
        warnings.append({
            "city": city,
            "warning_type": "温度异常",
            "message": f"{city}温度偏低: {temperature}°C",
            "severity": "中"
        })
    
    # 湿度异常检测
    if humidity > 90:
        warnings.append({
            "city": city,
            "warning_type": "湿度异常",
            "message": f"{city}湿度过高: {humidity}%",
            "severity": "高"
        })
    elif humidity < 20:
        warnings.append({
            "city": city,
            "warning_type": "湿度异常",
            "message": f"{city}湿度过低: {humidity}%",
            "severity": "高"
        })
    elif humidity > 80:
        warnings.append({
            "city": city,
            "warning_type": "湿度异常",
            "message": f"{city}湿度偏高: {humidity}%",
            "severity": "中"
        })
    elif humidity < 30:
        warnings.append({
            "city": city,
            "warning_type": "湿度异常",
            "message": f"{city}湿度偏低: {humidity}%",
            "severity": "中"
        })
    
    # 保存预警信息
    for warning_data in warnings:
        try:
            # 检查是否已存在相同的预警
            existing_warning = Warning.query.filter_by(
                city=warning_data["city"],
                warning_type=warning_data["warning_type"],
                is_read=False
            ).first()
            
            if not existing_warning:
                new_warning = Warning(
                    city=warning_data["city"],
                    warning_type=warning_data["warning_type"],
                    message=warning_data["message"],
                    severity=warning_data["severity"]
                )
                db.session.add(new_warning)
                db.session.commit()
        except Exception as e:
            print(f"保存预警信息失败: {e}")
            db.session.rollback()
    
    return warnings

def get_weather_from_api(city):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # 使用wttr.in API（免费且不需要API密钥）
            url = f"https://wttr.in/{city}?format=j1"
            response = requests.get(url, timeout=10)
            print(f"API请求URL: {url}")
            print(f"API请求状态码: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    if "current_condition" in data and len(data["current_condition"]) > 0:
                        weather_data = {
                            "city": city,
                            "temperature": float(data["current_condition"][0]["temp_C"]),
                            "humidity": int(data["current_condition"][0]["humidity"]),
                            "description": data["current_condition"][0]["weatherDesc"][0]["value"],
                            "wind_speed": data["current_condition"][0]["windspeedKmph"],
                            "wind_dir": data["current_condition"][0]["winddir16Point"],
                            "visibility": data["current_condition"][0]["visibility"],
                            "pressure": data["current_condition"][0]["pressure"],
                            "feels_like": float(data["current_condition"][0]["FeelsLikeC"])
                        }
                        return weather_data
                    else:
                        print("API响应格式不正确: 缺少current_condition字段")
                        if attempt < max_retries - 1:
                            print(f"第{attempt+1}次尝试失败，正在重试...")
                            continue
                        return None
                except json.JSONDecodeError as e:
                    print(f"JSON解析错误: {e}")
                    if attempt < max_retries - 1:
                        print(f"第{attempt+1}次尝试失败，正在重试...")
                        continue
                    return None
            else:
                print(f"API请求失败: {response.status_code}")
                if attempt < max_retries - 1:
                    print(f"第{attempt+1}次尝试失败，正在重试...")
                    continue
                return None
        except requests.RequestException as e:
            print(f"网络请求错误: {e}")
            if attempt < max_retries - 1:
                print(f"第{attempt+1}次尝试失败，正在重试...")
                continue
            return None
        except Exception as e:
            print(f"获取天气数据时出错: {e}")
            if attempt < max_retries - 1:
                print(f"第{attempt+1}次尝试失败，正在重试...")
                continue
            return None
    return None

@app.route("/cities", methods=["GET", "POST"])
@login_required
def cities():
    if request.method == "POST":
        if "add_city" in request.form:
            city_name = request.form["city_name"]
            if city_name:
                # 检查城市是否已存在
                existing_city = City.query.filter_by(user_id=current_user.id, name=city_name).first()
                if not existing_city:
                    new_city = City(user_id=current_user.id, name=city_name)
                    db.session.add(new_city)
                    db.session.commit()
                    flash("城市添加成功")
                else:
                    flash("城市已存在")
        elif "delete_city" in request.form:
            city_id = request.form["city_id"]
            city = City.query.filter_by(id=city_id, user_id=current_user.id).first()
            if city:
                db.session.delete(city)
                db.session.commit()
                flash("城市删除成功")
        elif "set_default" in request.form:
            city_id = request.form["city_id"]
            # 先将所有城市的is_default设置为False
            City.query.filter_by(user_id=current_user.id).update({"is_default": False})
            # 再将选中的城市设置为默认
            city = City.query.filter_by(id=city_id, user_id=current_user.id).first()
            if city:
                city.is_default = True
                db.session.commit()
                flash("默认城市设置成功")
    
    user_cities = City.query.filter_by(user_id=current_user.id).all()
    return render_template("cities.html", cities=user_cities, user=current_user)

@app.route("/history", methods=["GET", "POST"])
@login_required
def history():
    records = []
    stats = {}
    start_date = request.form.get("start_date")
    end_date = request.form.get("end_date")
    city = request.form.get("city")
    
    if request.method == "POST":
        try:
            query = Weather.query
            
            if start_date:
                start = datetime.strptime(start_date, "%Y-%m-%d")
                query = query.filter(Weather.date >= start)
            
            if end_date:
                end = datetime.strptime(end_date, "%Y-%m-%d")
                # 结束日期设置为当天的23:59:59
                end = end.replace(hour=23, minute=59, second=59)
                query = query.filter(Weather.date <= end)
            
            if city:
                query = query.filter(Weather.city == city)
            
            records = query.order_by(Weather.date.desc()).all()
            
            # 计算统计数据
            if records:
                temperatures = [r.temperature for r in records]
                humidities = [r.humidity for r in records]
                stats = {
                    "max_temp": max(temperatures),
                    "min_temp": min(temperatures),
                    "avg_temp": round(sum(temperatures) / len(temperatures), 2),
                    "avg_humidity": round(sum(humidities) / len(humidities), 1),
                    "record_count": len(records)
                }
        except Exception as e:
            print(f"查询历史数据失败: {e}")
            flash("查询历史数据失败")
    
    # 获取所有城市列表
    cities = Weather.query.distinct(Weather.city).all()
    city_list = [c.city for c in cities]
    
    return render_template("history.html", records=records, stats=stats, city_list=city_list, user=current_user)

@app.route("/warnings", methods=["GET", "POST"])
@login_required
def warnings():
    if request.method == "POST":
        if "mark_read" in request.form:
            warning_id = request.form["warning_id"]
            warning = Warning.query.get(warning_id)
            if warning:
                warning.is_read = True
                db.session.commit()
                flash("预警已标记为已读")
        elif "mark_all_read" in request.form:
            Warning.query.update({"is_read": True})
            db.session.commit()
            flash("所有预警已标记为已读")
    
    # 获取所有预警
    all_warnings = Warning.query.order_by(Warning.date.desc()).all()
    # 获取未读预警数量
    unread_count = Warning.query.filter_by(is_read=False).count()
    
    return render_template("warnings.html", warnings=all_warnings, unread_count=unread_count, user=current_user)

@app.route("/realtime", methods=["GET", "POST"])
@login_required
def realtime():
    weather = None
    warnings = []
    user_cities = City.query.filter_by(user_id=current_user.id).all()
    
    if request.method == "POST":
        city = request.form["city"]
        weather_data = get_weather_from_api(city)
        if weather_data:
            weather = weather_data
            # 检测天气异常
            warnings = check_weather_anomalies(
                weather_data["city"],
                weather_data["temperature"],
                weather_data["humidity"]
            )
            # 保存到数据库
            try:
                new_weather = Weather(
                    city=weather_data["city"],
                    temperature=weather_data["temperature"],
                    humidity=weather_data["humidity"],
                    description=weather_data["description"],
                    wind_speed=weather_data["wind_speed"],
                    wind_dir=weather_data["wind_dir"],
                    visibility=weather_data["visibility"],
                    pressure=weather_data["pressure"],
                    feels_like=weather_data["feels_like"]
                )
                db.session.add(new_weather)
                db.session.commit()
                flash("天气数据已保存到数据库")
                # 显示预警信息
                if warnings:
                    for warning in warnings:
                        flash(f"⚠️ {warning['message']} (严重程度: {warning['severity']})")
            except Exception as e:
                db.session.rollback()
                print(f"数据库保存失败: {e}")
                flash("天气数据保存失败")
        else:
            flash("获取天气数据失败")
    return render_template("realtime.html", weather=weather, user=current_user, cities=user_cities)

@app.route("/forecast", methods=["GET", "POST"])
@login_required
def forecast():
    forecast_data = None
    city = None
    
    if request.method == "POST":
        city = request.form["city"]
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # 使用wttr.in API获取未来天气预报
                url = f"https://wttr.in/{city}?format=j1"
                response = requests.get(url, timeout=10)
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        if "weather" in data:
                            # 提取未来7天的预报数据
                            forecast_data = []
                            for day in data["weather"]:
                                day_data = {
                                    "date": day["date"],
                                    "max_temp": day["maxtempC"],
                                    "min_temp": day["mintempC"],
                                    "avg_temp": day["avgtempC"],
                                    "description": day["hourly"][0]["weatherDesc"][0]["value"],
                                    "humidity": day["hourly"][0]["humidity"]
                                }
                                forecast_data.append(day_data)
                            break
                    except json.JSONDecodeError as e:
                        print(f"JSON解析错误: {e}")
                        if attempt < max_retries - 1:
                            continue
                else:
                    print(f"API请求失败: {response.status_code}")
                    if attempt < max_retries - 1:
                        continue
            except requests.RequestException as e:
                print(f"网络请求错误: {e}")
                if attempt < max_retries - 1:
                    continue
    
    return render_template("forecast.html", forecast_data=forecast_data, city=city, user=current_user)

@app.route("/air-quality", methods=["GET", "POST"])
@login_required
def air_quality():
    air_quality_data = None
    city = None
    
    if request.method == "POST":
        city = request.form["city"]
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # 使用wttr.in API获取天气数据，包含空气质量信息
                url = f"https://wttr.in/{city}?format=j1"
                response = requests.get(url, timeout=10)
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        if "current_condition" in data and len(data["current_condition"]) > 0:
                            current = data["current_condition"][0]
                            # 模拟空气质量数据（因为wttr.in可能不直接提供AQI）
                            # 实际项目中可以使用专门的空气质量API
                            air_quality_data = {
                                "city": city,
                                "aqi": int(current.get("air_quality", {}).get("us-epa-index", 5)),
                                "pm25": float(current.get("air_quality", {}).get("pm25", 25)),
                                "pm10": float(current.get("air_quality", {}).get("pm10", 40)),
                                "o3": float(current.get("air_quality", {}).get("o3", 60)),
                                "no2": float(current.get("air_quality", {}).get("no2", 30)),
                                "so2": float(current.get("air_quality", {}).get("so2", 10)),
                                "co": float(current.get("air_quality", {}).get("co", 0.8))
                            }
                            # 如果wttr.in没有提供空气质量数据，使用模拟数据
                            if air_quality_data["aqi"] == 5:
                                import random
                                air_quality_data = {
                                    "city": city,
                                    "aqi": random.randint(20, 150),
                                    "pm25": random.uniform(10, 80),
                                    "pm10": random.uniform(20, 100),
                                    "o3": random.uniform(30, 100),
                                    "no2": random.uniform(10, 50),
                                    "so2": random.uniform(5, 20),
                                    "co": random.uniform(0.5, 1.5)
                                }
                            break
                    except json.JSONDecodeError as e:
                        print(f"JSON解析错误: {e}")
                        if attempt < max_retries - 1:
                            continue
                else:
                    print(f"API请求失败: {response.status_code}")
                    if attempt < max_retries - 1:
                        continue
            except requests.RequestException as e:
                print(f"网络请求错误: {e}")
                if attempt < max_retries - 1:
                    continue
    
    return render_template("air_quality.html", air_quality_data=air_quality_data, city=city, user=current_user)

@app.route("/life-index", methods=["GET", "POST"])
@login_required
def life_index():
    life_index_data = None
    city = None
    
    if request.method == "POST":
        city = request.form["city"]
        # 获取天气数据
        weather_data = get_weather_from_api(city)
        
        if weather_data:
            # 基于天气数据生成生活指数
            temperature = weather_data["temperature"]
            humidity = weather_data["humidity"]
            
            # 穿衣指数
            if temperature >= 30:
                clothing = {"level": "炎热", "advice": "建议穿着短袖、短裤等清凉透气的衣物，外出时注意防晒。"}
            elif temperature >= 20:
                clothing = {"level": "舒适", "advice": "建议穿着短袖、薄长裤等舒适的衣物。"}
            elif temperature >= 10:
                clothing = {"level": "较凉", "advice": "建议穿着长袖衬衫、薄外套等保暖衣物。"}
            else:
                clothing = {"level": "寒冷", "advice": "建议穿着厚外套、毛衣、围巾等保暖衣物。"}
            
            # 运动指数
            if temperature >= 35 or temperature <= 0:
                sport = {"level": "不宜", "advice": "天气过于极端，不建议进行户外运动。"}
            elif humidity >= 80:
                sport = {"level": "较不宜", "advice": "湿度较大，建议减少户外运动时间。"}
            else:
                sport = {"level": "适宜", "advice": "天气适宜进行户外运动，建议适当锻炼。"}
            
            # 紫外线指数
            if temperature >= 25 and weather_data["description"].find("晴") != -1:
                uv = {"level": "强", "advice": "紫外线强，外出时请涂抹防晒霜，戴遮阳帽。"}
            elif temperature >= 20 and weather_data["description"].find("晴") != -1:
                uv = {"level": "中等", "advice": "紫外线中等，建议涂抹防晒霜。"}
            else:
                uv = {"level": "弱", "advice": "紫外线弱，无需特别防护。"}
            
            # 感冒指数
            if temperature <= 5:
                cold = {"level": "易发", "advice": "天气寒冷，易感冒，建议注意保暖。"}
            elif temperature >= 30 and humidity >= 80:
                cold = {"level": "易发", "advice": "天气闷热，易感冒，建议保持室内通风。"}
            else:
                cold = {"level": "少发", "advice": "天气适宜，感冒几率较低。"}
            
            # 洗车指数
            if weather_data["description"].find("雨") != -1 or weather_data["description"].find("雪") != -1:
                car_wash = {"level": "不宜", "advice": "天气不佳，不适宜洗车。"}
            else:
                car_wash = {"level": "适宜", "advice": "天气良好，适宜洗车。"}
            
            life_index_data = {
                "city": city,
                "weather": weather_data,
                "clothing": clothing,
                "sport": sport,
                "uv": uv,
                "cold": cold,
                "car_wash": car_wash
            }
    
    return render_template("life_index.html", life_index_data=life_index_data, city=city, user=current_user)

@app.route("/admin")
@admin_required
def admin():
    # 获取所有用户
    users = User.query.all()
    # 获取所有天气数据（最近100条）
    weather_data = Weather.query.order_by(Weather.date.desc()).limit(100).all()
    
    return render_template("admin.html", users=users, weather_data=weather_data, user=current_user)

@app.route("/admin/user/<int:user_id>/delete", methods=["POST"])
@admin_required
def delete_user(user_id):
    user = User.query.get(user_id)
    if user:
        # 防止删除自己
        if user.id == current_user.id:
            flash("不能删除自己的账户")
        else:
            db.session.delete(user)
            db.session.commit()
            flash("用户删除成功")
    else:
        flash("用户不存在")
    return redirect(url_for("admin"))

@app.route("/admin/weather/<int:weather_id>/delete", methods=["POST"])
@admin_required
def delete_weather(weather_id):
    weather = Weather.query.get(weather_id)
    if weather:
        db.session.delete(weather)
        db.session.commit()
        flash("天气数据删除成功")
    else:
        flash("天气数据不存在")
    return redirect(url_for("admin"))

def get_city_weather_from_api(city_name):
    """从wttr.in API获取城市天气数据"""
    try:
        url = f"https://wttr.in/{city_name}?format=j1"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            # 获取当前天气数据
            current = data.get("current_condition", [{}])[0]
            
            # 获取温度
            temp_c = float(current.get("temp_C", 20))
            
            # 获取湿度
            humidity = float(current.get("humidity", 50))
            
            # 获取天气描述
            description = current.get("weatherDesc", [{}])[0].get("value", "未知")
            
            # 获取AQI（wttr.in可能没有直接提供AQI，我们使用默认值或模拟）
            aqi = int(current.get("air_quality", {}).get("us-epa-index", 50))
            if aqi == 50:  # 如果AQI为默认值，说明API没有提供
                aqi = 60  # 使用中等偏下的AQI值
            
            return {
                'temperature': temp_c,
                'humidity': humidity,
                'description': description,
                'aqi': aqi
            }
    except Exception as e:
        print(f"获取{city_name}天气数据失败: {e}")
    
    return None

@app.route("/national-weather")
@login_required
def national_weather():
    # 获取所有城市的最新天气数据
    cities_data = []
    # 使用字典去重，确保每个城市只出现一次
    city_dict = {}
    
    # 默认城市列表，用于从API获取数据
    default_cities = [
        '北京', '上海', '广州', '深圳', '杭州', '成都', '武汉', '西安',
        '天津', '南京', '重庆', '郑州', '长沙', '沈阳', '青岛', '宁波',
        '昆明', '福州', '厦门', '济南', '大连', '合肥', '南宁', '贵阳',
        '石家庄', '太原', '哈尔滨', '长春', '南昌', '兰州', '乌鲁木齐'
    ]
    
    # 从API获取每个城市的实时数据
    for city in default_cities:
        weather_data = get_city_weather_from_api(city)
        
        if weather_data:
            # 计算宜居指数
            temp_score = max(0, 100 - abs(weather_data['temperature'] - 22.5) * 10)
            humidity_score = max(0, 100 - abs(weather_data['humidity'] - 50) * 2)
            aqi_score = max(0, 100 - weather_data['aqi'] * 0.5)
            livability_score = (temp_score + humidity_score + aqi_score) / 3
            
            city_dict[city] = {
                'city': city,
                'temperature': weather_data['temperature'],
                'humidity': weather_data['humidity'],
                'description': weather_data['description'],
                'aqi': weather_data['aqi'],
                'livability_score': round(livability_score, 2),
                'date': datetime.now()
            }
    
    # 如果API获取失败，尝试使用数据库中的数据
    if not city_dict:
        weather_records = Weather.query.order_by(Weather.city, Weather.date.desc()).all()
        
        for record in weather_records:
            if record.city not in city_dict:
                # 使用数据库中的数据
                temp_score = max(0, 100 - abs(record.temperature - 22.5) * 10)
                humidity_score = max(0, 100 - abs(record.humidity - 50) * 2)
                aqi_score = max(0, 100 - (record.aqi or 50) * 0.5)
                livability_score = (temp_score + humidity_score + aqi_score) / 3
                
                city_dict[record.city] = {
                    'city': record.city,
                    'temperature': record.temperature,
                    'humidity': record.humidity,
                    'description': record.description,
                    'aqi': record.aqi or 50,
                    'livability_score': round(livability_score, 2),
                    'date': record.date
                }
    
    # 将字典值转换为列表
    cities_data = list(city_dict.values())
    
    # 中国主要省份的省会城市
    provincial_capitals = [
        '北京', '上海', '广州', '成都', '武汉', '西安', '南京', '重庆',
        '杭州', '济南', '哈尔滨', '长春', '沈阳', '长沙', '福州', '南昌',
        '昆明', '南宁', '贵阳', '太原', '石家庄', '合肥', '西宁', '银川',
        '乌鲁木齐', '拉萨', '海口', '呼和浩特'
    ]
    
    # 按温度排序（从高到低）
    temperature_ranking = sorted(cities_data, key=lambda x: x['temperature'], reverse=True)
    
    # 过滤出省会城市的空气质量排名
    air_quality_ranking = []
    for city in provincial_capitals:
        for data in cities_data:
            if data['city'] == city:
                air_quality_ranking.append(data)
                break
    # 按AQI从低到高排序
    air_quality_ranking = sorted(air_quality_ranking, key=lambda x: x['aqi'])
    
    # 按宜居指数排序（从高到低）
    livability_ranking = sorted(cities_data, key=lambda x: x['livability_score'], reverse=True)
    
    # 简单线性回归模型预测短期温度趋势
    def simple_linear_regression(x, y):
        """简单线性回归模型"""
        n = len(x)
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(xi * yi for xi, yi in zip(x, y))
        sum_x2 = sum(xi**2 for xi in x)
        
        # 计算斜率和截距
        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x**2)
        intercept = (sum_y - slope * sum_x) / n
        
        return slope, intercept
    
    # 生成温度预测数据
    temperature_prediction = {}
    for city in provincial_capitals[:5]:  # 取前5个省会城市进行预测
        # 模拟历史温度数据（最近7天）
        import random
        historical_temps = []
        for i in range(7):
            base_temp = random.uniform(15, 30)
            # 添加一些随机波动
            temp = base_temp + random.uniform(-2, 2)
            historical_temps.append(round(temp, 1))
        
        # 准备回归数据
        x = list(range(7))  # 时间点（0-6）
        y = historical_temps  # 历史温度
        
        # 训练模型
        slope, intercept = simple_linear_regression(x, y)
        
        # 预测未来3天的温度
        predictions = []
        for i in range(7, 10):  # 未来3天（7-9）
            pred_temp = slope * i + intercept
            predictions.append(round(pred_temp, 1))
        
        temperature_prediction[city] = {
            'historical': historical_temps,
            'predictions': predictions
        }
    
    # 获取降雨数据
    rainfall_data = []
    
    for city in provincial_capitals:
        weather_data = get_city_weather_from_api(city)
        if weather_data:
            # wttr.in API不直接提供降雨量，我们通过天气描述和湿度来估算
            rainfall = 0
            if '雨' in weather_data['description']:
                rainfall = weather_data['humidity'] / 3  # 估算降雨量
            rainfall_data.append({
                'name': city,
                'value': round(rainfall, 1)
            })
        else:
            # 如果API调用失败，设置默认值
            rainfall_data.append({
                'name': city,
                'value': 0
            })
    
    return render_template("national_weather.html", 
                           temperature_ranking=temperature_ranking,
                           air_quality_ranking=air_quality_ranking,
                           livability_ranking=livability_ranking,
                           rainfall_data=rainfall_data,
                           temperature_prediction=temperature_prediction,
                           user=current_user)

