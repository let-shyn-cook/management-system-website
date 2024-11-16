from pymongo import MongoClient
from werkzeug.security import generate_password_hash
from datetime import datetime
from bson import ObjectId

def init_database():
    client = MongoClient('mongodb://localhost:27017/')
    db = client['doan_thanh_nien']
    
    # Tạo admin mặc định nếu chưa tồn tại
    if not db.users.find_one({"username": "superadmin"}):
        admin_user = {
            "username": "superadmin",
            "password": generate_password_hash("admin123"),
            "email": "admin@system.com",
            "full_name": "System Administrator",
            "role": {
                "level": 1,
                "position": "Super Administrator",
                "is_admin": True
            },
            "status": "active",
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        }
        db.users.insert_one(admin_user)
        print("Đã tạo tài khoản admin mặc định!")

if __name__ == "__main__":
    init_database() 