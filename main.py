import streamlit as st
import pandas as pd
from datetime import datetime
import plotly.express as px
from rapidfuzz import fuzz
import os

# -------------------------------
# FILE SETUP
# -------------------------------
FILE_NAME = "complaints.csv"

if not os.path.exists(FILE_NAME):
    df = pd.DataFrame(columns=["Complaint", "Risk_Level", "Timestamp"])
    df.to_csv(FILE_NAME, index=False)

df = pd.read_csv(FILE_NAME)

# -------------------------------
# CLEAN DATA
# -------------------------------
if not df.empty:
    df["Risk_Level"] = df["Risk_Level"].astype(str).str.strip().str.capitalize()

# -------------------------------
# KEYWORDS
# -------------------------------
high_keywords = [
    "kill", "murder", "bomb", "attack", "rape",
    "suicide", "stab", "violence", "die"
]

medium_keywords = [
    "bully", "bullying", "harass", "harassment",
    "threat", "abuse", "blackmail", "stalk", "intimidate"
]

# -------------------------------
# RISK DETECTION (FUZZY)
# -------------------------------
def detect_risk(text):
    text = text.lower()

    for word in high_keywords:
        if fuzz.partial_ratio(word, text) > 80:
            return "High"

    for word in medium_keywords:
        if fuzz.partial_ratio(word, text) > 80:
            return "Medium"

    return "Low"

# -------------------------------
# UI
# -------------------------------
st.title("🛡️ AI Complaint Management System")

menu = st.sidebar.selectbox("Menu", ["Submit Complaint", "Admin Dashboard"])

# -------------------------------
# SUBMIT PAGE
# -------------------------------
if menu == "Submit Complaint":

    st.subheader("📩 Submit a Complaint")

    complaint = st.text_area("Enter your complaint:")

    if st.button("Submit"):

        if len(complaint.strip()) < 5:
            st.warning("⚠️ Complaint too short")
        else:
            risk = detect_risk(complaint)
            time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            new_data = pd.DataFrame([[complaint, risk, time]],
                                    columns=["Complaint", "Risk_Level", "Timestamp"])

            df = pd.concat([df, new_data], ignore_index=True)
            df.to_csv(FILE_NAME, index=False)

            st.success(f"✅ Complaint submitted! Risk Level: {risk}")

# -------------------------------
# ADMIN DASHBOARD
# -------------------------------
elif menu == "Admin Dashboard":

    password = st.text_input("Enter Admin Password", type="password")

    if password == "admin123":

        st.subheader("📊 Complaints Dashboard")

        if df.empty:
            st.info("No complaints yet.")
        else:
            st.dataframe(df)

            # -------------------------------
            # PIE CHART WITH CORRECT COLORS
            # -------------------------------
            color_map = {
                "Low": "green",
                "Medium": "orange",
                "High": "red"
            }

            fig = px.pie(
                df,
                names="Risk_Level",
                title="Risk Level Distribution",
                color="Risk_Level",
                color_discrete_map=color_map
            )

            fig.update_traces(textinfo='percent+label')
            fig.update_layout(title_x=0.3)

            st.plotly_chart(fig, use_container_width=True)

            # -------------------------------
            # LIVE DATA PREVIEW (last entries)
            # -------------------------------
            st.subheader("🕒 Latest Complaints")
            st.write(df.tail(5))

    else:
        st.warning("🔒 Incorrect Password")