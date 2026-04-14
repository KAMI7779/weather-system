from flask import Flask, render_template, redirect, url_for, request, flash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from app.models import db, User, Weather
from app.analysis import basic_stats, temp_trend, humidity_trend, combined_trend
import requests
import json

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
    return render_template("index.html", stats=basic_stats(), user=current_user)

@app.route("/chart")
@login_required
def chart():
    temp_trend()
    return render_template("chart.html", user=current_user)

@app.route("/humidity-chart")
@login_required
def humidity_chart():
    humidity_trend()
    return render_template("humidity_chart.html", user=current_user)

@app.route("/combined-chart")
@login_required
def combined_chart():
    combined_trend()
    return render_template("combined_chart.html", user=current_user)

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
                            "description": data["current_condition"][0]["weatherDesc"][0]["value"]
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
                    description=weather_data["description"]
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

