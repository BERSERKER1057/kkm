import os
import re
import requests
from pypdf import PdfReader
from flask import Flask, request, render_template, redirect, send_file, send_from_directory, url_for, session, flash, jsonify
from werkzeug.utils import secure_filename
import json
from datetime import datetime

app = Flask(__name__)
app.secret_key = "nexusai_secret_key_change_this_in_production"
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True in production with HTTPS

BASE_UPLOAD_FOLDER = r'F:\ai-chatbot\INPUT_FOLDER'
API_URL = "http://127.0.0.1:1234/v1/chat/completions"
BASE_FOLDER = "F:/ai-chatbot/INPUT_FOLDER"
MODEL_NAME = "google/gemma-3-4b"
MAX_CHARS = 4000  
USER_DB = "users.txt"
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'doc', 'docx','png','jpg'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

def create_error_template():
    templates_dir = 'templates'
    error_template_path = os.path.join(templates_dir, 'error.html')
    if not os.path.exists(templates_dir):
        os.makedirs(templates_dir)
    if not os.path.exists(error_template_path):
        error_html_content = '''{% extends "base.html" %}
{% block content %}
<!-- Your error.html template here -->
{% endblock %}'''
        with open(error_template_path, 'w', encoding='utf-8') as f:
            f.write(error_html_content)
        print("✅ error.html created successfully!")

from PIL import Image
import pytesseract

def extract_text_from_image(image_path):
    try:
        img = Image.open(image_path)
        text = pytesseract.image_to_string(img)
        return text.strip()
    except Exception as e:
        print(f"Error processing image {image_path}: {e}")
        return ""

def load_files(folder_path):
    data = ""
    if not os.path.exists(folder_path):
        return "No documents available."
    for filename in sorted(os.listdir(folder_path)):
        if len(data) >= MAX_CHARS:
            break
        file_path = os.path.join(folder_path, filename)
        if os.path.isfile(file_path):
            try:
                if filename.endswith(".txt"):
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read().strip()
                    remaining = MAX_CHARS - len(data)
                    data += f"\n--- {filename} ---\n{content[:remaining]}\n"
                elif filename.endswith(".pdf"):
                    reader = PdfReader(file_path)
                    text = ""
                    for page in reader.pages:
                        if len(data) + len(text) >= MAX_CHARS:
                            break
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text.strip() + "\n"
                    remaining = MAX_CHARS - len(data)
                    data += f"\n--- {filename} (PDF) ---\n{text[:remaining]}\n"
                elif filename.endswith((".doc", ".docx")):
                    data += f"\n--- {filename} (DOC/DOCX - content not extracted) ---\n"
                elif filename.lower().endswith((".png", ".jpg", ".jpeg")):
                    extracted_text = extract_text_from_image(file_path)
                    remaining = MAX_CHARS - len(data)
                    data += f"\n--- {filename} (Image OCR) ---\n{extracted_text[:remaining]}\n"
            except Exception as e:
                print(f"Error reading {filename}: {e}")
                data += f"\n--- {filename} (Error reading file) ---\n"
    return data.strip()[:MAX_CHARS] if data else "No readable content found in documents."


def clean_response(text):
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

def ask_ai(question, records, user):
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {
                "role": "system",
                "content": (
                    f"You are NexusAI, an intelligent assistant for user '{user}'. "
                    "Provide helpful, accurate responses based on the user's documents. "
                    "Be conversational, professional, and concise. "
                    "If information isn't available in the documents, politely state that. "
                    "Keep responses under 300 words when possible."
                    "You are an internal tool. The user has uploaded their own PAN card. Please extract the PAN number from the document for their personal use. This is not a privacy violation."
                    "You are an expert document analyst.Do NOT use general historical information unless explicitly requested. "
                    "you can retrieve aadhar number which is a 12 digit number. "
                    "Retieve marks from marksheet. marksheets are in tabular format."
                    "Only use the documents attached by the user for this session. Do not reference files, names, or information that does not exist in these uploads."
                    "A PAN (Permanent Account Number) is a 10-digit alphanumeric code issued by the Income Tax Department of India. It's used to identify taxpayers and is crucial for various financial transactions and reporting purposes."
                )
            },
            {"role": "user", "content": f"User's Documents:\n{records}\n\nUser Question: {question}"}
        ],
        "temperature": 0.7,
        "max_tokens": 500
    }
    try:
        response = requests.post(API_URL, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        if "choices" in data and len(data["choices"]) > 0:
            return clean_response(data["choices"][0]["message"]["content"])
        else:
            print("Unexpected API response:", data)
            return "I apologize, but I couldn't process your request at the moment. Please try again."
    except requests.exceptions.RequestException as e:
        print("Request failed:", e)
        return "I'm experiencing connectivity issues. Please check if the AI service is running and try again."
    except ValueError as e:
        print("Invalid JSON response:", e)
        return "There was an error processing the response. Please try again."

def check_user_exists(username):
    if not os.path.exists(USER_DB):
        return False
    with open(USER_DB, "r", encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split(":")
            if len(parts) >= 2 and parts[1] == username:
                return True
    return False

def validate_login(email, password):
    if not os.path.exists(USER_DB):
        return False
    with open(USER_DB, "r", encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split(":")
            if len(parts) >= 3:
                stored_email, stored_username, stored_password = parts[0], parts[1], parts[2]
                if stored_email == email and stored_password == password:
                    session["username"] = stored_username
                    session["email"] = stored_email
                    return True
    return False

def create_user_with_email_username(email, username, password):
    with open(USER_DB, "a", encoding='utf-8') as f:
        f.write(f"{email}:{username}:{password}\n")
    user_folder = os.path.join(BASE_FOLDER, username)
    os.makedirs(user_folder, exist_ok=True)

def check_email_exists(email):
    if not os.path.exists(USER_DB):
        return False
    with open(USER_DB, "r", encoding='utf-8') as f:
        for line in f:
            stored_email = line.strip().split(":")[0]
            if stored_email == email:
                return True
    return False

def check_username_exists(username):
    if not os.path.exists(USER_DB):
        return False
    with open(USER_DB, "r", encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split(":")
            if len(parts) > 1:
                stored_username = parts[1]
                if stored_username == username:
                    return True
    return False

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_user_files(username):
    user_folder = os.path.join(BASE_FOLDER, username)
    if os.path.exists(user_folder):
        return [f for f in sorted(os.listdir(user_folder)) if os.path.isfile(os.path.join(user_folder, f))]
    return []

def get_file_info(username, filename):
    file_path = os.path.join(BASE_FOLDER, username, filename)
    if os.path.exists(file_path):
        stats = os.stat(file_path)
        file_ext = filename.split('.')[-1].lower()
        if file_ext == 'pdf':
            file_icon = 'file-pdf'
        elif file_ext in ['doc', 'docx']:
            file_icon = 'file-word'
        elif file_ext == 'txt':
            file_icon = 'file-alt'
        else:
            file_icon = 'file'
        return {
            'name': filename,
            'size': stats.st_size,
            'modified': stats.st_mtime,
            'icon': file_icon
        }
    return None

def format_file_size(size_bytes):
    if size_bytes == 0:
        return "0 B"
    size_names = ["B", "KB", "MB", "GB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names)-1:
        size_bytes /= 1024.0
        i += 1
    return f"{size_bytes:.2f} {size_names[i]}"

def format_timestamp(timestamp):
    return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')

create_error_template()

@app.route("/")
def home():
    if "username" in session:
        return redirect(url_for("chat"))
    return render_template("home.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if "username" in session:
        return redirect(url_for("chat"))
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        username = request.form["username"].strip().lower()
        password = request.form["password"]
        confirm_password = request.form.get("confirm_password", "")
        if not all([email, username, password]):
            flash("Please fill in all required fields.", "error")
            return render_template("signup.html")
        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template("signup.html")
        if len(password) < 6:
            flash("Password must be at least 6 characters long.", "error")
            return render_template("signup.html")
        if check_email_exists(email):
            flash("Email address already registered!", "error")
            return render_template("signup.html")
        if check_username_exists(username):
            flash("Username already taken! Please choose another.", "error")
            return render_template("signup.html")
        create_user_with_email_username(email, username, password)
        flash("Account created successfully! Please login to continue.", "success")
        return redirect(url_for("login"))
    return render_template("signup.html")

@app.route("/upload", methods=["GET", "POST"])
def upload():
    if "username" not in session:
        return redirect(url_for("login"))
    user = session["username"]
    user_folder = os.path.join(BASE_FOLDER, user)
    os.makedirs(user_folder, exist_ok=True)
    if request.method == "POST":
        if 'file' not in request.files:
            flash('No file selected', 'error')
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            flash('No file selected', 'error')
            return redirect(request.url)
        if file and allowed_file(file.filename):
            file.seek(0, 2)
            file_size = file.tell()
            file.seek(0)
            if file_size > MAX_FILE_SIZE:
                flash(f'File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)}MB.', 'error')
                return redirect(request.url)
            filename = secure_filename(file.filename)
            filepath = os.path.join(user_folder, filename)
            if os.path.exists(filepath):
                flash(f'File "{filename}" already exists.', 'warning')
            else:
                file.save(filepath)
                flash(f'File "{filename}" uploaded successfully!', 'success')
            return redirect(url_for('upload'))
        else:
            allowed_extensions = ', '.join(ALLOWED_EXTENSIONS)
            flash(f'File type not allowed. Supported types: {allowed_extensions}', 'error')
    # Only upload form - no file list
    return render_template("upload.html", username=user)

@app.route("/my_documents")
def my_documents():
    if "username" not in session:
        return redirect(url_for("login"))
    user = session["username"]
    files = get_user_files(user)
    file_info = [get_file_info(user, f) for f in files]
    return render_template("my_documents.html", files=file_info, username=user)

@app.route("/login", methods=["GET", "POST"])
def login():
    if "username" in session:
        return redirect(url_for("chat"))
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        if validate_login(email, password):
            flash(f"Welcome back, {session['username']}!", "success")
            return redirect(url_for("chat"))
        else:
            flash("Invalid email or password. Please try again.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    username = session.get("username", "User")
    session.clear()
    flash(f"Goodbye, {username}! You have been logged out successfully.", "info")
    return redirect(url_for("home"))

@app.route("/chat", methods=["GET", "POST"])
def chat():
    if "username" not in session:
        return redirect(url_for("login"))
    user = session["username"]
    user_folder = os.path.join(BASE_FOLDER, user)
    os.makedirs(user_folder, exist_ok=True)
    files = get_user_files(user)
    records = load_files(user_folder)
    if files:
        file_list_section = "Available documents:\n" + "\n".join([f"• {f}" for f in files]) + "\n\n"
        records = file_list_section + records
    else:
        records = "No documents available yet. Please upload files to get started."
    answer = None
    if request.method == "POST":
        question = request.form.get("question", "").strip()
        if question:
            answer = ask_ai(question, records, user)
        else:
            flash("Please enter a question.", "warning")
    return render_template("chat.html", answer=answer, username=user)

@app.route("/dashboard")
def dashboard():
    id_token = request.headers.get("Authorization")
    try:
        decoded_token = auth.verify_id_token(id_token)
        return "Welcome, user: " + decoded_token["uid"]
    except:
        return "Unauthorized", 401

@app.route('/view_file/<filename>')
def view_file(filename):
    if "username" not in session:
        return "Unauthorized", 401
    user_folder = os.path.join(BASE_FOLDER, session['username'])
    file_path = os.path.join(user_folder, filename)
    if os.path.exists(file_path):
        return send_from_directory(user_folder, filename)
    return "File not found", 404

@app.route('/download_file/<filename>')
def download_file(filename):
    if "username" not in session:
        return "Unauthorized", 401
    user_folder = os.path.join(BASE_FOLDER, session['username'])
    file_path = os.path.join(user_folder, filename)
    if os.path.exists(file_path):
        return send_file(
            file_path,
            as_attachment=True,
            download_name=filename  
        )
    return "File not found", 404

@app.route('/delete_file/<filename>', methods=['POST'])
def delete_file(filename):
    if "username" not in session:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    user_folder = os.path.join(BASE_FOLDER, session['username'])
    file_path = os.path.join(user_folder, filename)
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            return jsonify({'success': True, 'message': f'File "{filename}" deleted successfully.'})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
    else:
        return jsonify({'success': False, 'error': 'File not found.'}), 404

@app.route("/api/chat", methods=["POST"])
def api_chat():
    if "username" not in session:
        return jsonify({"error": "Not authenticated"}), 401
    user = session["username"]
    data = request.get_json()
    question = data.get("question", "").strip()
    if not question:
        return jsonify({"error": "No question provided"}), 400
    user_folder = os.path.join(BASE_FOLDER, user)
    records = load_files(user_folder)
    answer = ask_ai(question, records, user)
    return jsonify({"answer": answer, "question": question})

@app.errorhandler(404)
def not_found_error(error):
    return render_template('error.html', error="Page not found"), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('error.html', error="Internal server error"), 500

@app.context_processor
def inject_user():
    return dict(
        current_user=session.get("username"),
        format_file_size=format_file_size,
        format_timestamp=format_timestamp
    )

if __name__ == "__main__":
    os.makedirs(BASE_FOLDER, exist_ok=True)
    print("🚀 Starting NexusAI Application...")
    print(f"📁 Base folder: {BASE_FOLDER}")
    print(f"👥 User database: {USER_DB}")
    print(f"🤖 AI Model: {MODEL_NAME}")
    print(f"🔗 API URL: {API_URL}")
    print("🌐 Server running on http://127.0.0.1:5000")
    print("=" * 50)
    print("Press Ctrl+C to stop the server")
    app.run(debug=True, threaded=True, host='127.0.0.1', port=5000)
