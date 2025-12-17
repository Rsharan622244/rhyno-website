from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime 
import smtplib
from email.message import EmailMessage
import stripe
import os
from dotenv import load_dotenv

load_dotenv()
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

def send_prebook_email(data):
    sender = os.getenv("EMAIL_ADDRESS")
    password = os.getenv("EMAIL_PASSWORD")
    receiver = sender   # admin receives mail

    msg = EmailMessage()
    msg["Subject"] = "New Rhyno Pre-Booking"
    msg["From"] = sender
    msg["To"] = receiver

    msg.set_content(f"""
New Pre-Booking Received

Customer Details:
Name: {data['name']}
Email: {data['email']}
Address: {data['address']}
State: {data['state']}
Country: {data['country']}

Products:
{data['products']}
""")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, password)
        server.send_message(msg)


app = Flask(__name__)
app.config["SECRET_KEY"] = "dev-secret-key"  # just for flash messages

# ---- DB CONFIG ----
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(BASE_DIR, "rhyno.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# change these to stronger values before deploying
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "1234"

# ---- MODELS (must be defined before routes and db.create_all()) ----
class PreBooking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(100), nullable=False)
    customer_email = db.Column(db.String(120), nullable=False)
    customer_state = db.Column(db.String(100))
    se03lite_qty = db.Column(db.Integer, default=0)
    se03_qty = db.Column(db.Integer, default=0)
    se03max_qty = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<PreBooking {self.customer_name} - {self.customer_email}>"

# ---- ROUTES ----
@app.route("/")
def home():
    return render_template("home.html")

@app.route("/about")
def about():
    return render_template("aboutus.html")

@app.route("/contact")
def contact():
    return render_template("contactus.html")

@app.route("/compare")
def compare():
    return render_template("compareall.html")

@app.route("/rentals")
def rentals():
    return render_template("rentals.html")

@app.route("/se03lite")
def se03lite():
    return render_template("product1.html")

@app.route("/se03")
def se03():
    return render_template("product2.html")

@app.route("/se03max")
def se03max():
    return render_template("product3.html")

@app.route("/prebook", methods=["GET", "POST"])
def prebook():
    if request.method == "POST":

        # ---- Customer details ----
        customer_name = request.form.get("customer_name")
        customer_email = request.form.get("customer_email")
        customer_address = request.form.get("customer_address")
        customer_state = request.form.get("customer_state")
        customer_country = request.form.get("customer_country")

        # ---- Product quantities ----
        se03lite_qty = int(request.form.get("se03lite_qty") or 0)
        se03_qty = int(request.form.get("se03_qty") or 0)
        se03max_qty = int(request.form.get("se03max_qty") or 0)

        # ---- Basic validation ----
        if not customer_name or not customer_email:
            flash("Name and email are required.", "error")
            return redirect(url_for("prebook"))

        # ---- Build product details string (IMPORTANT) ----
        products = []

        if se03lite_qty > 0:
            products.append(f"SE03 Lite - Qty: {se03lite_qty}")

        if se03_qty > 0:
            products.append(f"SE03 - Qty: {se03_qty}")

        if se03max_qty > 0:
            products.append(f"SE03 Max - Qty: {se03max_qty}")

        product_details = "\n".join(products) if products else "No products selected"

        # ---- Save to database ----
        booking = PreBooking(
            customer_name=customer_name,
            customer_email=customer_email,
            customer_state=customer_state,
            se03lite_qty=se03lite_qty,
            se03_qty=se03_qty,
            se03max_qty=se03max_qty,
        )

        db.session.add(booking)
        db.session.commit()

            # ---- Send backend email (CORRECT PLACE) ----
        try:
            send_prebook_email({
                "name": customer_name,
                "email": customer_email,
                "address": customer_address,
                "state": customer_state,
                "country": customer_country,
                "products": product_details
            })
        except Exception as e:
            print("Email failed (SMTP blocked on Render):", e)


        flash("Pre-booking submitted successfully! Email sent.", "success")
        return redirect(url_for("home"))

    return render_template("paymentgateway.html")


        

@app.route("/create-checkout-session", methods=["POST"])
def create_checkout_session():
    amount = int(float(request.form["amount"]) * 100)  # INR → paise

    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": "inr",
                "product_data": {
                    "name": "Rhyno EV Pre-Booking"
                },
                "unit_amount": amount,
            },
            "quantity": 1,
        }],
        mode="payment",
        success_url=url_for("payment_success", _external=True),
        cancel_url=url_for("prebook", _external=True),
    )

    return redirect(session.url, code=303)

@app.route("/payment-success")
def payment_success():
    return render_template("success.html")

# ---- ADMIN: simple session-based auth (dev only) ----

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["admin"] = True
            flash("Login successful", "success")
            return redirect(url_for("admin_dashboard"))
        else:
            flash("Invalid credentials", "error")
            return redirect(url_for("admin_login"))

    return render_template("admin_login.html")


@app.route("/admin/dashboard")
def admin_dashboard():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    # simple stats
    total = PreBooking.query.count()
    latest = PreBooking.query.order_by(PreBooking.created_at.desc()).limit(5).all()
    return render_template("admin_dashboard.html", total=total, latest=latest)


@app.route("/admin/bookings")
def admin_bookings():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    bookings = PreBooking.query.order_by(PreBooking.created_at.desc()).all()
    return render_template("admin_bookings.html", bookings=bookings)


@app.route("/admin/delete/<int:id>", methods=["POST", "GET"])
def admin_delete(id):
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    booking = PreBooking.query.get(id)
    if booking:
        db.session.delete(booking)
        db.session.commit()
        flash(f"Deleted booking #{id}", "success")
    else:
        flash("Booking not found", "error")
    return redirect(url_for("admin_bookings"))


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    flash("Logged out", "info")
    return redirect(url_for("admin_login"))



# ---- create tables and run app ----
if __name__ == "__main__":
    with app.app_context():
        db.create_all()  # create tables if not exist
    app.run(debug=True)
