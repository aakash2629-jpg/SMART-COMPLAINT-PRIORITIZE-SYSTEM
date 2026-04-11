import streamlit as st
from datetime import datetime

# -------------------------------
# 🔐 Simple Admin Login
# -------------------------------
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "1234"

# -------------------------------
# 🧠 Risk Keywords
# -------------------------------
high_risk_keywords = ["bullying", "harassment", "fight", "abuse", "danger", "threat"]
medium_risk_keywords = ["argument", "issue", "problem", "complaint", "delay"]
low_risk_keywords = ["fan", "light", "clean", "water", "maintenance"]

# -------------------------------
# 🧠 Risk Detection Function
# -------------------------------
def detect_risk(complaint):
    complaint = complaint.lower()
    score = 0

    for word in high_risk_keywords:
        if word in complaint:
            score += 3

    for word in medium_risk_keywords:
        if word in complaint:
            score += 2

    for word in low_risk_keywords:
        if word in complaint:
            score += 1

    if score >= 3:
        return "High Risk 🔴", score
    elif score == 2:
        return "Medium Risk 🟡", score
    else:
        return "Low Risk 🟢", score

# -------------------------------
# 📦 Session Storage
# -------------------------------
if "complaints" not in st.session_state:
    st.session_state.complaints = []

# -------------------------------
# ➕ Add Complaint
# -------------------------------
def add_complaint(text):
    risk, score = detect_risk(text)

    complaint_data = {
        "text": text,
        "risk": risk,
        "score": score,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    st.session_state.complaints.append(complaint_data)

# -------------------------------
# 🔽 Sort Complaints
# -------------------------------
def get_sorted_complaints():
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

    complaint_text = st.text_area("Enter your complaint")

    if st.button("Submit Complaint"):
        if complaint_text.strip() == "":
            st.warning("Please enter a complaint")
        else:
            add_complaint(complaint_text)
            st.success("Complaint submitted successfully!")

# ===============================
# 🔐 Admin Page
# ===============================
elif page == "Admin Page":
    st.title("🔐 Admin Login")

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            st.session_state.logged_in = True
        else:
            st.error("Invalid credentials")

    if st.session_state.get("logged_in"):
        st.success("Logged in successfully")

        st.subheader("📊 Complaints Dashboard")

        sorted_complaints = get_sorted_complaints()

        if len(sorted_complaints) == 0:
            st.info("No complaints yet")
        else:
            for c in sorted_complaints:
                st.write(f"🕒 {c['time']}")
                st.write(f"📌 {c['text']}")
                st.write(f"⚠️ {c['risk']}")
                st.write("---")

        # -------------------------------
        # 📊 Simple Analytics
        # -------------------------------
        st.subheader("📈 Analytics")

        high = sum(1 for c in sorted_complaints if "High" in c["risk"])
        medium = sum(1 for c in sorted_complaints if "Medium" in c["risk"])
        low = sum(1 for c in sorted_complaints if "Low" in c["risk"])

        st.write(f"🔴 High Risk: {high}")
        st.write(f"🟡 Medium Risk: {medium}")
        st.write(f"🟢 Low Risk: {low}")
