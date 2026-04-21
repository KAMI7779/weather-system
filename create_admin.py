from app.app import app, db
from app.models import User, WeatherStation, StationObservation, SatelliteImage, RadarEcho, NumericalForecast, DataSource, DataAccessLog, DataQuality, DataPreprocessing, WarningRule, WarningRecord, PushRecord

with app.app_context():
    # 删除所有表
    db.drop_all()
    # 重新创建表
    db.create_all()
    
    # 创建管理员账户
    admin_user = User(
        username='admin',
        email='admin@example.com',
        password='admin123',
        role='admin'
    )
    db.session.add(admin_user)
    
    # 创建普通用户账户
    user = User(
        username='user',
        email='user@example.com',
        password='user123',
        role='user'
    )
    db.session.add(user)
    
    db.session.commit()
    
    print("管理员账户创建成功！")
    print("用户名: admin")
    print("密码: admin123")
    print("\n普通用户账户也已创建！")
    print("用户名: user")
    print("密码: user123")