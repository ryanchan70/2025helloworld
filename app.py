import streamlit as st
import requests

# Your Firebase Web API Key
API_KEY = "YOUR_FIREBASE_WEB_API_KEY"

# Firebase Auth endpoints
SIGNUP_URL = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={API_KEY}"
SIGNIN_URL = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={API_KEY}"

# --- Authentication functions ---
def register_user(email, password):
    payload = {"email": email, "password": password, "returnSecureToken": True}
    r = requests.post(SIGNUP_URL, data=payload)
    return r.json()

def login_user(email, password):
    payload = {"email": email, "password": password, "returnSecureToken": True}
    r = requests.post(SIGNIN_URL, data=payload)
    return r.json()

# --- Streamlit UI ---
st.title("🔥 Firebase Auth Demo")

menu = ["Login", "Register"]
choice = st.sidebar.selectbox("Menu", menu)

if choice == "Register":
    st.subheader("Create a New Account")

    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    confirm_password = st.text_input("Confirm Password", type="password")

    if st.button("Register"):
        if password == confirm_password:
            result = register_user(email, password)
            if "error" in result:
                st.error(result["error"]["message"])
            else:
                st.success("✅ Account created successfully!")
                st.json(result)  # Debug info
        else:
            st.error("❌ Passwords do not match")

elif choice == "Login":
    st.subheader("Log In")

    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        result = login_user(email, password)
        if "error" in result:
            st.error(result["error"]["message"])
        else:
            st.success("✅ Logged in successfully!")
            st.write(f"Welcome, {email} 👋")
            st.json(result)  # Debug info (contains ID token, refresh token, etc.)
