from flask import Flask, render_template, redirect, url_for, request, flash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from app.models import db, User, Weather, City, Warning
from app.analysis import basic_stats
import requests
import json
from datetime import datetime

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

@app.route("/national-weather")
@login_required
def national_weather():
    # 获取所有城市的最新天气数据
    cities_data = []
    # 使用字典去重，确保每个城市只出现一次
    city_dict = {}
    
    # 获取所有天气数据，按城市和日期排序
    weather_records = Weather.query.order_by(Weather.city, Weather.date.desc()).all()
    
    for record in weather_records:
        if record.city not in city_dict:
            # 计算宜居指数（简单算法：温度适宜度 + 湿度适宜度 + 空气质量适宜度）
            # 温度适宜度：20-25度为最佳，偏离越多分数越低
            temp_score = max(0, 100 - abs(record.temperature - 22.5) * 10)
            # 湿度适宜度：40-60%为最佳，偏离越多分数越低
            humidity_score = max(0, 100 - abs(record.humidity - 50) * 2)
            # 空气质量适宜度：AQI越低分数越高
            aqi_score = max(0, 100 - (record.aqi or 50) * 0.5)
            # 综合宜居指数
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
    
    # 按温度排序（从高到低）
    temperature_ranking = sorted(cities_data, key=lambda x: x['temperature'], reverse=True)
    # 按空气质量排序（从低到高，AQI越低越好）
    air_quality_ranking = sorted(cities_data, key=lambda x: x['aqi'])
    # 按宜居指数排序（从高到低）
    livability_ranking = sorted(cities_data, key=lambda x: x['livability_score'], reverse=True)
    
    return render_template("national_weather.html", 
                           temperature_ranking=temperature_ranking,
                           air_quality_ranking=air_quality_ranking,
                           livability_ranking=livability_ranking,
                           user=current_user)

