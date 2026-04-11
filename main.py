import streamlit as st
from datetime import datetime
import pandas as pd
import plotly.express as px
from rapidfuzz import fuzz

# -------------------------------
# 🔐 Admin Login
# -------------------------------
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "1234"

# -------------------------------
# 🧠 Keywords
# -------------------------------
high_risk_keywords = [
    "bullying", "harassment", "fight", "abuse", "danger", "threat",
    "suicide", "kill myself", "self harm", "die", "end my life"
]

medium_risk_keywords = ["argument", "issue", "problem", "complaint", "delay"]

low_risk_keywords = ["fan", "light", "clean", "water", "maintenance"]

# -------------------------------
# 🧠 RapidFuzz Match Function
# -------------------------------
def is_match(word, keyword_list):
    for keyword in keyword_list:
        score = fuzz.ratio(word, keyword)
        if score > 80:  # similarity threshold
            return True
    return False

# -------------------------------
# 🧠 Risk Detection
# -------------------------------
def detect_risk(complaint):
    words = complaint.lower().split()

    # 🔴 HIGH RISK (priority)
    for word in words:
        if is_match(word, high_risk_keywords):
            return "High Risk 🔴", 5

    score = 0

    # 🟡 MEDIUM
    for word in words:
        if is_match(word, medium_risk_keywords):
            score += 2

    # 🟢 LOW
    for word in words:
        if is_match(word, low_risk_keywords):
            score += 1

    if score >= 2:
        return "Medium Risk 🟡", score
    else:
        return "Low Risk 🟢", score

# -------------------------------
# 📦 Storage
# -------------------------------
if "complaints" not in st.session_state:
    st.session_state.complaints = []

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

# -------------------------------
# ➕ Add Complaint
# -------------------------------
def add_complaint(text):
    risk, score = detect_risk(text)

    data = {
        "text": text,
        "risk": risk,
        "score": score,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    st.session_state.complaints.append(data)

# -------------------------------
# 🔽 Sort
# -------------------------------
def get_sorted():
    return sorted(st.session_state.complaints, key=lambda x: x["score"], reverse=True)

# -------------------------------
# 🧭 Navigation
# -------------------------------
page = st.sidebar.selectbox("Select Page", ["Complaint Page", "Admin Page"])

# ===============================
# 👤 Complaint Page
# ===============================
if page == "Complaint Page":
    st.title("📝 Complaint Submission")

    text = st.text_area("Enter your complaint")

    if st.button("Submit Complaint"):
        if text.strip() == "":
            st.warning("Enter something da")
        else:
            add_complaint(text)
            st.success("Complaint submitted")

# ===============================
# 🔐 Admin Page
# ===============================
elif page == "Admin Page":
    st.title("🔐 Admin Login")

    if not st.session_state.logged_in:
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")

        if st.button("Login"):
            if u == ADMIN_USERNAME and p == ADMIN_PASSWORD:
                st.session_state.logged_in = True
                st.success("Logged in")
            else:
                st.error("Wrong credentials")

    if st.session_state.logged_in:
        st.subheader("📋 Complaints Dashboard")

        data = get_sorted()

        if not data:
            st.info("No complaints")
        else:
            for c in data:
                st.write(f"🕒 {c['time']}")
                st.write(f"📌 {c['text']}")
                st.write(f"⚠️ {c['risk']}")
                st.write("---")

        # -------------------------------
        # 📊 Analytics (Plotly)
        # -------------------------------
        st.subheader("📈 Analytics")

        if data:
            df = pd.DataFrame(data)
            df["risk_clean"] = df["risk"].str.replace("🔴|🟡|🟢", "", regex=True).str.strip()

            # Bar
            fig1 = px.bar(df, x="risk_clean", color="risk_clean", title="Risk Levels")
            st.plotly_chart(fig1, use_container_width=True)

            # Pie
            fig2 = px.pie(df, names="risk_clean", title="Risk Distribution")
            st.plotly_chart(fig2, use_container_width=True)

            # Trend
            df["time"] = pd.to_datetime(df["time"])
            df["date"] = df["time"].dt.date
            trend = df.groupby("date").size().reset_index(name="count")

            fig3 = px.line(trend, x="date", y="count", markers=True, title="Trend")
            st.plotly_chart(fig3, use_container_width=True)

        if st.button("Logout"):
            st.session_state.logged_in = False
