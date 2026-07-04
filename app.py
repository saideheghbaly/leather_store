import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
from flask_admin.form.upload import ImageUploadField
from sqlalchemy import desc
from markupsafe import Markup

app = Flask(__name__)

# تنظیمات اصلی برنامه
app.config['SECRET_KEY'] = 'secret123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///shop.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static/images')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

db = SQLAlchemy(app)

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])


@app.template_filter('comma_decimal')
def comma_decimal_filter(value):
    try:
        return "{:,}".format(int(value))
    except (ValueError, TypeError):
        return value


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Integer, nullable=False)
    image = db.Column(db.String(100))
    description = db.Column(db.String(500))
    features = db.Column(db.String(500))

    def __repr__(self):
        return self.name


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    customer_name = db.Column(db.String(100), nullable=False)
    customer_address = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(50), default='در انتظار')
    product = db.relationship('Product', backref=db.backref('orders', lazy=True))


class ProductAdmin(ModelView):
    column_list = ('image_preview', 'name', 'price', 'description', 'features')

    def _list_thumbnail(view, context, model, name):
        if not model.image:
            return ''
        file_url = f"/static/images/{model.image}"
        return Markup(
            f'<a href="{file_url}" target="_blank" '
            f'style="text-decoration: none; font-weight: bold; color: #007bff;">'
            f'🔗 مشاهده عکس ({model.image})</a>'
        )

    column_formatters = {
        'image_preview': _list_thumbnail
    }

    column_labels = {
        'image_preview': 'لینک تصویر',
        'name': 'نام محصول',
        'price': 'قیمت (تومان)',
        'description': 'توضیحات',
        'features': 'ویژگی‌ها'
    }

    form_columns = ('name', 'price', 'image', 'description', 'features')
    form_overrides = {
        'image': ImageUploadField
    }
    form_args = {
        'image': {
            'label': 'تصویر محصول',
            'base_path': app.config['UPLOAD_FOLDER'],
            'relative_path': ''
        }
    }


class OrderAdmin(ModelView):
    column_list = ('customer_name', 'product', 'status', 'customer_address')
    form_columns = ('customer_name', 'customer_address', 'product', 'status')

    column_labels = {
        'customer_name': 'نام مشتری',
        'product': 'محصول خریداری شده',
        'status': 'وضعیت سفارش',
        'customer_address': 'آدرس تحویل'
    }


admin = Admin(app, name='پنل مدیریت چرم شیک', template_mode='bootstrap3')
admin.add_view(ProductAdmin(Product, db.session))
admin.add_view(OrderAdmin(Order, db.session))


@app.route('/')
def index():
    products = Product.query.order_by(desc(Product.id)).all()
    return render_template('index.html', products=products)


@app.route('/search')
def search():
    query = request.args.get('query', '').strip()
    if query:
        products = Product.query.filter(
            (Product.name.ilike(f'%{query}%')) |
            (Product.description.ilike(f'%{query}%')) |
            (Product.features.ilike(f'%{query}%'))
        ).order_by(desc(Product.id)).all()
    else:
        products = Product.query.order_by(desc(Product.id)).all()
    return render_template('index.html', products=products, query=query)


@app.route('/add_to_cart/<int:product_id>')
def add_to_cart(product_id):
    product = Product.query.get_or_404(product_id)

    if 'cart' not in session:
        session['cart'] = []

    cart = session['cart']
    if product_id not in cart:
        cart.append(product_id)

    session['cart'] = cart
    session.modified = True

    flash(f'محصول "{product.name}" به سبد خرید شما اضافه شد.', 'success')

    if request.args.get('redirect') == 'cart':
        return redirect(url_for('view_cart'))

    return redirect(url_for('index'))


@app.route('/cart')
def view_cart():
    cart_product_ids = session.get('cart', [])

    if not cart_product_ids:
        return render_template('cart.html', products=[], total_price=0)

    products = Product.query.filter(Product.id.in_(cart_product_ids)).all()
    total_price = sum(product.price for product in products)

    return render_template('cart.html', products=products, total_price=total_price)


@app.route('/remove_from_cart/<int:product_id>')
def remove_from_cart(product_id):
    if 'cart' in session:
        cart = session['cart']
        if product_id in cart:
            cart.remove(product_id)
            session['cart'] = cart
            session.modified = True
            flash('محصول از سبد خرید شما حذف شد.', 'info')

    return redirect(url_for('view_cart'))


@app.route('/clear_cart')
def clear_cart():
    session.pop('cart', None)
    flash('سبد خرید شما کاملاً خالی شد.', 'info')
    return redirect(url_for('view_cart'))


@app.route('/place_order', methods=['GET', 'POST'])
def place_order():
    product_id = request.args.get('product_id', type=int) or request.form.get('product_id', type=int)

    if product_id:
        product = Product.query.get_or_404(product_id)
        products = [product]
    else:
        cart_product_ids = session.get('cart', [])
        if not cart_product_ids:
            flash('سبد خرید شما خالی است و محصولی برای ثبت وجود ندارد.', 'warning')
            return redirect(url_for('index'))
        products = Product.query.filter(Product.id.in_(cart_product_ids)).all()

    if request.method == 'POST':
        customer_name = request.form.get('customer_name', '').strip()
        customer_address = request.form.get('customer_address', '').strip()

        if not customer_name or not customer_address:
            flash('لطفاً نام و آدرس دقیق خود را جهت ارسال وارد کنید.', 'danger')
            return render_template('order.html', products=products)

        for prod in products:
            new_order = Order(
                product_id=prod.id,
                customer_name=customer_name,
                customer_address=customer_address,
                status='در انتظار'
            )
            db.session.add(new_order)

        db.session.commit()

        if not product_id:
            session.pop('cart', None)

        flash('سفارش شما با موفقیت ثبت شد! به زودی با شما تماس می‌گیریم.', 'success')
        return redirect(url_for('index'))

    return render_template('order.html', products=products)


with app.app_context():
    db.create_all()


if __name__ == '__main__':
    app.run(debug=True)


