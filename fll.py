import pickle
import requests
import json
import os
from datetime import datetime
from twilio.rest import Client
import streamlit as st
import smtplib
from deep_translator import GoogleTranslator
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
import hashlib
import re
from streamlit import session_state as state
import pandas as pd

# Load environment variables
load_dotenv()

# Enhanced language dictionary with Indian languages
language_dict = {
    'English': 'en',
    'Hindi (हिंदी)': 'hi',
    'Bengali (বাংলা)': 'bn',
    'Telugu (తెలుగు)': 'te', 
    'Marathi (मराठी)': 'mr',
    'Tamil (தமிழ்)': 'ta',
    'Urdu (اردو)': 'ur',
    'Gujarati (ગુજરાતી)': 'gu',
    'Kannada (ಕನ್ನಡ)': 'kn',
    'Odia (ଓଡ଼ିଆ)': 'or',
    'Punjabi (ਪੰਜਾਬੀ)': 'pa',
    'Malayalam (മലയാളം)': 'ml',
    'Assamese (অসমীয়া)': 'as'
}

# --- UTILITY FUNCTIONS ---
def hash_password(password):
    """Hash a password using SHA-256 with salt"""
    salt = "flood_alert_salt"
    return hashlib.sha256((password + salt).encode()).hexdigest()

def validate_email(email):
    """Basic email validation"""
    pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    return re.match(pattern, email)

def get_weather_icon(icon_code):
    """Get weather icon from OpenWeatherMap code"""
    if not icon_code:
        return "🌤️"
    icon_map = {
        '01d': '☀️', '01n': '🌙',
        '02d': '⛅', '02n': '⛅',
        '03d': '☁️', '03n': '☁️',
        '04d': '☁️', '04n': '☁️',
        '09d': '🌧️', '09n': '🌧️',
        '10d': '🌦️', '10n': '🌦️',
        '11d': '⛈️', '11n': '⛈️',
        '13d': '❄️', '13n': '❄️',
        '50d': '🌫️', '50n': '🌫️'
    }
    return icon_map.get(icon_code, '🌤️')

def translate_message(text, dest_lang):
    """Translate message to selected language using Google Translator"""
    if dest_lang == 'en' or not text:
        return text
    
    try:
        # Split long text into chunks if needed (Google Translator has character limits)
        max_chunk_size = 5000  # Google's limit is 5000 characters per request
        if len(text) <= max_chunk_size:
            return GoogleTranslator(source='auto', target=dest_lang).translate(text)
        else:
            # Split into sentences and translate chunks
            sentences = text.split('. ')
            translated_chunks = []
            current_chunk = ""
            
            for sentence in sentences:
                if len(current_chunk) + len(sentence) < max_chunk_size:
                    current_chunk += sentence + ". "
                else:
                    if current_chunk:
                        translated = GoogleTranslator(source='auto', target=dest_lang).translate(current_chunk)
                        translated_chunks.append(translated)
                    current_chunk = sentence + ". "
            
            if current_chunk:
                translated = GoogleTranslator(source='auto', target=dest_lang).translate(current_chunk)
                translated_chunks.append(translated)
            
            return " ".join(translated_chunks)
    except Exception as e:
        st.error(f"Translation failed: {str(e)}")
        return f"[Translation Failed] {text}"

# --- DATA MANAGEMENT FUNCTIONS ---
def load_users():
    """Load user data from JSON file with proper city field handling"""
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r') as f:
                users = json.load(f)
                # Ensure all users have 'city' field
                for email, user_data in users.items():
                    if 'city' not in user_data:
                        user_data['city'] = 'Unknown City'
                # Ensure admin account exists
                if ADMIN_EMAIL not in users:
                    users[ADMIN_EMAIL] = create_admin_user()
                    save_users(users)
                return users
    except (json.JSONDecodeError, FileNotFoundError):
        users = {ADMIN_EMAIL: create_admin_user()}
        save_users(users)
        return users
    return {}

def create_admin_user():
    """Create admin user with all required fields"""
    return {
        'city': 'Admin Headquarters',
        'password': hash_password(os.getenv('ADMIN_PASSWORD', 'admin123')),
        'alerts': True,
        'is_admin': True
    }

def save_users(users):
    """Save user data to JSON file"""
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2)

def save_status(status, city_name, alert_type, language='en'):
    """Save alert history with all required fields"""
    entry = {
        'city': city_name or 'Unknown location',
        'status': status or 'unknown',
        'type': alert_type or 'unknown',
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'language': language
    }

    history = []
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, 'r') as f:
                history = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            history = []

    history.append(entry)
    with open(STATUS_FILE, 'w') as f:
        json.dump(history, f, indent=2)

# --- EMAIL FUNCTIONS ---
def send_welcome_email(to_email, city):
    """Send welcome email after registration"""
    try:
        sender_email = os.getenv("SENDER_EMAIL")
        sender_password = os.getenv("SENDER_PASSWORD")
        
        if not sender_email or not sender_password:
            st.error("Email credentials not configured")
            return False

        subject = f"🌊 Welcome to Smart Flood Alert System - {city}"
        html_content = f"""
<html><body>
    <h2 style="color:#2e86c1;">Welcome to Smart Flood Alert System</h2>
    <p>Thank you for registering to receive flood alerts for <strong>{city}</strong>.</p>
    <div style="background-color:#f2f4f4; padding:15px; border-radius:5px;">
        <h3 style="color:#2e86c1;">Your Account Details:</h3>
        <ul>
            <li><strong>Registered City:</strong> {city}</li>
            <li><strong>Notification Email:</strong> {to_email}</li>
        </ul>
    </div>
    <p>You will now receive automated alerts when flood risks are detected in your area.</p>
    <p style="color:#5d6d7e;"><em>This is an automated message - please do not reply</em></p>
</body></html>"""

        message = MIMEMultipart()
        message["From"] = sender_email
        message["To"] = to_email
        message["Subject"] = subject
        message.attach(MIMEText(html_content, "html"))

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, to_email, message.as_string())
            st.toast("Welcome email sent successfully!", icon="✉️")
        return True
    except Exception as e:
        st.error(f"Failed to send welcome email: {str(e)}")
        return False

def send_alert_email(to_email, city, alert_message):
    """Send flood alert email"""
    try:
        sender_email = os.getenv("SENDER_EMAIL")
        sender_password = os.getenv("SENDER_PASSWORD")
        
        subject = f"🚨 Flood Alert for {city}"
        html_content = f"""
<html><body>
    <h2 style="color:#e74c3c;">Flood Alert Notification</h2>
    <p><strong>Location:</strong> {city}</p>
    <div style="background-color:#fdebd0; padding:15px; border-radius:5px;">
        <h3 style="color:#e67e22;">Alert Message:</h3>
        <p>{alert_message}</p>
    </div>
    <p>Please take necessary precautions.</p>
    <p style="color:#5d6d7e;"><em>This is an automated alert - do not reply</em></p>
</body></html>"""

        message = MIMEMultipart()
        message["From"] = sender_email
        message["To"] = to_email
        message["Subject"] = subject
        message.attach(MIMEText(html_content, "html"))

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, to_email, message.as_string())
        return True
    except Exception as e:
        st.error(f"Failed to send alert email: {str(e)}")
        return False

def send_bulk_emails(recipients, city, alert_message):
    """Send emails to multiple recipients from CSV"""
    success_count = 0
    failure_count = 0
    
    for recipient in recipients:
        email = recipient.get('email', '').strip()
        if not email or '@' not in email:
            failure_count += 1
            continue
            
        try:
            if send_alert_email(email, city, alert_message):
                success_count += 1
            else:
                failure_count += 1
        except Exception as e:
            st.error(f"Error sending to {email}: {str(e)}")
            failure_count += 1
    
    return success_count, failure_count

def read_recipients_from_csv(file):
    """Read recipients from CSV file (name and email only)"""
    try:
        df = pd.read_csv(file)
        df.columns = df.columns.str.lower()
        
        required_columns = ['name', 'email']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            st.error(f"CSV file must contain these columns: {', '.join(required_columns)}")
            return None
        
        recipients = []
        for _, row in df.iterrows():
            recipient = {
                'name': str(row['name']).strip(),
                'email': str(row['email']).strip().lower()
            }
            recipients.append(recipient)
        
        return recipients
        
    except Exception as e:
        st.error(f"Error reading CSV file: {str(e)}")
        return None

# --- FLOOD ALERT FUNCTIONS ---
def load_model():
    """Load the trained flood prediction model"""
    try:
        with open(MODEL_FILE, "rb") as file:
            return pickle.load(file)
    except Exception as e:
        st.error(f"❌ Error loading model: {e}")
        return None

def get_weather_data_by_name(city_name):
    """Fetch weather data from OpenWeatherMap API"""
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city_name}&appid={API_KEY}&units=metric"
        response = requests.get(url, timeout=10)

        if response.status_code != 200:
            st.error(f"❌ API call failed: {response.status_code} - {response.text}")
            return None

        data = response.json()
        return {
            'temperature': data.get('main', {}).get('temp', 0),
            'humidity': data.get('main', {}).get('humidity', 0),
            'pressure': data.get('main', {}).get('pressure', 0),
            'wind_speed': data.get('wind', {}).get('speed', 0),
            'rainfall': data.get('rain', {}).get('1h', 0) if data.get('rain') else 0,
            'weather_desc': data.get('weather', [{}])[0].get('description', ''),
            'icon': data.get('weather', [{}])[0].get('icon', '')
        }

    except Exception as e:
        st.error(f"❌ Error fetching weather data: {e}")
        return None

def predict_flood(weather_data, model):
    """Predict flood risk using ML model"""
    if not model or not weather_data:
        return False
    
    try:
        features = [[
            weather_data['temperature'],
            weather_data['humidity'],
            weather_data['pressure'],
            weather_data['rainfall'],
            weather_data['wind_speed']
        ]]
        prediction = model.predict(features)
        return prediction[0] == 1
    except Exception as e:
        st.error(f"❌ Error during prediction: {e}")
        return False

def check_flood_risk_by_rain(rainfall):
    """Simple threshold-based flood check"""
    THRESHOLD = 50  # mm rainfall in last 1 hour
    return rainfall > THRESHOLD

def send_sms(to_phone, message):
    """Send SMS alert via Twilio"""
    try:
        client.messages.create(
            body=message,
            from_=twilio_number,
            to=to_phone
        )
        st.success(f"✅ SMS sent to {to_phone}")
        return True
    except Exception as e:
        st.error(f"❌ Failed to send SMS to {to_phone}: {e}")
        return False

# --- CONFIGURATION ---
MODEL_FILE = "flood_model.pkl"
API_KEY = os.getenv('WEATHER_API_KEY', 'a6f81aff8e354cf14db2c448cbb27e5c')
USERS_FILE = "users_data.json"
STATUS_FILE = 'status_history.json'
ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', 'admin@floodalert.com')

# Twilio Configuration
account_sid = os.getenv('TWILIO_ACCOUNT_SID', 'ACa87356bcc92f8c0c5b484c4d07847b89')
auth_token = os.getenv('TWILIO_AUTH_TOKEN', '76ee8346337a83745229caecdee69a65')
twilio_number = os.getenv('TWILIO_NUMBER', '+13305835246')

client = Client(account_sid, auth_token)

# --- STREAMLIT UI ---
def main():
    st.set_page_config(page_title="Smart Flood Alert", page_icon="🌊", layout="wide")

    # Custom CSS
    st.markdown("""
    <style>
        .admin-panel { background-color: #fff3cd; padding: 15px; border-radius: 10px; border-left: 5px solid #ffc107; }
        .user-panel { background-color: #e7f5ff; padding: 15px; border-radius: 10px; border-left: 5px solid #4dabf7; }
        .flood-alert { color: white; background-color: #ff4b4b; padding: 15px; border-radius: 10px; }
        .safe-alert { color: white; background-color: #4CAF50; padding: 15px; border-radius: 10px; }
        .weather-card { padding: 15px; border-radius: 10px; box-shadow: 0 4px 8px 0 rgba(0,0,0,0.2); }
        .history-item { padding: 10px; margin: 5px 0; border-radius: 5px; background-color: #f0f2f6; }
    </style>
    """, unsafe_allow_html=True)

    # Initialize session state with proper city handling
    if 'users' not in state:
        state.users = load_users()

    if 'auth' not in state:
        state.auth = {
            'authenticated': False,
            'user_email': None,
            'user_city': None,
            'login_attempts': 0,
            'language': 'en',
            'is_admin': False
        }

    # --- MAIN APP ---
    st.title("🌊 Smart Flood Alert System")
    st.markdown("Monitor flood risks in your city")

    # Sidebar - Authentication
    with st.sidebar:
        st.image("https://img.icons8.com/color/96/000000/flood.png", width=80)
        st.title("Account")
        
        if not state.auth['authenticated']:
            tab1, tab2, tab3 = st.tabs(["User Login", "User Register", "Admin Login"])
            
            with tab1:
                with st.form("user_login_form"):
                    login_email = st.text_input("Email")
                    login_password = st.text_input("Password", type="password")
                    login_submitted = st.form_submit_button("Sign In")
                    
                    if login_submitted:
                        user = state.users.get(login_email.strip().lower())
                        if user and user['password'] == hash_password(login_password) and not user.get('is_admin', False):
                            # Safely get city with default value
                            user_city = user.get('city', 'Unknown City')
                            state.auth = {
                                'authenticated': True,
                                'user_email': login_email,
                                'user_city': user_city,
                                'login_attempts': 0,
                                'language': 'en',
                                'is_admin': False
                            }
                            st.success("Login successful!")
                            st.rerun()
                        else:
                            st.error("Invalid credentials")
            
            with tab2:
                with st.form("register_form"):
                    st.markdown("#### Create New Account")
                    reg_email = st.text_input("Email Address")
                    reg_city = st.text_input("Your City", placeholder="Enter your city name")
                    reg_password = st.text_input("Create Password", type="password", 
                                              help="At least 6 characters")
                    reg_confirm = st.text_input("Confirm Password", type="password")
                    reg_submitted = st.form_submit_button("Register")
                    
                    if reg_submitted:
                        if not all([reg_email, reg_city, reg_password, reg_confirm]):
                            st.error("All fields are required")
                        elif not validate_email(reg_email):
                            st.error("Please enter a valid email address")
                        elif len(reg_password) < 6:
                            st.error("Password must be at least 6 characters")
                        elif reg_password != reg_confirm:
                            st.error("Passwords do not match")
                        elif reg_email.lower() in state.users:
                            st.error("Email already registered")
                        else:
                            state.users[reg_email.lower()] = {
                                'city': reg_city,
                                'password': hash_password(reg_password),
                                'alerts': True,
                                'is_admin': False
                            }
                            save_users(state.users)
                            
                            if send_welcome_email(reg_email, reg_city):
                                st.success("Account created successfully! Please sign in.")
                            else:
                                st.success("Account created but welcome email failed")

            with tab3:
                with st.form("admin_login_form"):
                    admin_email = st.text_input("Admin Email")
                    admin_password = st.text_input("Admin Password", type="password")
                    admin_submitted = st.form_submit_button("Admin Login")
                    
                    if admin_submitted:
                        user = state.users.get(admin_email.strip().lower())
                        if user and user['password'] == hash_password(admin_password) and user.get('is_admin', False):
                            state.auth = {
                                'authenticated': True,
                                'user_email': admin_email,
                                'user_city': user.get('city', 'Admin Headquarters'),
                                'login_attempts': 0,
                                'language': 'en',
                                'is_admin': True
                            }
                            st.success("Admin login successful!")
                            st.rerun()
                        else:
                            st.error("Invalid admin credentials")

        else:
            if state.auth['is_admin']:
                st.success(f"👑 Admin Dashboard ({state.auth['user_email']})")
                
                # Language selection dropdown for admin
                selected_language = st.selectbox(
                    "Alert Language Preference",
                    options=list(language_dict.keys()),
                    index=list(language_dict.values()).index(state.auth.get('language', 'en')),
                    key="admin_lang_select"
                )
                state.auth['language'] = language_dict[selected_language]
                
                # Show translation preview
                if st.checkbox("Preview translation", key="preview_translation"):
                    test_text = "Flood alert! Heavy rainfall detected. Please move to safer location."
                    translated = translate_message(test_text, state.auth['language'])
                    st.info(f"Translation preview ({selected_language}):")
                    st.write(f"Original: {test_text}")
                    st.write(f"Translated: {translated}")
            else:
                st.success(f"👤 User Account ({state.auth['user_email']})")
            
            if st.button("Sign Out"):
                state.auth['authenticated'] = False
                st.rerun()
            
            with st.expander("Account Settings"):
                user_data = state.users[state.auth['user_email']]
                st.write(f"**Registered City:** {user_data.get('city', 'Unknown City')}")
                
                if not state.auth['is_admin']:
                    receive_alerts = st.toggle(
                        "Receive Email Alerts",
                        value=user_data.get('alerts', True),
                        key="alert_toggle"
                    )
                    if receive_alerts != user_data.get('alerts', True):
                        user_data['alerts'] = receive_alerts
                        save_users(state.users)
                        st.toast("Notification preferences updated!")
            
            if not state.auth['is_admin']:
                with st.expander("Change Password"):
                    with st.form("change_password_form"):
                        old_pass = st.text_input("Current Password", type="password")
                        new_pass = st.text_input("New Password", type="password")
                        confirm_pass = st.text_input("Confirm New Password", type="password")
                        change_submitted = st.form_submit_button("Update Password")
                        
                        if change_submitted:
                            user = state.users[state.auth['user_email']]
                            if user['password'] != hash_password(old_pass):
                                st.error("Incorrect current password")
                            elif new_pass != confirm_pass:
                                st.error("New passwords don't match")
                            elif len(new_pass) < 6:
                                st.error("Password must be at least 6 characters")
                            else:
                                user['password'] = hash_password(new_pass)
                                save_users(state.users)
                                st.success("Password updated successfully!")
        
            st.subheader("🔔 Alert History")
            if st.button("View History"):
                if os.path.exists(STATUS_FILE):
                    with open(STATUS_FILE) as f:
                        try:
                            history = json.load(f)
                            st.subheader("Recent Alerts")
                            for record in history[-5:][::-1]:
                                city = record.get('city', 'Unknown location')
                                status = record.get('status', 'unknown')
                                alert_type = record.get('type', 'unknown')
                                timestamp = record.get('timestamp', 'unknown time')
                                lang = record.get('language', 'en')
                                
                                status_color = "🔴" if status == 'alert' else "🟢"
                                with st.container():
                                    st.markdown(f"""
                                    <div class="history-item">
                                        <strong>{status_color} {city}</strong><br>
                                        Type: {alert_type}<br>
                                        Status: {status}<br>
                                        Language: {lang}<br>
                                        <small>{timestamp}</small>
                                    </div>
                                    """, unsafe_allow_html=True)
                        except json.JSONDecodeError:
                            st.error("Error reading history file")
                else:
                    st.info("No alert history found")

    # Load ML Model
    model = load_model()

    # Main Content
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📍 City Monitoring")
        
        city_name = st.text_input(
            "Enter city name", 
            value=state.auth.get('user_city', ''),
            key="city_input"
        )
        
        if city_name:
            weather_data = get_weather_data_by_name(city_name)
            
            if weather_data:
                st.success(f"Weather data retrieved for {city_name}")
                
                st.markdown(f"""
                <div class="weather-card">
                    <h3>{get_weather_icon(weather_data['icon'])} Current Weather</h3>
                    <p>🌡️ Temperature: {weather_data['temperature']}°C</p>
                    <p>💧 Humidity: {weather_data['humidity']}%</p>
                    <p>⬇️ Pressure: {weather_data['pressure']} hPa</p>
                    <p>💨 Wind Speed: {weather_data['wind_speed']} m/s</p>
                    <p>🌧️ Rainfall (last 1h): {weather_data['rainfall']:.2f} mm</p>
                    <p>🔹 Conditions: {weather_data['weather_desc'].title()}</p>
                </div>
                """, unsafe_allow_html=True)
                
                ml_prediction = predict_flood(weather_data, model)
                rain_prediction = check_flood_risk_by_rain(weather_data['rainfall'])
                flood_risk = ml_prediction or rain_prediction
                
                if flood_risk:
                    st.markdown("<div class='flood-alert'>⚠️ FLOOD RISK DETECTED! Immediate action recommended</div>", unsafe_allow_html=True)
                    alert_status = 'alert'
                    base_msg = f"URGENT: Flood alert for {city_name}. Heavy rainfall ({weather_data['rainfall']:.1f}mm) detected. Move to safer location immediately. Avoid river areas."
                else:
                    st.markdown("<div class='safe-alert'>✅ No flood risk detected. Conditions are safe</div>", unsafe_allow_html=True)
                    alert_status = 'safe'
                    base_msg = f"Weather update for {city_name}: No flood risk currently. Rainfall: {weather_data['rainfall']:.1f}mm. Stay vigilant."

    with col2:
        if state.auth['authenticated']:
            if state.auth['is_admin']:
                # ADMIN ALERT PANEL
                with st.container():
                    st.markdown('<div class="admin-panel">', unsafe_allow_html=True)
                    st.subheader("👑 Admin Alert Dashboard")
                    
                    # Display current language selection
                    current_lang = [k for k, v in language_dict.items() if v == state.auth['language']][0]
                    st.info(f"Alerts will be sent in: {current_lang}")
                    
                    # Bulk Email Section
                    st.subheader("Bulk Email Alerts")
                    uploaded_file = st.file_uploader("Upload CSV with recipients (name, email)", type="csv")
                    
                    if uploaded_file is not None:
                        recipients = read_recipients_from_csv(uploaded_file)
                        if recipients:
                            st.success(f"Loaded {len(recipients)} recipients")
                            
                            with st.expander("View Recipients"):
                                preview_df = pd.DataFrame({
                                    'Name': [r['name'] for r in recipients[:5]],
                                    'Email': [r['email'] for r in recipients[:5]]
                                })
                                st.dataframe(preview_df)
                            
                            if st.button("📧 Send Bulk Emails", type="primary"):
                                with st.spinner(f"Sending emails to {len(recipients)} recipients..."):
                                    # Translate the message to selected language
                                    alert_msg = translate_message(base_msg, state.auth['language'])
                                    email_success, email_failures = send_bulk_emails(
                                        recipients,
                                        city_name,
                                        alert_msg
                                    )
                                    
                                    st.success(f"""
                                    Bulk emails sent:
                                    - Successful: {email_success}
                                    - Failed: {email_failures}
                                    """)
                                    
                                    if email_success > 0:
                                        save_status(
                                            alert_status,
                                            city_name,
                                            f"BulkEmail({email_success})",
                                            state.auth['language']
                                        )
                    
                    # Individual Alert Section (Admin-only)
                    st.subheader("Individual Alerts")
                    if st.checkbox("Include SMS alert", key="sms_checkbox"):
                        phone_number = st.text_input("Mobile number (with country code)", 
                                                   placeholder="e.g., +919876543210")
                    else:
                        phone_number = None
                        
                    email_address = st.text_input("Email address (for alerts)", 
                                                placeholder="user@example.com")
                    
                    if st.button("Send Alert", type="primary"):
                        if not city_name:
                            st.warning("Please enter a city name first")
                        elif not phone_number and not email_address:
                            st.warning("Please enter at least one contact method")
                        else:
                            with st.spinner("Sending alerts..."):
                                sms_success = not bool(phone_number)
                                email_success = not bool(email_address)
                                
                                # Translate the message to selected language
                                translated_msg = translate_message(base_msg, state.auth['language'])
                                
                                if phone_number:
                                    sms_success = send_sms(phone_number, translated_msg)
                                
                                if email_address and "@" in email_address:
                                    if flood_risk:
                                        email_success = send_alert_email(
                                            email_address, 
                                            city_name, 
                                            translated_msg
                                        )
                                    else:
                                        email_body = f"""
Dear Resident,

{translated_msg}

Current Weather Conditions:
- Temperature: {weather_data['temperature']}°C
- Humidity: {weather_data['humidity']}%
- Rainfall: {weather_data['rainfall']:.1f}mm
- Conditions: {weather_data['weather_desc']}

Stay safe,
Flood Alert System
"""
                                        email_success = send_alert_email(
                                            email_address,
                                            city_name,
                                            email_body
                                        )
                                elif email_address:
                                    email_success = False
                                    st.error("Invalid email address format")
                                
                                if sms_success or email_success:
                                    alert_type = []
                                    if sms_success and phone_number:
                                        alert_type.append("SMS")
                                    if email_success and email_address:
                                        alert_type.append("Email")
                                    
                                    save_status(
                                        alert_status,
                                        city_name,
                                        '+'.join(alert_type) if alert_type else 'None',
                                        state.auth['language']
                                    )
                                    
                                    st.success("Alerts sent successfully!")
                                else:
                                    st.error("Failed to send all alerts")
                    
                    st.markdown('</div>', unsafe_allow_html=True)
            else:
                # Regular user view - monitoring only
                st.subheader("Flood Monitoring")
                st.info("You are viewing flood monitoring information for your city.")
        else:
            # Non-registered user view
            st.subheader("Flood Monitoring")
            st.info("Please register or log in to track flood risks for your city")

    # Add some spacing at the bottom
    st.markdown("<br><br>", unsafe_allow_html=True)

if __name__ == "__main__":
    main()