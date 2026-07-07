import os
import shutil
import uuid

from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.orm import declarative_base, sessionmaker

from sqladmin import Admin, ModelView
from wtforms import FileField


DATABASE_URL = "sqlite:///./shop.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

UPLOAD_DIR = os.path.join("static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def is_allowed_image(filename: str) -> bool:
    ext = os.path.splitext(filename.lower())[1]
    return ext in ALLOWED_EXTENSIONS


def generate_filename(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    return f"{uuid.uuid4().hex}{ext}"


# مدل محصول در دیتابیس
class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    price = Column(Integer, nullable=False)
    image = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    features = Column(Text, nullable=True)


# مدل سفارش در دیتابیس
class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, nullable=False)
    customer_name = Column(String, nullable=False)
    status = Column(String, default="در انتظار بررسی")


Base.metadata.create_all(bind=engine)

app = FastAPI()

# اتصال پوشه استاتیک برای تصاویر
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# مسیر صفحه اصلی
@app.get("/")
def home(request: Request, query: str = ""):
    db = SessionLocal()
    try:
        if query and query.strip():
            products = db.query(Product).filter(Product.name.contains(query.strip())).all()
        else:
            products = db.query(Product).all()
    finally:
        db.close()

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "products": products,
            "query": query
        }
    )


# مسیر ثبت سفارش سریع از طریق API سمت فرانت‌اند
@app.post("/order/{product_id}")
async def create_order(product_id: int):
    db = SessionLocal()
    try:
        # بررسی وجود محصول
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise HTTPException(status_code=404, detail="محصول یافت نشد")
        
        # ایجاد سفارش جدید
        new_order = Order(
            product_id=product.id,
            customer_name="مشتری آنلاین (سفارش سریع)",
            status="در انتظار بررسی"
        )
        db.add(new_order)
        db.commit()
        return {"status": "success", "message": "سفارش شما با موفقیت ثبت شد."}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


# تنظیمات پنل مدیریت محصولات
class ProductAdmin(ModelView, model=Product):
    name = "محصول"
    name_plural = "محصولات"

    column_list = [
        Product.id,
        Product.name,
        Product.price,
        Product.image,
        Product.description,
        Product.features,
    ]

    form_columns = [
        Product.name,
        Product.price,
        Product.image,
        Product.description,
        Product.features,
    ]

    form_overrides = {
        "image": FileField
    }

    async def on_model_change(self, data, model, is_created, request):
        image_file = data.get("image")

        if image_file and hasattr(image_file, "filename") and image_file.filename:
            original_filename = image_file.filename

            if not is_allowed_image(original_filename):
                raise ValueError("فقط فایل‌های عکس مجاز هستند.")

            new_filename = generate_filename(original_filename)
            save_path = os.path.join(UPLOAD_DIR, new_filename)

            with open(save_path, "wb") as buffer:
                shutil.copyfileobj(image_file.file, buffer)

            image_path = f"uploads/{new_filename}"

            data["image"] = image_path
            model.image = image_path
        else:
            if is_created:
                data["image"] = None
                model.image = None
            else:
                data["image"] = model.image


# تنظیمات پنل مدیریت سفارشات
class OrderAdmin(ModelView, model=Order):
    name = "سفارش"
    name_plural = "سفارش‌ها"

    column_list = [
        Order.id,
        Order.product_id,
        Order.customer_name,
        Order.status,
    ]


admin = Admin(app, engine)
admin.add_view(ProductAdmin)
admin.add_view(OrderAdmin)









