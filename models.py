user_schema = {
    "_id": ObjectId,
    "username": str,
    "password": str,
    "email": str,
    "full_name": str,
    "phone": str,
    "role": {
        "role_id": ObjectId,
        "level": int,
        "position": str,
        "department": str,
        "is_admin": bool,
        "name": str
    },
    "organization": {
        "tinh_id": ObjectId,
        "huyen_id": ObjectId,
        "xa_id": ObjectId
    },
    "created_by": ObjectId,
    "status": str,
    "created_at": datetime,
    "updated_at": datetime
}

organization_schema = {
    "_id": ObjectId,
    "name": str,
    "type": str,  # "tinh", "huyen", "xa"
    "parent_id": ObjectId,  # ID của đơn vị cấp trên
    "code": str,  # Mã đơn vị
    "address": str,
    "phone": str,
    "email": str,
    "created_at": datetime,
    "updated_at": datetime
}

task_schema = {
    "_id": ObjectId,
    "title": str,
    "description": str,
    "project_id": ObjectId,  # ID của dự án (nếu có)
    "creator_id": ObjectId,  # ID người tạo
    "assignee_id": ObjectId,  # ID người được giao
    "organization": {
        "tinh_id": ObjectId,
        "huyen_id": ObjectId,
        "xa_id": ObjectId
    },
    "status": str,  # "pending", "in_progress", "completed", "cancelled"
    "progress": int,  # Tiến độ (0-100)
    "priority": str,  # "low", "medium", "high"
    "start_date": datetime,
    "due_date": datetime,
    "completed_date": datetime,
    "created_at": datetime,
    "updated_at": datetime
}

project_schema = {
    "_id": ObjectId,
    "name": str,
    "description": str,
    "manager_id": ObjectId,  # ID người quản lý dự án
    "organization": {
        "tinh_id": ObjectId,
        "huyen_id": ObjectId,
        "xa_id": ObjectId
    },
    "status": str,  # "active", "completed", "cancelled"
    "start_date": datetime,
    "end_date": datetime,
    "created_at": datetime,
    "updated_at": datetime
}

proposal_schema = {
    "_id": ObjectId,
    "title": str,
    "content": str,
    "type": str,  # "kinh_phi", "trang_thiet_bi", "khac"
    "creator_id": ObjectId,
    "department": str,  # Phòng ban đề xuất
    "status": str,  # "pending", "approved", "rejected", "reviewing"
    "approver_id": ObjectId,  # ID người phê duyệt
    "approval_note": str,
    "amount": float,  # Số tiền (nếu là đề xuất kinh phí)
    "attachments": [str],  # Danh sách đường dẫn tệp đính kèm
    "created_at": datetime,
    "updated_at": datetime
}

department_schema = {
    "_id": ObjectId,
    "name": str,  # Tên phòng ban
    "code": str,  # Mã phòng ban
    "type": str,  # "thuong_truc", "tuyen_giao", "phong_trao", etc.
    "organization_id": ObjectId,  # ID của tỉnh
    "leader_id": ObjectId,  # ID trưởng ban
    "deputy_ids": [ObjectId],  # Danh sách ID phó ban
    "created_at": datetime,
    "updated_at": datetime
}

roles_schema = {
    "_id": ObjectId,
    "name": str,
    "level": int,  # 1: Admin, 2: Tỉnh, 3: Huyện, 4: Xã
    "position": str,  # Chức vụ cụ thể
    "can_create": [str],  # Danh sách role có thể tạo
    "can_approve": [str], # Danh sách role có thể duyệt
    "created_at": datetime,
    "updated_at": datetime
}

# Danh sách vai trò mặc định
default_roles = [
    {
        "name": "admin",
        "level": 1,
        "position": "Admin",
        "can_create": ["quan_tri_tinh", "quan_tri_huyen", "quan_tri_xa"],
        "can_approve": ["all"]
    },
    {
        "name": "quan_tri_tinh", 
        "level": 2,
        "position": "Quản trị tỉnh",
        "can_create": ["ban_thuong_truc", "quan_tri_huyen", "nhan_vien_huyen"],
        "can_approve": ["quan_tri_huyen"]
    },
    {
        "name": "ban_thuong_truc",
        "level": 2,
        "position": "Ban thường trực",
        "can_create": ["ban_khac", "chuyen_vien_btv"],
        "can_approve": ["ban_khac", "chuyen_vien_btv"]
    },
    {
        "name": "ban_khac",
        "level": 2,
        "position": "Ban khác",
        "can_create": ["chuyen_vien_ban_khac"],
        "can_approve": ["chuyen_vien_ban_khac"]
    },
    {
        "name": "quan_tri_huyen",
        "level": 3,
        "position": "Quản trị huyện", 
        "can_create": ["quan_tri_xa", "nhan_vien_huyen", "doan_vien_xa"],
        "can_approve": ["quan_tri_xa"]
    },
    {
        "name": "quan_tri_xa",
        "level": 4,
        "position": "Quản trị xã",
        "can_create": ["doan_vien_xa"],
        "can_approve": ["doan_vien_xa"]
    }
]

# Tạo indexes
db.users.create_index([("username", 1)], unique=True)
db.users.create_index([("email", 1)], unique=True)
db.organizations.create_index([("code", 1)], unique=True)
db.tasks.create_index([("creator_id", 1)])
db.tasks.create_index([("assignee_id", 1)])
db.proposals.create_index([("creator_id", 1)])
db.proposals.create_index([("status", 1)])

permission_schema = {
    "_id": ObjectId,
    "code": str,  # Mã quyền
    "name": str,  # Tên quyền
    "description": str,
    "scope": str,  # Phạm vi: "system", "tinh", "huyen", "xa"
    "created_at": datetime,
    "updated_at": datetime
}

# Danh sách quyền mặc định
default_permissions = [
    {
        "code": "all",
        "name": "Toàn quyền",
        "scope": "system"
    },
    {
        "code": "manage_tinh",
        "name": "Quản lý cấp tỉnh",
        "scope": "tinh"
    },
    {
        "code": "manage_huyen",
        "name": "Quản lý cấp huyện",
        "scope": "huyen"
    },
    {
        "code": "manage_xa",
        "name": "Quản lý cấp xã",
        "scope": "xa"
    },
    # Quản lý công việc
    {"code": "create_project", "name": "Tạo dự án"},
    {"code": "assign_task", "name": "Giao việc"},
    {"code": "view_tasks", "name": "Xem danh sách công việc"},
    {"code": "update_progress", "name": "Cập nhật tiến độ"},
    
    # Hạn mục
    {"code": "approve_category", "name": "Phê duyệt hạn mục"},
    {"code": "create_category", "name": "Tạo hạn mục"},
    
    # Lịch công tác
    {"code": "create_schedule", "name": "Đăng ký lịch công tác"},
    {"code": "approve_schedule", "name": "Phê duyệt lịch công tác"},
    {"code": "view_schedules", "name": "Xem lịch công tác"},
    
    # Tìm kiếm
    {"code": "search_subordinates", "name": "Tra cứu thông tin cấp dưới"},
    {"code": "search_all", "name": "Xem toàn bộ thông tin hệ thống"}
]

default_admin = {
    "username": "superadmin",
    "password": "hashed_password",  # Cần hash password trước khi lưu
    "email": "admin@system.com",
    "full_name": "System Administrator",
    "role": {
        "role_id": ObjectId("super_admin_role_id"),
        "level": 1,
        "position": "Super Administrator",
        "is_admin": True
    },
    "organization": None,  # Admin cao nhất không thuộc tổ chức nào
    "status": "active",
    "created_at": datetime.now(),
    "updated_at": datetime.now()
}

permission_requests = {
    "user_id": ObjectId,  # ID người yêu cầu
    "current_role": {     # Role hiện tại
        "level": int,
        "position": str
    },
    "requested_role": {   # Role yêu cầu
        "level": int, 
        "position": str
    },
    "status": str,        # pending/approved/rejected
    "approvers": [{       # Danh sách người cần duyệt
        "user_id": ObjectId,
        "role_level": int,
        "approved": bool
    }],
    "created_at": datetime,
    "updated_at": datetime,
    "approved_at": datetime
}

# Collection projects (dự án)
projects = {
    "_id": ObjectId,
    "name": str,
    "description": str,
    "created_by": ObjectId,  # user_id người tạo
    "created_at": datetime,
    "status": str,  # active/completed/cancelled
    "members": [{
        "user_id": ObjectId,
        "role": str  # owner/member
    }]
}

# Collection tasks (công việc)
tasks = {
    "_id": ObjectId,
    "title": str,
    "description": str,
    "status": str,  # "waiting", "in_progress", "pending_approval", "completed", "paused"
    "priority": str,  # "low", "medium", "high"
    "created_by": ObjectId,  # user_id người tạo
    "assigned_to": ObjectId,  # user_id người được giao
    "organization_level": str,  # "tinh", "huyen", "xa" - cấp của task
    "organization_id": ObjectId,  # ID của đơn vị
    "deadline": datetime,
    "created_at": datetime,
    "updated_at": datetime
}

# Collection categories (hạn mục)
categories = {
    "_id": ObjectId,
    "name": str,
    "description": str,
    "created_by": ObjectId,
    "approved_by": ObjectId,
    "status": str,  # pending/approved/rejected
    "created_at": datetime,
    "updated_at": datetime
}

# Collection schedules (lịch công tác) 
schedules = {
    "_id": ObjectId,
    "title": str,
    "description": str,
    "start_time": datetime,
    "end_time": datetime,
    "location": str,
    "created_by": ObjectId,
    "approved_by": ObjectId,
    "status": str,  # pending/approved/rejected
    "created_at": datetime,
    "updated_at": datetime,
    "participants": [ObjectId]  # Danh sách user_id tham gia
}

def initialize_default_data(db):
    # Tạo roles mặc định
    roles_collection = db.roles
    for role in default_roles:
        roles_collection.update_one(
            {"name": role["name"]},
            {"$set": role},
            upsert=True
        )
    
    # Tạo permissions mặc định
    permissions_collection = db.permissions
    for permission in default_permissions:
        permissions_collection.update_one(
            {"code": permission["code"]},
            {"$set": permission},
            upsert=True
        )
    
    # Tạo admin mặc định nếu chưa tồn tại
    users_collection = db.users
    if not users_collection.find_one({"username": "superadmin"}):
        users_collection.insert_one(default_admin) 