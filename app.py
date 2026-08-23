from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, date
from functools import wraps
from pathlib import Path

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for, send_file
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / 'instance'
UPLOAD_DIR = BASE_DIR / 'static' / 'uploads'
INSTANCE_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'change-this-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{INSTANCE_DIR / '4tact.sqlite3'}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024
app.config['UPLOAD_EXTENSIONS'] = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}

db = SQLAlchemy(app)


# ---------------------------- Models ----------------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(120), nullable=False, default='Пользователь')
    phone = db.Column(db.String(50), default='')
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    favorites = db.relationship('Favorite', backref='user', cascade='all, delete-orphan')
    cart_items = db.relationship('CartItem', backref='user', cascade='all, delete-orphan')

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    brand = db.Column(db.String(120), default='')
    description = db.Column(db.Text, default='')
    price = db.Column(db.Float, nullable=False, default=0)
    car_make = db.Column(db.String(120), default='')
    car_model = db.Column(db.String(120), default='')
    sku = db.Column(db.String(120), default='')
    stock = db.Column(db.Integer, default=0)
    images_json = db.Column(db.Text, default='[]')
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def images(self):
        try:
            return json.loads(self.images_json or '[]')
        except Exception:
            return []

    def set_images(self, paths):
        self.images_json = json.dumps(paths, ensure_ascii=False)


class Favorite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    __table_args__ = (db.UniqueConstraint('user_id', 'product_id', name='uq_favorite'),)
    product = db.relationship('Product')


class CartItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    product = db.relationship('Product')
    __table_args__ = (db.UniqueConstraint('user_id', 'product_id', name='uq_cart'),)


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    customer_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    comment = db.Column(db.Text, default='')
    total = db.Column(db.Float, default=0)
    status = db.Column(db.String(30), default='new')  # new, working, done
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    user = db.relationship('User')
    items = db.relationship('OrderItem', backref='order', cascade='all, delete-orphan')


class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_id = db.Column(db.Integer, nullable=True)
    product_name = db.Column(db.String(255), nullable=False)
    price = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)


class ExpertRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    vin = db.Column(db.String(80), nullable=False)
    part = db.Column(db.String(255), nullable=False)
    comment = db.Column(db.Text, default='')
    customer_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(50), default='')
    email = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(30), default='new')  # new, working, done
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    user = db.relationship('User')


class SiteSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(120), unique=True, nullable=False)
    value = db.Column(db.Text, default='')


# ---------------------------- Helpers ----------------------------
def current_user():
    user_id = session.get('user_id')
    return db.session.get(User, user_id) if user_id else None


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user():
            if request.path.startswith('/api/'):
                return jsonify({'ok': False, 'error': 'Требуется вход'}), 401
            flash('Войдите в аккаунт, чтобы продолжить.', 'warning')
            return redirect(url_for('auth'))
        return view(*args, **kwargs)
    return wrapper


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user or not user.is_admin:
            if request.path.startswith('/api/'):
                return jsonify({'ok': False, 'error': 'Доступ запрещён'}), 403
            flash('Нужны права администратора.', 'error')
            return redirect(url_for('home'))
        return view(*args, **kwargs)
    return wrapper


def parse_price(value):
    try:
        return round(float(str(value).replace(' ', '').replace(',', '.')), 2)
    except Exception:
        return 0.0


def product_from_form(product: Product, form):
    product.name = form.get('name', '').strip()
    product.brand = form.get('brand', '').strip()
    product.description = form.get('description', '').strip()
    product.price = parse_price(form.get('price', 0))
    product.car_make = form.get('car_make', '').strip()
    product.car_model = form.get('car_model', '').strip()
    product.sku = form.get('sku', '').strip()
    try:
        product.stock = max(0, int(form.get('stock', 0)))
    except Exception:
        product.stock = 0
    return product


def save_uploaded_images(files):
    saved = []
    for file in files:
        if not file or not file.filename:
            continue
        ext = Path(file.filename).suffix.lower()
        if ext not in app.config['UPLOAD_EXTENSIONS']:
            continue
        safe = secure_filename(Path(file.filename).stem) or 'image'
        token = secrets.token_hex(5)
        filename = f"{safe}_{token}{ext}"
        destination = UPLOAD_DIR / filename
        file.save(destination)
        saved.append(f"/static/uploads/{filename}")
    return saved


def status_label(status):
    return {'new': 'Новое', 'working': 'В работе', 'done': 'Выполнено'}.get(status, status)


@app.context_processor
def inject_globals():
    user = current_user()
    cart_count = 0
    favorite_ids = set()
    if user:
        cart_count = sum(i.quantity for i in user.cart_items)
        favorite_ids = {f.product_id for f in user.favorites}
    return {
        'current_user': user,
        'cart_count': cart_count,
        'favorite_ids': favorite_ids,
        'status_label': status_label,
    }


# ---------------------------- App setup ----------------------------
def seed_data():
    if not User.query.filter_by(is_admin=True).first():
        admin = User(email='admin', name='Администратор', is_admin=True)
        admin.set_password('admin')
        db.session.add(admin)

    samples = Product.query.count()
    if samples == 0:
        demo = [
            Product(name='Тормозные колодки', brand='Оригинал', price=329520, car_make='Toyota', car_model='Camry', description='Оригинальные передние тормозные колодки.', sku='BP-329520', stock=4),
            Product(name='Тормозные колодки', brand='ADR', price=6795, car_make='BMW', car_model='3 Series', description='Комплект тормозных колодок ADR.', sku='ADR-6795', stock=10),
            Product(name='Тормозные колодки', brand='ADR', price=1, car_make='Lada', car_model='Vesta', description='Бюджетный комплект колодок.', sku='ADR-1', stock=20),
        ]
        for p in demo:
            p.set_images([])
            db.session.add(p)
    db.session.commit()


with app.app_context():
    db.create_all()
    seed_data()


# ---------------------------- Pages ----------------------------
@app.route('/')
def home():
    return render_template('index.html')


@app.route('/search')
def search_page():
    return render_template('search.html')


@app.route('/auth')
def auth():
    if current_user():
        return redirect(url_for('profile'))
    return render_template('auth.html')


@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html')


@app.route('/cart')
@login_required
def cart():
    return render_template('cart.html')


@app.route('/admin')
@admin_required
def admin_panel():
    stats = {
        'new_orders': Order.query.filter_by(status='new').count(),
        'working_orders': Order.query.filter_by(status='working').count(),
        'done_orders': Order.query.filter_by(status='done').count(),
        'new_requests': ExpertRequest.query.filter_by(status='new').count(),
        'working_requests': ExpertRequest.query.filter_by(status='working').count(),
        'done_requests': ExpertRequest.query.filter_by(status='done').count(),
        'products': Product.query.filter_by(is_active=True).count(),
    }
    return render_template('admin.html', stats=stats)


# ---------------------------- Auth API ----------------------------
@app.post('/api/register')
def api_register():
    data = request.get_json(silent=True) or request.form
    email = str(data.get('email', '')).strip().lower()
    password = str(data.get('password', ''))
    name = str(data.get('name', '')).strip() or 'Пользователь'
    if '@' not in email or len(password) < 4:
        return jsonify({'ok': False, 'error': 'Укажите корректную почту и пароль от 4 символов.'}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({'ok': False, 'error': 'Пользователь с такой почтой уже существует.'}), 409
    user = User(email=email, name=name)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    session['user_id'] = user.id
    return jsonify({'ok': True, 'redirect': url_for('home')})


@app.post('/api/login')
def api_login():
    data = request.get_json(silent=True) or request.form
    login = str(data.get('email', '')).strip().lower()
    password = str(data.get('password', ''))
    user = User.query.filter_by(email=login).first()
    if user and user.check_password(password):
        session['user_id'] = user.id
        return jsonify({'ok': True, 'redirect': url_for('admin_panel' if user.is_admin else 'home')})
    return jsonify({'ok': False, 'error': 'Неверная почта/логин или пароль.'}), 401


@app.post('/api/logout')
def api_logout():
    session.clear()
    return jsonify({'ok': True, 'redirect': url_for('home')})


# ---------------------------- Search / Products ----------------------------
@app.get('/api/products')
def api_products():
    q = request.args.get('q', '').strip().lower()
    make = request.args.get('make', '').strip().lower()
    model = request.args.get('model', '').strip().lower()
    part = request.args.get('part', '').strip().lower()
    brand = request.args.get('brand', '').strip().lower()
    products = Product.query.filter_by(is_active=True).order_by(Product.created_at.desc()).all()
    result = []
    for p in products:
        hay = ' '.join([p.name, p.brand, p.description, p.car_make, p.car_model, p.sku]).lower()
        if q and q not in hay:
            continue
        if make and make not in p.car_make.lower():
            continue
        if model and model not in p.car_model.lower():
            continue
        if part and part not in (p.name + ' ' + p.description).lower():
            continue
        if brand and brand not in p.brand.lower():
            continue
        result.append({
            'id': p.id, 'name': p.name, 'brand': p.brand, 'description': p.description,
            'price': p.price, 'car_make': p.car_make, 'car_model': p.car_model,
            'sku': p.sku, 'stock': p.stock, 'images': p.images,
            'favorite': p.id in (inject_globals()['favorite_ids'] or set()),
        })
    return jsonify({'ok': True, 'products': result})


@app.post('/api/favorites/<int:product_id>')
@login_required
def api_favorite(product_id):
    user = current_user()
    product = db.session.get(Product, product_id)
    if not product:
        return jsonify({'ok': False, 'error': 'Товар не найден'}), 404
    existing = Favorite.query.filter_by(user_id=user.id, product_id=product_id).first()
    if existing:
        db.session.delete(existing)
        active = False
    else:
        db.session.add(Favorite(user_id=user.id, product_id=product_id))
        active = True
    db.session.commit()
    return jsonify({'ok': True, 'favorite': active})


@app.post('/api/cart/<int:product_id>')
@login_required
def api_cart_add(product_id):
    user = current_user()
    product = db.session.get(Product, product_id)
    if not product or not product.is_active:
        return jsonify({'ok': False, 'error': 'Товар не найден'}), 404
    item = CartItem.query.filter_by(user_id=user.id, product_id=product_id).first()
    if item:
        item.quantity += 1
    else:
        item = CartItem(user_id=user.id, product_id=product_id, quantity=1)
        db.session.add(item)
    db.session.commit()
    return jsonify({'ok': True, 'message': 'Товар добавлен в корзину.'})


@app.get('/api/cart')
@login_required
def api_cart():
    user = current_user()
    items = []
    total = 0
    for item in user.cart_items:
        subtotal = item.product.price * item.quantity
        total += subtotal
        items.append({'id': item.id, 'product_id': item.product.id, 'name': item.product.name,
                      'price': item.product.price, 'quantity': item.quantity, 'images': item.product.images,
                      'subtotal': subtotal})
    return jsonify({'ok': True, 'items': items, 'total': total})


@app.delete('/api/cart/<int:item_id>')
@login_required
def api_cart_delete(item_id):
    item = CartItem.query.filter_by(id=item_id, user_id=current_user().id).first()
    if item:
        db.session.delete(item)
        db.session.commit()
    return jsonify({'ok': True})


# ---------------------------- Orders ----------------------------
@app.post('/api/orders')
@login_required
def api_order_create():
    user = current_user()
    data = request.get_json(silent=True) or request.form
    name = str(data.get('name', '')).strip() or user.name
    phone = str(data.get('phone', '')).strip()
    email = str(data.get('email', '')).strip() or user.email
    comment = str(data.get('comment', '')).strip()
    if not phone:
        return jsonify({'ok': False, 'error': 'Укажите номер телефона.'}), 400
    if not user.cart_items:
        return jsonify({'ok': False, 'error': 'Корзина пуста.'}), 400
    order = Order(user_id=user.id, customer_name=name, phone=phone, email=email, comment=comment, status='new')
    total = 0
    for cart_item in list(user.cart_items):
        p = cart_item.product
        order_item = OrderItem(product_id=p.id, product_name=p.name, price=p.price, quantity=cart_item.quantity)
        order.items.append(order_item)
        total += p.price * cart_item.quantity
        db.session.delete(cart_item)
    order.total = total
    db.session.add(order)
    db.session.commit()
    return jsonify({'ok': True, 'order_id': order.id})


# ---------------------------- Expert requests ----------------------------
@app.post('/api/expert-requests')
@login_required
def api_expert_create():
    user = current_user()
    data = request.get_json(silent=True) or request.form
    vin = str(data.get('vin', '')).strip()
    part = str(data.get('part', '')).strip()
    comment = str(data.get('comment', '')).strip()
    phone = str(data.get('phone', '')).strip() or user.phone
    if not vin or not part or not phone:
        return jsonify({'ok': False, 'error': 'Заполните VIN, искомую запчасть и телефон.'}), 400
    req = ExpertRequest(user_id=user.id, vin=vin, part=part, comment=comment,
                        customer_name=user.name, phone=phone, email=user.email)
    user.phone = phone
    db.session.add(req)
    db.session.commit()
    return jsonify({'ok': True, 'request_id': req.id})


# ---------------------------- Profile ----------------------------
@app.post('/api/profile')
@login_required
def api_profile():
    user = current_user()
    data = request.get_json(silent=True) or request.form
    name = str(data.get('name', '')).strip()
    phone = str(data.get('phone', '')).strip()
    new_password = str(data.get('password', ''))
    if name:
        user.name = name
    user.phone = phone
    if new_password:
        if len(new_password) < 4:
            return jsonify({'ok': False, 'error': 'Пароль должен быть минимум 4 символа.'}), 400
        user.set_password(new_password)
    db.session.commit()
    return jsonify({'ok': True})


# ---------------------------- Admin API ----------------------------
@app.get('/api/admin/dashboard')
@admin_required
def api_admin_dashboard():
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(8).all()
    recent_requests = ExpertRequest.query.order_by(ExpertRequest.created_at.desc()).limit(8).all()
    return jsonify({'ok': True,
        'orders': [order_to_dict(o) for o in recent_orders],
        'requests': [request_to_dict(r) for r in recent_requests],
    })


def order_to_dict(o):
    return {'id': o.id, 'customer_name': o.customer_name, 'phone': o.phone, 'email': o.email,
            'comment': o.comment, 'total': o.total, 'status': o.status, 'status_label': status_label(o.status),
            'created_at': o.created_at.strftime('%d.%m.%Y %H:%M'),
            'items': [{'name': i.product_name, 'price': i.price, 'quantity': i.quantity} for i in o.items]}


def request_to_dict(r):
    return {'id': r.id, 'customer_name': r.customer_name, 'phone': r.phone, 'email': r.email,
            'vin': r.vin, 'part': r.part, 'comment': r.comment, 'status': r.status,
            'status_label': status_label(r.status), 'created_at': r.created_at.strftime('%d.%m.%Y %H:%M')}


@app.get('/api/admin/orders')
@admin_required
def api_admin_orders():
    status = request.args.get('status', '')
    query = Order.query.order_by(Order.created_at.desc())
    if status:
        query = query.filter_by(status=status)
    return jsonify({'ok': True, 'orders': [order_to_dict(o) for o in query.all()]})


@app.patch('/api/admin/orders/<int:order_id>')
@admin_required
def api_admin_order_status(order_id):
    order = db.session.get(Order, order_id)
    if not order:
        return jsonify({'ok': False, 'error': 'Заказ не найден'}), 404
    data = request.get_json(silent=True) or {}
    status = data.get('status')
    if status not in {'new', 'working', 'done'}:
        return jsonify({'ok': False, 'error': 'Некорректный статус'}), 400
    order.status = status
    order.completed_at = datetime.utcnow() if status == 'done' else None
    db.session.commit()
    return jsonify({'ok': True})


@app.get('/api/admin/requests')
@admin_required
def api_admin_requests():
    status = request.args.get('status', '')
    query = ExpertRequest.query.order_by(ExpertRequest.created_at.desc())
    if status:
        query = query.filter_by(status=status)
    return jsonify({'ok': True, 'requests': [request_to_dict(r) for r in query.all()]})


@app.patch('/api/admin/requests/<int:req_id>')
@admin_required
def api_admin_request_status(req_id):
    req = db.session.get(ExpertRequest, req_id)
    if not req:
        return jsonify({'ok': False, 'error': 'Заявка не найдена'}), 404
    data = request.get_json(silent=True) or {}
    status = data.get('status')
    if status not in {'new', 'working', 'done'}:
        return jsonify({'ok': False, 'error': 'Некорректный статус'}), 400
    req.status = status
    req.completed_at = datetime.utcnow() if status == 'done' else None
    db.session.commit()
    return jsonify({'ok': True})


@app.get('/api/admin/products')
@admin_required
def api_admin_products():
    return jsonify({'ok': True, 'products': [
        {'id': p.id, 'name': p.name, 'brand': p.brand, 'description': p.description,
         'price': p.price, 'car_make': p.car_make, 'car_model': p.car_model, 'sku': p.sku,
         'stock': p.stock, 'images': p.images, 'is_active': p.is_active}
        for p in Product.query.order_by(Product.created_at.desc()).all()
    ]})


@app.post('/api/admin/products')
@admin_required
def api_admin_product_create():
    p = product_from_form(Product(), request.form)
    if not p.name:
        return jsonify({'ok': False, 'error': 'Введите название товара.'}), 400
    files = request.files.getlist('images')
    images = save_uploaded_images(files[:5])
    p.set_images(images)
    db.session.add(p)
    db.session.commit()
    return jsonify({'ok': True, 'product_id': p.id})


@app.post('/api/admin/products/<int:product_id>')
@admin_required
def api_admin_product_update(product_id):
    p = db.session.get(Product, product_id)
    if not p:
        return jsonify({'ok': False, 'error': 'Товар не найден'}), 404
    product_from_form(p, request.form)
    keep = request.form.get('existing_images')
    paths = json.loads(keep) if keep else p.images
    files = request.files.getlist('images')
    new_images = save_uploaded_images(files[:5])
    p.set_images((paths + new_images)[:5])
    p.is_active = request.form.get('is_active', '1') != '0'
    db.session.commit()
    return jsonify({'ok': True})


@app.delete('/api/admin/products/<int:product_id>')
@admin_required
def api_admin_product_delete(product_id):
    p = db.session.get(Product, product_id)
    if not p:
        return jsonify({'ok': False, 'error': 'Товар не найден'}), 404
    p.is_active = False
    db.session.commit()
    return jsonify({'ok': True})


@app.post('/api/admin/password')
@admin_required
def api_admin_password():
    admin = current_user()
    data = request.get_json(silent=True) or request.form
    old = str(data.get('old_password', ''))
    new = str(data.get('new_password', ''))
    if not admin.check_password(old):
        return jsonify({'ok': False, 'error': 'Старый пароль неверен.'}), 400
    if len(new) < 4:
        return jsonify({'ok': False, 'error': 'Новый пароль должен быть от 4 символов.'}), 400
    admin.set_password(new)
    db.session.commit()
    return jsonify({'ok': True})


@app.get('/api/admin/report')
@admin_required
def api_admin_report():
    start_raw = request.args.get('start')
    end_raw = request.args.get('end')
    try:
        start = date.fromisoformat(start_raw) if start_raw else date.today().replace(day=1)
        end = date.fromisoformat(end_raw) if end_raw else date.today()
    except Exception:
        return jsonify({'ok': False, 'error': 'Неверный период'}), 400
    end_exclusive = datetime.combine(end, datetime.max.time())
    start_dt = datetime.combine(start, datetime.min.time())
    orders = Order.query.filter(Order.created_at >= start_dt, Order.created_at <= end_exclusive).order_by(Order.created_at).all()
    requests_ = ExpertRequest.query.filter(ExpertRequest.created_at >= start_dt, ExpertRequest.created_at <= end_exclusive).order_by(ExpertRequest.created_at).all()
    done_orders = [o for o in orders if o.status == 'done']
    profit = round(sum(o.total for o in done_orders), 2)
    return jsonify({'ok': True,
        'period': {'start': start.isoformat(), 'end': end.isoformat()},
        'orders': [order_to_dict(o) for o in orders],
        'requests': [request_to_dict(r) for r in requests_],
        'profit': profit
    })


@app.get('/admin/report.pdf')
@admin_required
def admin_report_pdf():
    start_raw = request.args.get('start')
    end_raw = request.args.get('end')
    try:
        start = date.fromisoformat(start_raw) if start_raw else date.today().replace(day=1)
        end = date.fromisoformat(end_raw) if end_raw else date.today()
    except Exception:
        return 'Неверный период', 400
    end_exclusive = datetime.combine(end, datetime.max.time())
    start_dt = datetime.combine(start, datetime.min.time())
    orders = Order.query.filter(Order.created_at >= start_dt, Order.created_at <= end_exclusive).order_by(Order.created_at).all()
    requests_ = ExpertRequest.query.filter(ExpertRequest.created_at >= start_dt, ExpertRequest.created_at <= end_exclusive).order_by(ExpertRequest.created_at).all()
    profit = round(sum(o.total for o in orders if o.status == 'done'), 2)

    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.pdfbase import pdfmetrics
        from reportlab.lib import colors
        import io

        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        font_regular = 'Helvetica'
        font_bold = 'Helvetica-Bold'
        font_path = os.environ.get('T4TACT_FONT')
        if font_path and os.path.exists(font_path):
            pdfmetrics.registerFont(TTFont('SiteFont', font_path))
            font_regular = font_bold = 'SiteFont'

        y = height - 48
        c.setFont(font_bold, 18)
        c.drawString(42, y, '4tact.ru — отчёт')
        y -= 24
        c.setFont(font_regular, 10)
        c.drawString(42, y, f'Период: {start.strftime("%d.%m.%Y")} — {end.strftime("%d.%m.%Y")}')
        y -= 28

        c.setFont(font_bold, 12)
        c.drawString(42, y, 'Заказы')
        y -= 18
        c.setFont(font_regular, 9)
        for o in orders:
            line = f'#{o.id}  {o.created_at.strftime("%d.%m.%Y")}  {o.customer_name[:20]}  {o.total:.2f} ₽  {status_label(o.status)}'
            c.drawString(42, y, line)
            y -= 14
            if y < 60:
                c.showPage(); y = height - 48; c.setFont(font_regular, 9)
        y -= 8
        c.setFont(font_bold, 12)
        c.drawString(42, y, 'Заявки на подбор')
        y -= 18
        c.setFont(font_regular, 9)
        for r in requests_:
            line = f'#{r.id}  {r.created_at.strftime("%d.%m.%Y")}  {r.customer_name[:20]}  {r.part[:32]}  {status_label(r.status)}'
            c.drawString(42, y, line)
            y -= 14
            if y < 60:
                c.showPage(); y = height - 48; c.setFont(font_regular, 9)
        y -= 12
        c.setFont(font_bold, 14)
        c.setFillColor(colors.HexColor('#2463cf'))
        c.drawString(42, y, f'Итоговая прибыль: {profit:.2f} ₽')
        c.save()
        buffer.seek(0)
        return send_file(buffer, mimetype='application/pdf', as_attachment=True,
                         download_name=f'4tact_report_{start}_{end}.pdf')
    except ImportError:
        return 'Для PDF нужен пакет reportlab. Установите зависимости из requirements.txt.', 500


if __name__ == '__main__':
    app.run(debug=True)
