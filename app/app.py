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
    app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:123456@localhost/weather_system'
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

def get_weather_from_api(city):
    try:
        # 使用wttr.in API（免费且不需要API密钥）
        url = f"https://wttr.in/{city}?format=j1"
        response = requests.get(url, timeout=10)
        print(f"API请求URL: {url}")
        print(f"API请求状态码: {response.status_code}")
        print(f"API响应内容: {response.text}")
        
        if response.status_code == 200:
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
                print("API响应格式不正确")
                return None
        else:
            print(f"API请求失败: {response.status_code}")
            return None
    except Exception as e:
        print(f"获取天气数据时出错: {e}")
        return None

@app.route("/realtime", methods=["GET", "POST"])
@login_required
def realtime():
    weather = None
    if request.method == "POST":
        city = request.form["city"]
        weather_data = get_weather_from_api(city)
        if weather_data:
            weather = weather_data
            # 保存到数据库
            new_weather = Weather(
                city=weather_data["city"],
                temperature=weather_data["temperature"],
                humidity=weather_data["humidity"],
                description=weather_data["description"]
            )
            db.session.add(new_weather)
            db.session.commit()
            flash("天气数据已保存到数据库")
        else:
            flash("获取天气数据失败")
    return render_template("realtime.html", weather=weather, user=current_user)

