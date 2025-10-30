import os
from flask import Flask, request, render_template, redirect, url_for, session, flash
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi

app = Flask(__name__)
app.secret_key = "your_secret_key_here"  # Change this to a random secret key

# MongoDB Atlas Connection Setup
MONGO_URI = "mongodb+srv://tomkarthik1057:sktk1057@kkm.v96sqaq.mongodb.net/?retryWrites=true&w=majority&appName=kkm"
client = MongoClient(MONGO_URI, server_api=ServerApi('1'))

try:
    client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print("MongoDB connection error:", e)

db = client["kkm"]  # Use your database name
user_collection = db["users"]  # Example collection for user data
file_collection = db["files"]   # Example collection for file metadata

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/signup', methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"].strip()
        # Insert user data to MongoDB
        user_collection.insert_one({"username": username, "password": password})
        flash("Signup successful! Please log in.")
        return redirect(url_for("login"))
    return render_template("signup.html")

@app.route('/login', methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"].strip()
        user = user_collection.find_one({"username": username, "password": password})
        if user:
            session['username'] = username
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid username or password.")
    return render_template("login.html")

@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))
    username = session['username']
    files = list(file_collection.find({"username": username}))
    return render_template("dashboard.html", files=files, username=username)

@app.route('/upload', methods=["GET", "POST"])
def upload():
    if 'username' not in session:
        return redirect(url_for('login'))
    username = session['username']
    if request.method == "POST":
        file = request.files['file']
        if file:
            filename = file.filename
            # Normally save file somewhere (e.g., cloud); here, just store metadata
            file_collection.insert_one({
                "username": username,
                "filename": filename
            })
            flash(f"File '{filename}' uploaded and metadata saved.")
    return render_template("upload.html", username=username)

@app.route('/logout')
def logout():
    session.pop('username', None)
    flash("Logged out successfully.")
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True, threaded=True, host='127.0.0.1', port=5000)
