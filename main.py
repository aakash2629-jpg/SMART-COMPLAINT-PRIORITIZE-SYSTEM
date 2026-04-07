import streamlit as st
import pandas as pd
from datetime import datetime
import plotly.express as px
from rapidfuzz import fuzz
import os
import re

# ================================================================
# FILE SETUP
# ================================================================
FILE_NAME = "complaints.csv"
COLUMNS   = ["Complaint", "Risk_Level", "Score", "Matched_Keywords", "Timestamp"]

if not os.path.exists(FILE_NAME):
    pd.DataFrame(columns=COLUMNS).to_csv(FILE_NAME, index=False)

df = pd.read_csv(FILE_NAME)
if not df.empty:
    df["Risk_Level"] = df["Risk_Level"].astype(str).str.strip().str.capitalize()


# ================================================================
# KEYWORD LISTS WITH WEIGHTS
#
# Weight scale:
#   10  = absolutely critical (direct threat to life)
#    7–9 = very serious
#    4–6 = moderately serious (medium-tier)
#    1–3 = contextual signals (boost only)
#
# Rule: any single keyword whose weight >= HIGH_SOLO_FLOOR
#       forces the result to High, regardless of total score.
# ================================================================
HIGH_KEYWORDS: dict[str, int] = {
    "kill":     10,
    "murder":   10,
    "bomb":     10,
    "rape":     10,
    "suicide":  10,
    "shoot":     9,
    "stab":      9,
    "attack":    9,
    "weapon":    8,
    "violence":  8,
    "die":       7,   # short word — handled with min-length guard below
    "hurt":      7,
    "harm":      7,
    "strangle":  9,
    "threat":    7,
}

MEDIUM_KEYWORDS: dict[str, int] = {
    "bully":        5,
    "harass":       5,
    "abuse":        5,
    "blackmail":    6,
    "stalk":        5,
    "intimidate":   5,
    "coerce":       5,
    "humiliate":    4,
    "insult":       3,
    "discriminate": 4,
    "assault":      6,
    "molest":       6,
    "torment":      5,
    "taunt":        3,
    "mock":         3,
    "threaten":     5,
}

# Distress context phrases — these BOOST the score when present.
# They don't classify alone but raise severity of combined matches.
# Format: (phrase_to_search_in_full_text, boost_points)
DISTRESS_PHRASES: list[tuple[str, int]] = [
    ("please help",    2),
    ("help me",        2),
    ("i am scared",    3),
    ("i'm scared",     3),
    ("every day",      1),
    ("for days",       1),
    ("for weeks",      1),
    ("cant take",      2),
    ("can't take",     2),
    ("no one helps",   2),
    ("nobody helps",   2),
    ("i feel unsafe",  3),
    ("feel unsafe",    3),
    ("afraid",         2),
    ("frightened",     2),
    ("terrified",      3),
]

# ================================================================
# THRESHOLDS
#
#   HIGH_SOLO_FLOOR  : if any single keyword scores this or above,
#                      result is forced to High immediately.
#   HIGH_THRESHOLD   : accumulated score to reach High via sum.
#   MED_THRESHOLD    : accumulated score to reach Medium via sum.
#   FUZZY_THRESHOLD  : minimum fuzz.ratio similarity (0–100).
#   MIN_TOKEN_LEN    : ignore tokens shorter than this to prevent
#                      "die" from firing on "di" or "de" typos.
# ================================================================
HIGH_SOLO_FLOOR  = 8   # one word with weight ≥ 8 → always High
HIGH_THRESHOLD   = 9   # cumulative score for High
MED_THRESHOLD    = 4   # cumulative score for Medium
FUZZY_THRESHOLD  = 80  # lowered from 85 — catches more real typos safely
MIN_TOKEN_LEN    = 3   # skip very short tokens to reduce false positives


# ================================================================
# SUFFIX LIST FOR STEMMER
#
# ⚠️  "ly" is intentionally EXCLUDED.
#     Reason: "bully".endswith("ly") → strips to "bul", which then
#     fails to fuzzy-match "bullied" → "bulli" (similarity ~66%).
#     Removing "ly" keeps "bully" intact as its own root.
#
# Ordered longest-first so "tion" strips before "on" would.
# ================================================================
SUFFIXES = ["tion", "ment", "ing", "ers", "ied", "ed", "er", "s"]
#                                         ^^^
#                   "ied" must come BEFORE "ed" so "bullied" → "bull"
#                   then we re-attach "y" in the special-case below.


def simple_stem(word: str) -> str:
    """
    Strip one common suffix to approximate the root form.

    Special case: words ending in "ied" (bullied, terrified, petrified)
    map to their "-y" root (bully, terrify, petrify) — NOT to the bare
    stem — because that's what the keyword dict stores.

    Examples:
        bullied   → bully      (ied → y)
        bullying  → bull       (ing stripped)
        harassed  → harass     (ed stripped)
        threats   → threat     (s stripped)
        bully     → bully      (no suffix matched — returned as-is)
        violently → violently  ("ly" not in list — returned as-is,
                                fuzzy still matches "violence" fine)
    Keeps at least 3 characters after stripping.
    """
    # Special case: -ied → -y  (e.g. bullied → bully)
    if word.endswith("ied") and len(word) - 3 >= 3:
        return word[:-3] + "y"

    for suffix in SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def tokenize(text: str) -> list[str]:
    """
    Split text into individual lowercase alpha tokens.
    Splitting word-by-word prevents partial_ratio-style
    substring matches (e.g. 'skill' no longer triggers 'kill').
    """
    return re.findall(r"[a-z]+", text.lower())


def distress_boost(text: str) -> tuple[int, list[str]]:
    """
    Scan the full lowercased text for distress phrases.
    Returns (total_boost_points, list_of_matched_phrases).
    These are context signals — they raise severity but
    cannot push a complaint above Low by themselves.
    """
    lower = text.lower()
    boost   = 0
    phrases = []
    for phrase, points in DISTRESS_PHRASES:
        if phrase in lower:
            boost   += points
            phrases.append(phrase)
    return boost, phrases


# ================================================================
# CORE RISK DETECTION
# ================================================================
def detect_risk(text: str) -> dict:
    """
    Rule-based, fuzzy risk scorer for natural-language complaints.

    Algorithm (fully explainable, no ML):
    ──────────────────────────────────────
    1. Tokenize the complaint into individual words.
    2. Drop tokens shorter than MIN_TOKEN_LEN (noise/stopwords).
    3. Stem each token to its approximate root.
    4. Build a stemmed lookup for HIGH and MEDIUM keywords.
    5. For each token:
         a. Match against HIGH keywords using fuzz.ratio (whole-word).
         b. If similarity ≥ FUZZY_THRESHOLD, record the match.
         c. If no HIGH match, try MEDIUM keywords the same way.
         d. Track which keywords have already been matched to avoid
            counting the same concept twice (deduplication).
    6. Apply distress phrase boost to the accumulated score.
    7. Classify:
         - If any single HIGH keyword's weight ≥ HIGH_SOLO_FLOOR → High
         - elif total_score ≥ HIGH_THRESHOLD                     → High
         - elif total_score ≥ MED_THRESHOLD                      → Medium
         - else                                                   → Low

    Returns
    -------
    dict with keys:
        risk_level  : "Low" | "Medium" | "High"
        score       : int, total accumulated score
        matches     : list of match tuples
                      (original_word, keyword, similarity%, tier)
        distress    : list of distress phrases found
        forced_high : bool, True if a single keyword forced High
    """
    tokens = tokenize(text)

    # Build stemmed keyword tables (stem → original, weight)
    high_stemmed   = {simple_stem(k): (k, w) for k, w in HIGH_KEYWORDS.items()}
    medium_stemmed = {simple_stem(k): (k, w) for k, w in MEDIUM_KEYWORDS.items()}

    score        = 0
    matches      = []           # full match log for display
    seen_keywords: set[str] = set()  # dedup: don't count same keyword twice
    forced_high  = False
    max_single_weight = 0

    for original_word in tokens:
        # Skip very short tokens — they cause false fuzzy matches
        if len(original_word) < MIN_TOKEN_LEN:
            continue

        stemmed_word = simple_stem(original_word)
        matched_this_token = False

        # ── HIGH keywords ──
        for kw_stem, (kw_original, weight) in high_stemmed.items():
            similarity = fuzz.ratio(stemmed_word, kw_stem)
            if similarity >= FUZZY_THRESHOLD:
                if kw_original not in seen_keywords:         # deduplicate
                    score              += weight
                    max_single_weight   = max(max_single_weight, weight)
                    seen_keywords.add(kw_original)
                    matches.append((original_word, kw_original, similarity, "High", weight))
                matched_this_token = True
                break  # one match per token is enough

        # ── MEDIUM keywords (only if no HIGH match for this token) ──
        if not matched_this_token:
            for kw_stem, (kw_original, weight) in medium_stemmed.items():
                similarity = fuzz.ratio(stemmed_word, kw_stem)
                if similarity >= FUZZY_THRESHOLD:
                    if kw_original not in seen_keywords:     # deduplicate
                        score += weight
                        seen_keywords.add(kw_original)
                        matches.append((original_word, kw_original, similarity, "Medium", weight))
                    break

    # ── Distress context boost ──
    boost, distress_phrases = distress_boost(text)
    # Only apply boost if at least one keyword was matched — context
    # alone should not classify a complaint above Low.
    if matches:
        score += boost

    # ── Solo-keyword High override ──
    if max_single_weight >= HIGH_SOLO_FLOOR:
        forced_high = True

    # ── Final classification ──
    if forced_high or score >= HIGH_THRESHOLD:
        risk_level = "High"
    elif score >= MED_THRESHOLD:
        risk_level = "Medium"
    else:
        risk_level = "Low"

    return {
        "risk_level":   risk_level,
        "score":        score,
        "matches":      matches,
        "distress":     distress_phrases,
        "forced_high":  forced_high,
    }


# ================================================================
# HELPERS
# ================================================================
RISK_EMOJI = {"High": "🔴", "Medium": "🟠", "Low": "🟢"}

def format_matches(matches: list) -> str:
    """Human-readable match summary for the CSV and UI."""
    if not matches:
        return "None"
    return ", ".join(
        f"{m[0]}→{m[1]}({m[2]}%,+{m[4]})"
        for m in matches
    )


# ================================================================
# UI
# ================================================================
st.set_page_config(page_title="Complaint Management System", page_icon="🛡️")
st.title("🛡️ AI Complaint Management System")
menu = st.sidebar.selectbox("Menu", ["Submit Complaint", "Admin Dashboard"])


# ================================================================
# SUBMIT PAGE
# ================================================================
if menu == "Submit Complaint":
    st.subheader("📩 Submit a Complaint")
    st.caption(
        "Describe your situation in your own words. "
        "You may write in full sentences — the system will analyse the content."
    )
    complaint = st.text_area("Enter your complaint:", height=150)

    if st.button("Submit", type="primary"):
        if len(complaint.strip()) < 10:
            st.warning("⚠️ Please describe your complaint in more detail (at least 10 characters).")
        else:
            result  = detect_risk(complaint)
            risk    = result["risk_level"]
            score   = result["score"]
            matched = format_matches(result["matches"])
            emoji   = RISK_EMOJI[risk]

            # Persist to CSV
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            new_row   = pd.DataFrame(
                [[complaint, risk, score, matched, timestamp]],
                columns=COLUMNS,
            )
            df = pd.concat([df, new_row], ignore_index=True)
            df.to_csv(FILE_NAME, index=False)

            # ── Result card ──
            st.success(f"{emoji} Complaint submitted!  Risk Level: **{risk}**  |  Score: **{score}**")

            if result["forced_high"]:
                st.error(
                    "⚠️ A critical keyword was detected. "
                    "This complaint has been escalated to **High** priority automatically."
                )

            # ── Keyword breakdown ──
            if result["matches"]:
                with st.expander("🔍 Detected keywords (click to expand)"):
                    rows = []
                    for m in result["matches"]:
                        rows.append({
                            "Word in complaint": m[0],
                            "Matched keyword":   m[1],
                            "Similarity":        f"{m[2]}%",
                            "Tier":              m[3],
                            "Weight":            f"+{m[4]}",
                        })
                    st.table(pd.DataFrame(rows))

            if result["distress"]:
                st.info(
                    f"🆘 Distress signals detected: *{', '.join(result['distress'])}*  "
                    f"(+{sum(p for _, p in DISTRESS_PHRASES if _ in result['distress'])} pts)"
                )


# ================================================================
# ADMIN DASHBOARD
# ================================================================
elif menu == "Admin Dashboard":
    password = st.text_input("Enter Admin Password", type="password")

    if password == "admin123":
        st.subheader("📊 Complaints Dashboard")

        # Reload from disk so admin always sees fresh data
        df = pd.read_csv(FILE_NAME)
        if not df.empty:
            df["Risk_Level"] = df["Risk_Level"].astype(str).str.strip().str.capitalize()

        if df.empty:
            st.info("No complaints submitted yet.")
        else:
            # ── Summary metrics ──
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Complaints", len(df))
            col2.metric("🔴 High",   len(df[df["Risk_Level"] == "High"]))
            col3.metric("🟠 Medium", len(df[df["Risk_Level"] == "Medium"]))
            col4.metric("🟢 Low",    len(df[df["Risk_Level"] == "Low"]))

            st.divider()

            # ── Filter controls ──
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                filter_risk = st.multiselect(
                    "Filter by Risk Level",
                    options=["High", "Medium", "Low"],
                    default=["High", "Medium", "Low"],
                )
            with col_f2:
                sort_by = st.selectbox("Sort by", ["Timestamp", "Score", "Risk_Level"])

            filtered_df = df[df["Risk_Level"].isin(filter_risk)].sort_values(
                sort_by, ascending=(sort_by == "Risk_Level")
            )

            st.dataframe(filtered_df, use_container_width=True)

            st.divider()

            # ── Charts ──
            chart_col1, chart_col2 = st.columns(2)
            color_map = {"Low": "green", "Medium": "orange", "High": "red"}

            with chart_col1:
                fig_pie = px.pie(
                    df,
                    names="Risk_Level",
                    title="Risk Level Distribution",
                    color="Risk_Level",
                    color_discrete_map=color_map,
                )
                fig_pie.update_traces(textinfo="percent+label")
                st.plotly_chart(fig_pie, use_container_width=True)

            with chart_col2:
                if "Score" in df.columns:
                    fig_hist = px.histogram(
                        df,
                        x="Score",
                        color="Risk_Level",
                        color_discrete_map=color_map,
                        title="Score Distribution",
                        nbins=20,
                        barmode="overlay",
                    )
                    st.plotly_chart(fig_hist, use_container_width=True)

            # ── Latest complaints ──
            st.subheader("🕒 Latest 5 Complaints")
            st.dataframe(df.tail(5)[["Timestamp", "Risk_Level", "Score", "Complaint"]], use_container_width=True)

            # ── Export ──
            csv_bytes = df.to_csv(index=False).encode()
            st.download_button(
                label="⬇️ Download all complaints as CSV",
                data=csv_bytes,
                file_name="complaints_export.csv",
                mime="text/csv",
            )

    elif password:
        st.warning("🔒 Incorrect password. Please try again.")
