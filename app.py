from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime, timedelta
from bson import ObjectId
from werkzeug.utils import secure_filename
import os
from bs4 import BeautifulSoup
import requests
import threading
import time

app = Flask(__name__)
app.secret_key = 'shynlhu'  

# Cấu hình upload folder
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Tạo thư mục nếu chưa tồn tại
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Kết nối MongoDB
client = MongoClient('mongodb://localhost:27017/')
db = client['doan_thanh_nien']

# Decorator kiểm tra đăng nhập
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
@app.route('/dashboard')
@login_required
def dashboard():
    current_user = db.users.find_one({'_id': ObjectId(session['user_id'])})
    
    # Đếm số lượng công việc theo trạng thái và user
    waiting_count = db.tasks.count_documents({
        '$or': [
            {'assigned_by': current_user['_id']},
            {'assigned_to': current_user['_id']}
        ],
        'status': 'waiting'
    })
    
    in_progress_count = db.tasks.count_documents({
        '$or': [
            {'assigned_by': current_user['_id']},
            {'assigned_to': current_user['_id']}
        ],
        'status': 'in_progress'
    })
    
    completed_count = db.tasks.count_documents({
        '$or': [
            {'assigned_by': current_user['_id']},
            {'assigned_to': current_user['_id']}
        ],
        'status': 'completed'
    })
    
    # Đếm số lượng người dùng (chỉ cho admin)
    total_users = 0
    active_users = 0
    pending_users = 0
    if current_user.get('role') and current_user['role'].get('level') == 1:
        total_users = db.users.count_documents({})
        active_users = db.users.count_documents({'status': 'active'})
        pending_users = db.users.count_documents({'status': 'pending'})
    
    # Lấy thống kê công việc theo tháng
    now = datetime.now()
    start_of_year = datetime(now.year, 1, 1)
    
    pipeline = [
        {
            '$match': {
                '$or': [
                    {'created_by': current_user['_id']},
                    {'assigned_to': current_user['_id']}
                ],
                'created_at': {'$gte': start_of_year}
            }
        },
        {
            '$group': {
                '_id': {'$month': '$created_at'},
                'total': {'$sum': 1},
                'completed': {
                    '$sum': {'$cond': [{'$eq': ['$status', 'completed']}, 1, 0]}
                }
            }
        },
        {'$sort': {'_id': 1}}
    ]
    
    monthly_stats = list(db.tasks.aggregate(pipeline))
    
    # Lấy thống kê thời gian hoạt động theo ngày
    activity_stats = list(db.activity_logs.aggregate([
        {
            '$match': {
                'user_id': current_user['_id'],
                'created_at': {'$gte': datetime.now() - timedelta(days=7)}
            }
        },
        {
            '$group': {
                '_id': {'$dateToString': {'format': '%Y-%m-%d', 'date': '$created_at'}},
                'count': {'$sum': 1}
            }
        },
        {'$sort': {'_id': 1}}
    ]))

    return render_template('dashboard.html',
                         user=current_user,
                         monthly_stats=monthly_stats,
                         activity_stats=activity_stats,
                         waiting_count=waiting_count,
                         in_progress_count=in_progress_count, 
                         completed_count=completed_count,
                         total_users=total_users,
                         active_users=active_users,
                         pending_users=pending_users)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = db.users.find_one({'username': username})
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = str(user['_id'])
            session['role'] = user['role']
            flash('Đăng nhập thành công!', 'success')
            return redirect(url_for('dashboard'))
        
        flash('Tên đăng nhập hoặc mật khẩu không đúng!', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/users')
@login_required
def list_users():
    user = db.users.find_one({'_id': ObjectId(session['user_id'])})
    if user['role']['level'] != 1:
        flash('Bạn không có quyền truy cập!', 'error')
        return redirect(url_for('dashboard'))
    
    # Xử lý tìm kiếm
    search = request.args.get('search', '')
    
    # Xử lý phân trang
    page = int(request.args.get('page', 1))
    per_page = 10
    skip = (page - 1) * per_page
    
    # Query với điều kiện tìm kiếm và trạng thái
    query = {}
    if search:
        query['$or'] = [
            {'full_name': {'$regex': search, '$options': 'i'}},
            {'username': {'$regex': search, '$options': 'i'}},
            {'email': {'$regex': search, '$options': 'i'}}
        ]
    
    # Thêm filter theo trạng thái
    status = request.args.get('status', '')
    if status:
        query['status'] = status
    
    # Đếm tổng số bản ghi
    total_users = db.users.count_documents(query)
    total_pages = (total_users + per_page - 1) // per_page
    
    # Lấy danh sách người dùng theo trang
    users = list(db.users.find(query).skip(skip).limit(per_page))
    
    return render_template('users/list.html', 
                         users=users,
                         user=user,
                         current_page=page,
                         total_pages=total_pages,
                         search=search)

@app.route('/users/create', methods=['GET', 'POST'])
@login_required
def create_user():
    current_user = db.users.find_one({'_id': ObjectId(session['user_id'])})
    
    if current_user['role']['level'] != 1:
        flash('Bạn không có quyền tạo tài khoản!', 'error')
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        email = request.form.get('email')
        full_name = request.form.get('full_name')
        role_name = request.form.get('role_name')
        
        # Kiểm tra username đã tồn tại
        if db.users.find_one({'username': username}):
            flash('Tên đăng nhập đã tồn tại!', 'error')
            return redirect(url_for('create_user'))
            
        # Xác định thông tin role
        role_info = {
            'quan_tri_tinh': {'level': 2, 'position': 'Quản trị tỉnh'},
            'quan_tri_huyen': {'level': 3, 'position': 'Quản trị huyện'},
            'quan_tri_xa': {'level': 4, 'position': 'Quản trị xã'}
        }
        
        if role_name not in role_info:
            flash('Vai trò không hợp lệ!', 'error')
            return redirect(url_for('create_user'))
            
        new_user = {
            'username': username,
            'password': generate_password_hash(password),
            'email': email,
            'full_name': full_name,
            'role': {
                'name': role_name,
                'level': role_info[role_name]['level'],
                'position': role_info[role_name]['position']
            },
            'status': 'active',
            'created_at': datetime.now(),
            'updated_at': datetime.now()
        }
        
        db.users.insert_one(new_user)
        flash('Tạo người dùng thành công!', 'success')
        return redirect(url_for('list_users'))
    
    return render_template('users/create.html', user=current_user)

@app.route('/users/edit/<user_id>', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    current_user = db.users.find_one({'_id': ObjectId(session['user_id'])})
    
    # Kiểm tra quyền admin
    if current_user['role']['level'] != 1:
        flash('Bạn không có quyền chỉnh sửa tài khoản!', 'error')
        return redirect(url_for('dashboard'))
    
    # Lấy thông tin user cần sửa
    edit_user = db.users.find_one({'_id': ObjectId(user_id)})
    if not edit_user:
        flash('Không tìm thấy người dùng!', 'error')
        return redirect(url_for('list_users'))
        
    # Lấy danh sách roles có thể chọn dựa theo level của current user
    available_roles = []
    if current_user['role']['level'] == 1:  # Admin
        available_roles = [
            {'name': 'quan_tri_tinh', 'position': 'Quản trị tỉnh', 'level': 2},
            {'name': 'quan_tri_huyen', 'position': 'Quản trị huyện', 'level': 3},
            {'name': 'quan_tri_xa', 'position': 'Quản trị xã', 'level': 4}
        ]
    elif current_user['role']['level'] == 2:  # Quản trị tỉnh
        available_roles = [
            {'name': 'ban_thuong_truc', 'position': 'Ban thường trực', 'level': 2},
            {'name': 'quan_tri_huyen', 'position': 'Quản trị huyện', 'level': 3},
            {'name': 'nhan_vien_huyen', 'position': 'Nhân viên huyện', 'level': 3}
        ]
    
    if request.method == 'POST':
        # Cập nhật thông tin
        updates = {
            'email': request.form.get('email'),
            'full_name': request.form.get('full_name'),
            'role': {
                'name': request.form.get('role_name'),
                'level': int(request.form.get('role_level')),
                'position': request.form.get('position')
            },
            'status': request.form.get('status'),
            'updated_at': datetime.now()
        }
        
        # Nếu có nhập mt khẩu mi
        if request.form.get('password'):
            updates['password'] = generate_password_hash(request.form.get('password'))
        
        db.users.update_one(
            {'_id': ObjectId(user_id)},
            {'$set': updates}
        )
        flash('Cập nhật thành công!', 'success')
        return redirect(url_for('list_users'))
    
    return render_template('users/edit.html',
                         user=current_user,
                         edit_user=edit_user,
                         available_roles=available_roles)

@app.route('/users/delete/<user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if user_id == session['user_id']:
        flash('Không thể xóa tài khoản của chính mình!', 'error')
        return redirect(url_for('list_users'))
    
    db.users.delete_one({'_id': ObjectId(user_id)})
    flash('Xóa người dùng thành công!', 'success')
    return redirect(url_for('list_users'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        email = request.form.get('email')
        full_name = request.form.get('full_name')
        
        if db.users.find_one({'username': username}):
            flash('Tên đăng nhập đã tồn tại!', 'error')
            return redirect(url_for('register'))
            
        new_user = {
            'username': username,
            'password': generate_password_hash(password),
            'email': email,
            'full_name': full_name,
            'role': {
                'level': 5,
                'position': 'Người dùng mới'
            },
            'status': 'active',
            'created_at': datetime.now(),
            'updated_at': datetime.now()
        }
        
        db.users.insert_one(new_user)
        flash('Đăng ký thành công! Vui lòng yêu cầu nâng cấp quyền.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/request-role', methods=['GET', 'POST'])
@login_required
def request_role():
    current_user = db.users.find_one({'_id': ObjectId(session['user_id'])})
    
    # Kiểm tra quyền yêu cầu
    if current_user.get('role'):
        if current_user['role'].get('name') == 'admin':
            flash('Admin không cần yêu cầu nâng quyền!', 'error')
            return redirect(url_for('dashboard'))
            
    # Mapping role và người duyệt
    role_hierarchy = {
        'ban_thuong_truc': {
            'level': 2,
            'position': 'Ban thường trực',
            'approvers': ['quan_tri_tinh', 'admin']
        },
        'ban_khac': {
            'level': 2, 
            'position': 'Các ban khác',
            'approvers': ['ban_thuong_truc', 'admin']
        },
        'chuyen_vien_btv': {
            'level': 2,
            'position': 'Chuyên viên tỉnh',
            'approvers': ['ban_thuong_truc', 'admin']
        },
        'quan_tri_huyen': {
            'level': 3,
            'position': 'Quản trị huyện',
            'approvers': ['quan_tri_tinh', 'admin']
        },
        'nhan_vien_huyen': {
            'level': 3,
            'position': 'Nhân viên huyện',
            'approvers': ['quan_tri_huyen', 'quan_tri_tinh', 'admin']
        },
        'quan_tri_xa': {
            'level': 4,
            'position': 'Quản trị xã',
            'approvers': ['quan_tri_huyen', 'admin']
        },
        'doan_vien_xa': {
            'level': 4,
            'position': 'Đoàn viên xã',
            'approvers': ['quan_tri_xa', 'quan_tri_huyen', 'admin']
        }
    }

    # Lọc role có thể yêu cầu dựa theo role hiện tại
    available_roles = []
    current_role = current_user.get('role', {}).get('name', 'user')
    
    if current_role == 'user':
        # User mới có thể yêu cầu tất cả role cấp thấp
        available_roles = [r for r in role_hierarchy.keys() 
                         if role_hierarchy[r]['level'] >= 3]
    else:
        # Role hiện tại chỉ có thể yêu cầu role cao hơn
        available_roles = [r for r in role_hierarchy.keys()
                         if role_hierarchy[r]['level'] < current_user['role']['level']]

    if not available_roles:
        flash('Không có quyền phù hợp để yêu cầu!', 'error')
        return redirect(url_for('dashboard'))

    # Xử lý POST request
    if request.method == 'POST':
        requested_role = request.form.get('role_name')
        
        if requested_role not in role_hierarchy:
            flash('Vai trò không hợp lệ!', 'error')
            return redirect(url_for('request_role'))
            
        # Lấy danh sách người duyệt
        approvers = role_hierarchy[requested_role]['approvers']
            
        new_request = {
            'user_id': current_user['_id'],
            'current_role': current_user.get('role'),
            'requested_role': {
                'name': requested_role,
                'level': role_hierarchy[requested_role]['level'],
                'position': role_hierarchy[requested_role]['position'],
                'approvers': approvers
            },
            'status': 'pending',
            'created_at': datetime.now(),
            'updated_at': datetime.now()
        }
        
        db.role_requests.insert_one(new_request)
        flash('Gửi yêu cầu thành công!', 'success')
        return redirect(url_for('dashboard'))

    return render_template('request_role.html',
                         user=current_user,
                         role_hierarchy=role_hierarchy,
                         available_roles=available_roles)

@app.route('/role-requests')
@login_required
def list_role_requests():
    current_user = db.users.find_one({'_id': ObjectId(session['user_id'])})
    
    # Query role requests
    requests = db.role_requests.aggregate([
        {
            '$lookup': {
                'from': 'users',
                'localField': 'user_id',
                'foreignField': '_id',
                'as': 'user'
            }
        },
        {
            '$unwind': '$user'
        },
        {
            '$project': {
                'user_name': '$user.full_name',
                'current_role': '$user.role.position',  # Lấy tên hiển thị của role hiện tại
                'requested_role': '$requested_role.position',  # Lấy tên hiển thị của role yêu cầu
                'status': 1,
                'created_at': 1,
                '_id': 1
            }
        }
    ])
    
    return render_template('role_requests/list.html',
                         requests=list(requests),
                         user=current_user)

@app.route('/role-requests/<request_id>/approve', methods=['POST'])
@login_required
def approve_request(request_id):
    try:
        current_user = db.users.find_one({'_id': ObjectId(session['user_id'])})
        current_level = current_user['role']['level']

        request = db.role_requests.find_one({'_id': ObjectId(request_id)})
        if not request:
            flash('Không tìm thấy yêu cầu!', 'error')
            return redirect(url_for('list_role_requests'))

        # Admin có thể duyệt mọi yêu cầu
        if current_level == 1:
            # Cập nhật role cho user
            db.users.update_one(
                {'_id': request['user_id']},
                {'$set': {
                    'role': {
                        'name': request['requested_role']['name'],
                        'level': request['requested_role']['level'],
                        'position': request['requested_role']['position']
                    }
                }}
            )
            
            # Cập nhật trạng thái yêu cầu
            db.role_requests.update_one(
                {'_id': ObjectId(request_id)},
                {'$set': {
                    'status': 'approved',
                    'approved_at': datetime.now(),
                    'approved_by': current_user['_id']
                }}
            )
            
            flash('Đã duyệt yêu cầu!', 'success')
            return redirect(url_for('list_role_requests'))

        # Các role khác theo approval_rights
        approval_rights = {
            'quan_tri_tinh': ['ban_thuong_truc', 'quan_tri_huyen', 'nhan_vien_huyen'],
            'ban_thuong_truc': ['ban_khac', 'chuyen_vien_btv'],
            'ban_khac': ['chuyen_vien_ban_khac'],
            'quan_tri_huyen': ['quan_tri_xa', 'nhan_vien_huyen', 'doan_vien_xa'],
            'quan_tri_xa': ['doan_vien_xa']
        }

        current_role = current_user['role']['name']
        if current_role not in approval_rights:
            flash('Bạn không có quyền duyệt yêu cầu!', 'error')
            return redirect(url_for('list_role_requests'))

        requested_role = request['requested_role']['name']
        if requested_role not in approval_rights[current_role]:
            flash('Bạn không có quyền duyệt role này!', 'error')
            return redirect(url_for('list_role_requests'))

        # Cập nhật role và trạng thái
        db.users.update_one(
            {'_id': request['user_id']},
            {'$set': {
                'role': {
                    'name': request['requested_role']['name'],
                    'level': request['requested_role']['level'],
                    'position': request['requested_role']['position']
                }
            }}
        )

        db.role_requests.update_one(
            {'_id': ObjectId(request_id)},
            {'$set': {
                'status': 'approved',
                'approved_at': datetime.now(),
                'approved_by': current_user['_id']
            }}
        )

        flash('Đã duyệt yêu cầu!', 'success')
        return redirect(url_for('list_role_requests'))

    except Exception as e:
        print(f"Error in approve_request: {str(e)}")
        flash('Có lỗi xảy ra!', 'error')
        return redirect(url_for('list_role_requests'))

@app.route('/role-requests/<request_id>/reject', methods=['POST'])
@login_required
def reject_request(request_id):
    try:
        current_user = db.users.find_one({'_id': ObjectId(session['user_id'])})
        current_level = current_user['role']['level']

        request = db.role_requests.find_one({'_id': ObjectId(request_id)})
        if not request:
            flash('Không tìm thấy yêu cầu!', 'error')
            return redirect(url_for('list_role_requests'))

        # Admin có thể từ chối mọi yêu cầu
        if current_level == 1:
            db.role_requests.update_one(
                {'_id': ObjectId(request_id)},
                {'$set': {
                    'status': 'rejected',
                    'rejected_at': datetime.now(),
                    'rejected_by': current_user['_id']
                }}
            )
            
            flash('Đã từ chối yêu cầu!', 'success')
            return redirect(url_for('list_role_requests'))

        # Các role khác theo approval_rights
        approval_rights = {
            'quan_tri_tinh': ['ban_thuong_truc', 'quan_tri_huyen', 'nhan_vien_huyen'],
            'ban_thuong_truc': ['ban_khac', 'chuyen_vien_btv'],
            'ban_khac': ['chuyen_vien_ban_khac'],
            'quan_tri_huyen': ['quan_tri_xa', 'nhan_vien_huyen', 'doan_vien_xa'],
            'quan_tri_xa': ['doan_vien_xa']
        }

        current_role = current_user['role']['name']
        if current_role not in approval_rights:
            flash('Bạn không có quyền từ chối yêu cầu!', 'error')
            return redirect(url_for('list_role_requests'))

        requested_role = request['requested_role']['name']
        if requested_role not in approval_rights[current_role]:
            flash('Bạn không có quyền từ chối role này!', 'error')
            return redirect(url_for('list_role_requests'))

        # Cập nhật trạng thái
        db.role_requests.update_one(
            {'_id': ObjectId(request_id)},
            {'$set': {
                'status': 'rejected',
                'rejected_at': datetime.now(),
                'rejected_by': current_user['_id']
            }}
        )

        flash('Đã từ chối yêu cầu!', 'success')
        return redirect(url_for('list_role_requests'))

    except Exception as e:
        print(f"Error in reject_request: {str(e)}")
        flash('Có lỗi xảy ra!', 'error')
        return redirect(url_for('list_role_requests'))

# Quản lý dự án
@app.route('/projects')
@login_required
def list_projects():
    current_user = db.users.find_one({'_id': ObjectId(session['user_id'])})
    
    # Query dự án theo quyền
    if current_user['role']['name'] == 'quan_tri_tinh':
        projects = db.projects.find()
    else:
        projects = db.projects.find({
            '$or': [
                {'created_by': current_user['_id']},
                {'members.user_id': current_user['_id']}
            ]
        })
    
    projects_data = []
    for project in projects:
        creator = db.users.find_one({'_id': project['created_by']})
        project_data = {
            '_id': project['_id'],
            'name': project['name'],
            'description': project.get('description', ''),
            'status': project.get('status', 'active'),
            'created_by': creator.get('full_name', 'Unknown'),
            'created_at': project.get('created_at', datetime.now())
        }
        projects_data.append(project_data)
        
    return render_template('projects/list.html',
                         user=current_user,
                         projects=projects_data)

@app.route('/projects/create', methods=['GET', 'POST'])
@login_required
def create_project():
    current_user = db.users.find_one({'_id': ObjectId(session['user_id'])})
    
    if request.method == 'POST':
        project = {
            'name': request.form.get('name'),
            'description': request.form.get('description'),
            'created_by': current_user['_id'],
            'created_at': datetime.now(),
            'status': 'active',
            'members': [{
                'user_id': current_user['_id'],
                'role': 'owner'
            }]
        }
        
        db.projects.insert_one(project)
        flash('Tạo dự án thành công!', 'success')
        return redirect(url_for('list_projects'))
        
    return render_template('projects/create.html',
                         user=current_user)

# Quản lý công việc
@app.route('/tasks')
@login_required 
def list_tasks():
    try:
        current_user = db.users.find_one({'_id': ObjectId(session['user_id'])})
        
        # Chỉ lấy tasks mà user là người giao hoặc người nhận
        pipeline = [
            {
                '$match': {
                    '$or': [
                        {'created_by': current_user['_id']},
                        {'assigned_to': current_user['_id']}
                    ]
                }
            },
            {
                '$lookup': {
                    'from': 'users',
                    'localField': 'created_by',
                    'foreignField': '_id', 
                    'as': 'creator'
                }
            },
            {
                '$lookup': {
                    'from': 'users',
                    'localField': 'assigned_to',
                    'foreignField': '_id',
                    'as': 'assignee'
                }
            },
            {
                '$addFields': {
                    'creator_name': {'$arrayElemAt': ['$creator.full_name', 0]},
                    'assignee_name': {'$arrayElemAt': ['$assignee.full_name', 0]}
                }
            }
        ]
        
        tasks = list(db.tasks.aggregate(pipeline))
        
        return render_template('tasks/list.html',
                             tasks=tasks,
                             current_user=current_user,
                             user=current_user)
                             
    except Exception as e:
        print(f"Error in list_tasks: {str(e)}")
        flash('Có lỗi xảy ra khi tải danh sách công việc!', 'error')
        return redirect(url_for('dashboard'))

def prepare_task_data(task, current_user):
    assignee = db.users.find_one({'_id': task.get('assigned_to')})
    creator = db.users.find_one({'_id': task.get('created_by')})
    
    return {
        '_id': str(task['_id']),
        'title': task.get('title'),
        'description': task.get('description'),
        'status': task.get('status'),
        'priority': task.get('priority'),
        'deadline': task.get('deadline'),
        'assigned_to': assignee['full_name'] if assignee else 'Chưa phân công',
        'created_by': creator['full_name'] if creator else 'Không xác định',
        'evidence': task.get('evidence', []),
        'completion_note': task.get('completion_note', '')
    }

@app.route('/tasks/delegate/<task_id>', methods=['POST'])
@login_required
def delegate_task(task_id):
    current_user = db.users.find_one({'_id': ObjectId(session['user_id'])})
    task = db.tasks.find_one({'_id': ObjectId(task_id)})
    
    if not task:
        return jsonify({'success': False, 'message': 'Không tìm thấy công việc!'})
        
    new_assignee_id = request.form.get('assigned_to')
    if not new_assignee_id:
        return jsonify({'success': False, 'message': 'Vui lòng chọn người xử lý!'})
        
    db.tasks.update_one(
        {'_id': ObjectId(task_id)},
        {
            '$set': {
                'assigned_to': ObjectId(new_assignee_id),
                'delegated_by': current_user['_id'],
                'delegated_at': datetime.now()
            }
        }
    )
    
    return jsonify({'success': True, 'message': 'Đã giao việc thành công!'})



@app.route('/get-organizations/<level>')
@login_required
def get_organizations_by_level(level):
    current_user = db.users.find_one({'_id': ObjectId(session['user_id'])})
    current_role = current_user.get('role', {}).get('name')
    
    # Xác định role được phép theo cấp và role người dùng
    allowed_roles = []
    
    if current_role == 'quan_tri_tinh':
        if level == 'tinh':
            allowed_roles = ['ban_thuong_truc']
        elif level == 'huyen':
            allowed_roles = ['quan_tri_huyen', 'nhan_vien_huyen']
        elif level == 'xa':
            allowed_roles = ['quan_tri_xa', 'doan_vien_xa']
            
    elif current_role == 'quan_tri_huyen':
        if level == 'huyen':
            allowed_roles = ['nhan_vien_huyen']
        elif level == 'xa':
            allowed_roles = ['quan_tri_xa', 'doan_vien_xa']
            
    elif current_role == 'quan_tri_xa':
        if level == 'xa':
            allowed_roles = ['doan_vien_xa']

    # Lấy danh sách users theo role được phép
    users = list(db.users.find(
        {
            'role.name': {'$in': allowed_roles},
            'status': 'active'
        },
        {
            '_id': 1,
            'full_name': 1,
            'role.position': 1
        }
    ))
    
    # Format kết quả trả về
    result = []
    for user in users:
        result.append({
            '_id': str(user['_id']),
            'full_name': user['full_name'],
            'role': user['role']['position']
        })
        
    return jsonify(result)

@app.route('/get-users/<level>/<org_id>')
@login_required
def get_users_by_level_and_org(level, org_id):
    if level == 'tinh':
        users = db.users.find({
            'organization_id': ObjectId(org_id),
            'role.level': 1
        })
    elif level == 'huyen':
        users = db.users.find({
            'organization_id': ObjectId(org_id),
            'role.level': 2
        })
    elif level == 'xa':
        users = db.users.find({
            'organization_id': ObjectId(org_id),
            'role.level': 3
        })
    
    result = []
    for user in users:
        result.append({
            '_id': str(user['_id']),
            'full_name': user['full_name']
        })
    
    return jsonify(result)

@app.route('/get-users-by-role/<level>')
@login_required
def get_users_by_role(level):
    current_user = db.users.find_one({'_id': ObjectId(session['user_id'])})
    
    role_mapping = {
        'chuyen_vien': 'chuyen_vien',
        'nhan_vien': 'nhan_vien_huyen',
        'doan_vien': 'doan_vien_xa'
    }
    
    role_name = role_mapping.get(level)
    if not role_name:
        return jsonify([])
        
    # Query users theo role
    query = {'role.name': role_name}
    
    # Thêm điều kiện organization_id nếu có
    if current_user.get('organization_id'):
        query['organization_id'] = current_user['organization_id']
        
    users = db.users.find(query)
    
    result = []
    for user in users:
        result.append({
            '_id': str(user['_id']),
            'full_name': user['full_name']
        })
    
    return jsonify(result)

@app.route('/tasks/delete/<task_id>', methods=['POST'])
@login_required
def delete_task(task_id):
    current_user = db.users.find_one({'_id': ObjectId(session['user_id'])})
    
    try:
        # Kiểm tra task có tồn tại
        task = db.tasks.find_one({'_id': ObjectId(task_id)})
        if not task:
            return jsonify({'success': False, 'message': 'Không tìm thấy công việc!'})
            
        # Kiểm tra quyền xóa (chỉ người tạo mới được xóa)
        if str(task['created_by']) != str(current_user['_id']):
            return jsonify({'success': False, 'message': 'Bạn không có quyền xóa công việc này!'})
            
        # Thực hiện xóa
        db.tasks.delete_one({'_id': ObjectId(task_id)})
        return jsonify({'success': True, 'message': 'Xóa công việc thành công!'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Có lỗi xảy ra: {str(e)}'})

@app.route('/members')
@login_required 
def list_members():
    try:
        current_user = db.users.find_one({'_id': ObjectId(session['user_id'])})
        
        # Admin có quyền xem tất cả
        if current_user['role']['level'] == 1:
            members = list(db.users.find())
            for member in members:
                member['_id'] = str(member['_id'])
            return render_template('members/list.html',
                               members=members,
                               user=current_user,
                               current_user=current_user)  # Thêm current_user
        
        # Các role khác kiểm tra theo level
        if not current_user.get('role'):
            flash('Bạn không có quyền truy cập!', 'error')
            return redirect(url_for('dashboard'))

        current_level = current_user['role'].get('level')
        viewable_levels = {
            2: [2, 3, 4, 5],
            3: [3, 4, 5],
            4: [4, 5]
        }
        
        allowed_levels = viewable_levels.get(current_level, [])
        if not allowed_levels:
            flash('Bạn không có quyền truy cập!', 'error')
            return redirect(url_for('dashboard'))
            
        query = {'role.level': {'$in': allowed_levels}}
        members = list(db.users.find(query))
        
        for member in members:
            member['_id'] = str(member['_id'])

        return render_template('members/list.html',
                           members=members,
                           user=current_user,
                           current_user=current_user)  # Thêm current_user

    except Exception as e:
        print(f"Error in list_members: {str(e)}")
        flash('Có lỗi xảy ra!', 'error')
        return redirect(url_for('dashboard'))

@app.route('/members/<member_id>')
@login_required
def member_detail(member_id):
    current_user = db.users.find_one({'_id': ObjectId(session['user_id'])})
    
    # Kiểm tra quyền xem theo role
    viewable_roles = {
        'quan_tri_tinh': [
            'ban_thuong_truc', 'ban_khac', 'chuyen_vien_btv', 
            'chuyen_vien_ban_khac', 'quan_tri_huyen', 'nhan_vien_huyen',
            'quan_tri_xa', 'doan_vien_xa'
        ],
        'quan_tri_huyen': ['nhan_vien_huyen', 'quan_tri_xa', 'doan_vien_xa'],
        'quan_tri_xa': ['doan_vien_xa']
    }
    
    current_role = current_user['role'].get('name')
    allowed_roles = viewable_roles.get(current_role, [])
    
    if not allowed_roles:
        flash('Bạn không có quyền xem thông tin thành viên!', 'error')
        return redirect(url_for('dashboard'))
        
    member = db.users.find_one({'_id': ObjectId(member_id)})
    if not member:
        flash('Không tìm thấy thành viên!', 'error')
        return redirect(url_for('list_members'))
        
    if member['role']['name'] not in allowed_roles:
        flash('Bạn không có quyền xem thông tin thành viên này!', 'error')
        return redirect(url_for('list_members'))
        
    # Lấy danh sách công việc đã tham gia
    tasks = db.tasks.find({
        'assigned_to': ObjectId(member_id)
    }).sort('created_at', -1)
    
    # Lấy lịch sử hoạt động (login, tạo task, cập nhật task...)
    activity_logs = db.activity_logs.find({
        'user_id': ObjectId(member_id)
    }).sort('timestamp', -1).limit(20)
    
    return render_template('members/detail.html',
                         user=current_user,
                         member=member,
                         tasks=tasks,
                         activity_logs=activity_logs)

@app.route('/tasks/create', methods=['GET', 'POST'])
@login_required
def create_task():
    current_user = db.users.find_one({'_id': ObjectId(session['user_id'])})
    if not current_user:
        flash('Không tìm thấy thông tin người dùng!', 'error')
        return redirect(url_for('login'))

    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        priority = request.form.get('priority')
        deadline = request.form.get('deadline')
        assigned_to = request.form.get('assigned_to')
        organization_level = request.form.get('organization_level')

        if not title or not assigned_to:
            flash('Vui lòng điền đầy đủ thông tin!', 'error')
            return render_template('tasks/create.html', user=current_user)

        # Convert deadline string to datetime if provided
        deadline_date = None
        if deadline:
            try:
                deadline_date = datetime.strptime(deadline, '%Y-%m-%d')
            except ValueError:
                flash('Định dạng ngày không hợp lệ!', 'error')
                return render_template('tasks/create.html', user=current_user)

        # Lấy organization_id của người được giao việc
        assignee = db.users.find_one({'_id': ObjectId(assigned_to)})
        if not assignee:
            flash('Không tìm thấy thông tin người được giao việc!', 'error')
            return render_template('tasks/create.html', user=current_user)

        new_task = {
            'title': title,
            'description': description,
            'status': 'waiting',
            'priority': priority,
            'deadline': deadline_date,
            'assigned_to': ObjectId(assigned_to),
            'created_by': current_user['_id'],
            'organization_level': organization_level,
            'organization_id': assignee.get('organization_id'),
            'created_at': datetime.now(),
            'updated_at': datetime.now()
        }

        try:
            result = db.tasks.insert_one(new_task)
            if result.inserted_id:
                flash('Tạo công việc thành công!', 'success')
                return redirect(url_for('list_tasks'))
            else:
                flash('Có lỗi xảy ra khi tạo công việc!', 'error')
        except Exception as e:
            flash(f'Có lỗi xảy ra: {str(e)}', 'error')
            
    return render_template('tasks/create.html', user=current_user)

@app.route('/tasks/edit/<task_id>', methods=['GET', 'POST'])
@login_required
def edit_task(task_id):
    try:
        current_user = db.users.find_one({'_id': ObjectId(session['user_id'])})
        task = db.tasks.find_one({'_id': ObjectId(task_id)})
        
        if not task:
            flash('Không tìm thấy công việc!', 'error')
            return redirect(url_for('list_tasks'))

        # Kiểm tra quyền sửa
        if str(task['created_by']) != str(current_user['_id']) and str(task['assigned_to']) != str(current_user['_id']):
            flash('Bạn không có quyền sửa công việc này!', 'error')
            return redirect(url_for('list_tasks'))
            
        if request.method == 'POST':
            title = request.form.get('title')
            description = request.form.get('description')
            priority = request.form.get('priority')
            deadline = request.form.get('deadline')
            status = request.form.get('status')
            
            if not title:
                flash('Vui lòng điền tiêu đề!', 'error')
                return render_template('tasks/edit.html', 
                                     user=current_user, 
                                     task=task,
                                     is_creator=(str(task['created_by']) == str(current_user['_id'])))
                
            # Convert deadline
            deadline_date = None
            if deadline:
                try:
                    deadline_date = datetime.strptime(deadline, '%Y-%m-%d')
                except ValueError:
                    flash('Định dạng ngày không hợp lệ!', 'error')
                    return render_template('tasks/edit.html', 
                                         user=current_user, 
                                         task=task,
                                         is_creator=(str(task['created_by']) == str(current_user['_id'])))
                    
            # Update task
            update_data = {
                'updated_at': datetime.now()
            }
            
            # Người giao có thể sửa mọi thông tin
            if str(task['created_by']) == str(current_user['_id']):
                update_data.update({
                    'title': title,
                    'description': description,
                    'priority': priority,
                    'deadline': deadline_date,
                    'status': status
                })
            # Người nhận chỉ có thể sửa trạng thái
            else:
                update_data['status'] = status
            
            db.tasks.update_one(
                {'_id': ObjectId(task_id)},
                {'$set': update_data}
            )
            
            flash('Cập nhật công việc thành công!', 'success')
            return redirect(url_for('list_tasks'))
            
        return render_template('tasks/edit.html', 
                             user=current_user, 
                             task=task,
                             is_creator=(str(task['created_by']) == str(current_user['_id'])))

    except Exception as e:
        print(f"Error in edit_task: {str(e)}")
        flash('Có lỗi xảy ra!', 'error')
        return redirect(url_for('list_tasks'))

@app.route('/members/delete/<member_id>', methods=['POST'])
@login_required
def delete_member(member_id):
    current_user = db.users.find_one({'_id': ObjectId(session['user_id'])})
    
    # Kiểm tra quyền admin
    if not current_user.get('role') or current_user['role']['level'] != 1:
        flash('Bạn không có quyền xóa thành viên!', 'error')
        return redirect(url_for('list_members'))
    
    # Không cho phép xóa tài khoản System Administrator
    member = db.users.find_one({'_id': ObjectId(member_id)})
    if member['username'] == 'admin':
        flash('Không thể xóa tài khoản System Administrator!', 'error')
        return redirect(url_for('list_members'))
    
    db.users.delete_one({'_id': ObjectId(member_id)})
    flash('Xóa thành viên thành công!', 'success')
    return redirect(url_for('list_members'))

@app.route('/tasks/<task_id>/complete', methods=['POST'])
@login_required
def complete_task(task_id):
    try:
        current_user = db.users.find_one({'_id': ObjectId(session['user_id'])})
        task = db.tasks.find_one({'_id': ObjectId(task_id)})
        
        if not task:
            flash('Không tìm thấy công việc!', 'error')
            return redirect(url_for('list_tasks'))
            
        # Kiểm tra người thực hiện
        if str(task['assignee']) != str(current_user['_id']):
            flash('Bạn không phải người được giao việc này!', 'error')
            return redirect(url_for('list_tasks'))

        # Kiểm tra file minh chứng
        if 'evidence' not in request.files:
            flash('Vui lòng đính kèm minh chứng!', 'error')
            return redirect(url_for('list_tasks'))
            
        evidence_file = request.files['evidence']
        if evidence_file.filename == '':
            flash('Vui lòng chọn file minh chứng!', 'error')
            return redirect(url_for('list_tasks'))

        # Lưu file minh chứng
        if evidence_file:
            filename = secure_filename(evidence_file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            evidence_file.save(file_path)

        # Cập nhật trạng thái công việc
        db.tasks.update_one(
            {'_id': ObjectId(task_id)},
            {'$set': {
                'status': 'completed',
                'completed_at': datetime.now(),
                'evidence_file': filename
            }}
        )

        flash('Đã cập nhật trạng thái công việc!', 'success')
        return redirect(url_for('list_tasks'))

    except Exception as e:
        print(f"Error in complete_task: {str(e)}")
        flash('Có lỗi xảy ra!', 'error')
        return redirect(url_for('list_tasks'))

@app.route('/get_news')
def get_news():
    return jsonify({
        'news': news_cache['items'],
        'last_updated': news_cache['last_updated'].strftime('%Y-%m-%d %H:%M:%S') if news_cache['last_updated'] else None
    })

if __name__ == '__main__':
    app.run(
        host='0.0.0.0',  # Cho phép truy cập từ mọi IP trong mạng LAN
        port=5000,       # Port mặc định
        debug=True       # Tắt debug mode khi chạy production
    ) 