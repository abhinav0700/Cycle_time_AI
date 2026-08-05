import streamlit as st
import google.generativeai as genai
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import re
import os
import time
import tempfile
import requests

def list_local_videos():
    import glob
    dl_dir = "/Users/aswin/Downloads"
    if not os.path.exists(dl_dir):
        return []
    exts = ["*.mp4", "*.mov", "*.avi", "*.mkv"]
    videos = []
    for ext in exts:
        videos.extend(glob.glob(os.path.join(dl_dir, ext)))
    return sorted([os.path.basename(v) for v in videos])

def load_api_key():
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        return key
    if os.path.exists(".env"):
        try:
            with open(".env", "r") as f:
                for line in f:
                    if line.strip().startswith("GEMINI_API_KEY="):
                        parts = line.strip().split("=", 1)
                        if len(parts) == 2:
                            return parts[1].strip().strip('"').strip("'")
        except:
            pass
    return ""


def upload_file_to_gemini(file_path, mime_type, api_key):
    url = f"https://generativelanguage.googleapis.com/upload/v1beta/files?key={api_key}"
    headers = {
        "X-Goog-Upload-Protocol": "resumable",
        "X-Goog-Upload-Command": "start",
        "X-Goog-Upload-Header-Content-Length": str(os.path.getsize(file_path)),
        "X-Goog-Upload-Header-Content-Type": mime_type,
        "Content-Type": "application/json"
    }
    metadata = {
        "file": {
            "display_name": os.path.basename(file_path)
        }
    }
    r = requests.post(url, headers=headers, json=metadata)
    if r.status_code != 200:
        raise Exception(f"Failed to initiate upload session: {r.text}")
    upload_url = r.headers.get("X-Goog-Upload-URL")
    with open(file_path, "rb") as f:
        headers = {
            "X-Goog-Upload-Offset": "0",
            "X-Goog-Upload-Command": "upload, finalize",
            "Content-Length": str(os.path.getsize(file_path))
        }
        r2 = requests.post(upload_url, headers=headers, data=f)
    if r2.status_code != 200:
        raise Exception(f"Failed to upload file content: {r2.text}")
    return r2.json()

def get_file_status(file_name, api_key):
    url = f"https://generativelanguage.googleapis.com/v1beta/{file_name}?key={api_key}"
    r = requests.get(url)
    if r.status_code != 200:
        raise Exception(f"Failed to get file status: {r.text}")
    return r.json()

def delete_file_from_gemini(file_name, api_key):
    url = f"https://generativelanguage.googleapis.com/v1beta/{file_name}?key={api_key}"
    requests.delete(url)

def generate_content_with_file(model_name, file_uri, mime_type, prompt, api_key):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    headers = {
        "Content-Type": "application/json"
    }
    data = {
        "contents": [{
            "parts": [
                {
                    "file_data": {
                        "mime_type": mime_type,
                        "file_uri": file_uri
                    }
                },
                {
                    "text": prompt
                }
            ]
        }]
    }
    r = requests.post(url, headers=headers, json=data)
    if r.status_code != 200:
        raise Exception(f"Model generation failed: {r.text}")
    return r.json()

# 1. Page Configuration
st.set_page_config(
    page_title="IE Time Study Analyzer",
    page_icon="⏱️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 2. Theme Toggle State
IS_DARK = False

# 3. CSS Design System
# Zinc/shadcn inspired theme styles
css_vars = f"""
:root {{
    --bg: {"#09090b" if IS_DARK else "#ffffff"};
    --bg-subtle: {"#0c0c0f" if IS_DARK else "#f9fafb"};
    --card: {"#0c0c0f" if IS_DARK else "#ffffff"};
    --card-hover: {"#131316" if IS_DARK else "#f4f4f5"};
    --border: {"#1e1e24" if IS_DARK else "#e4e4e7"};
    --border-subtle: {"#16161a" if IS_DARK else "#f0f0f2"};
    --text: {"#fafafa" if IS_DARK else "#09090b"};
    --text-muted: #71717a;
    --text-dim: {"#52525b" if IS_DARK else "#a1a1aa"};
    --accent: #2563eb;
    --accent-muted: #1d4ed8;
    --green: {"#22c55e" if IS_DARK else "#16a34a"};
    --green-muted: {"rgba(34,197,94,0.12)" if IS_DARK else "rgba(22,163,74,0.08)"};
    --red: {"#ef4444" if IS_DARK else "#dc2626"};
    --red-muted: {"rgba(239,68,68,0.12)" if IS_DARK else "rgba(220,38,38,0.08)"};
    --amber: {"#f59e0b" if IS_DARK else "#d97706"};
    --amber-muted: {"rgba(245,158,11,0.12)" if IS_DARK else "rgba(217,119,6,0.08)"};
    --shadow: {"none" if IS_DARK else "0 1px 3px rgba(0,0,0,0.04), 0 1px 2px rgba(0,0,0,0.03)"};
    --radius: 10px;
}}
"""

style_css = """
/* Hide Streamlit default components */
header[data-testid="stHeader"], #MainMenu, footer, [data-testid="stDecoration"], [data-testid="stStatusWidget"], .stDeployButton {
    display: none !important;
}

html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"], .main, .block-container, section[data-testid="stMain"] {
    background-color: var(--bg) !important;
    color: var(--text) !important;
    font-family: 'DM Sans', -apple-system, sans-serif !important;
}

.block-container {
    padding: 1.5rem 2rem 2rem !important;
    max-width: 1400px !important;
}

/* Custom Cards */
.metric-card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1.25rem 1.4rem;
    box-shadow: var(--shadow);
    display: flex;
    flex-direction: column;
    height: 100%;
}
.metric-label {
    font-size: 0.78rem;
    color: var(--text-muted);
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
.metric-value {
    font-size: 1.85rem;
    font-weight: 700;
    color: var(--text);
    letter-spacing: -0.03em;
    margin-top: 0.2rem;
}
.metric-delta {
    font-size: 0.75rem;
    font-weight: 500;
    margin-top: 0.4rem;
    padding: 2px 8px;
    border-radius: 6px;
    display: inline-flex;
    align-items: center;
    gap: 3px;
    width: fit-content;
}
.delta-up { color: var(--green); background: var(--green-muted); }
.delta-down { color: var(--red); background: var(--red-muted); }
.delta-warn { color: var(--amber); background: var(--amber-muted); }

/* Chart and panel wrappers */
.panel-card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1.4rem;
    box-shadow: var(--shadow);
    margin-bottom: 1.25rem;
}
.panel-title {
    font-size: 0.95rem;
    font-weight: 600;
    color: var(--text);
    margin-bottom: 0.3rem;
    display: flex;
    align-items: center;
    gap: 6px;
}
.panel-subtitle {
    font-size: 0.75rem;
    color: var(--text-dim);
    margin-bottom: 1.2rem;
}

/* Tabs customization */
button[data-baseweb="tab"] {
    background: transparent !important;
    color: var(--text-muted) !important;
    font-size: 0.85rem !important;
    font-weight: 500 !important;
    padding: 0.55rem 1.2rem !important;
    border: 1px solid transparent !important;
    border-radius: 8px !important;
    transition: all 0.2s ease !important;
}
button[data-baseweb="tab"]:hover {
    color: var(--text) !important;
    background: var(--card-hover) !important;
}
button[data-baseweb="tab"][aria-selected="true"] {
    color: var(--text) !important;
    background: var(--card) !important;
    border-color: var(--border) !important;
}
[data-baseweb="tab-highlight"], [data-baseweb="tab-border"] {
    display: none !important;
}
[data-baseweb="tab-list"] {
    gap: 6px !important;
    background: var(--bg-subtle) !important;
    border: 1px solid var(--border) !important;
    border-radius: 10px !important;
    padding: 4px !important;
}

/* Sidebar Custom Styling */
[data-testid="stSidebar"] {
    background-color: var(--bg-subtle) !important;
    border-right: 1px solid var(--border) !important;
}

/* Horizontal block spacing */
[data-testid="stHorizontalBlock"] {
    gap: 1.25rem !important;
}

/* Global text/heading color overrides for Streamlit elements to prevent contrast issues */
.stMarkdown, .stMarkdown p, .stMarkdown li, .stMarkdown span,
.stMarkdown h1, .stMarkdown h2, .stMarkdown h3, .stMarkdown h4, .stMarkdown h5, .stMarkdown h6,
label, .stWidgetLabel, div[data-testid="stWidgetLabel"] p, div[data-testid="stWidgetLabel"] span,
.stRadio label, .stRadio label p, .stRadio label span,
.stSelectbox label, .stSelectbox label p,
.stFileUploader label, .stFileUploader label p,
.stTextInput label, .stTextInput label p,
.stTextArea label, .stTextArea label p {
    color: var(--text) !important;
}

/* Alert Styling overrides */
div[data-testid="stAlert"] {
    background-color: var(--bg-subtle) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
}
div[data-testid="stAlert"] p, div[data-testid="stAlert"] div {
    color: var(--text) !important;
}

/* Styled Data Table */
.data-table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 0.75rem;
    font-size: 0.85rem;
}
.data-table th {
    text-align: left;
    padding: 0.6rem 0.8rem;
    background-color: var(--bg-subtle);
    border-bottom: 2px solid var(--border);
    color: var(--text-muted) !important;
    font-weight: 600;
}
.data-table td {
    padding: 0.6rem 0.8rem;
    border-bottom: 1px solid var(--border-subtle);
    color: var(--text) !important;
}
.data-table tr:hover {
    background-color: var(--card-hover);
}
.badge {
    display: inline-flex;
    align-items: center;
    padding: 2px 8px;
    border-radius: 6px;
    font-size: 0.75rem;
    font-weight: 500;
}
.badge-blue {
    background-color: rgba(37, 99, 235, 0.1);
    color: var(--accent);
}

/* Style all Streamlit bordered containers to match panel-card design */
div[data-testid="stVerticalBlockBorderWrapper"] {
    background-color: var(--card) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    padding: 1.4rem !important;
    box-shadow: var(--shadow) !important;
    margin-bottom: 1.25rem !important;
}
div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stVerticalBlock"] {
    gap: 0.5rem !important;
}
"""

st.markdown(f"<style>{css_vars}\n{style_css}</style>", unsafe_allow_html=True)

# 4. Helper UI Functions
def metric_card(label, value, delta=None, delta_type="up"):
    cls = f"delta-{delta_type}"
    arrow = "↑" if delta_type == "up" else ("↓" if delta_type == "down" else "→")
    delta_html = f'<div class="metric-delta {cls}">{arrow} {delta}</div>' if delta else ""
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">{label}</div>
        <div class="metric-value">{value}</div>
        {delta_html}
    </div>
    """, unsafe_allow_html=True)

# Plotly styling configuration
PLOT_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="DM Sans, sans-serif", color="#71717a" if not IS_DARK else "#a1a1aa", size=11),
    margin=dict(l=0, r=0, t=10, b=10),
)

# 5. API Key and Model Sidebar Configurations
with st.sidebar:
    st.markdown("""
    <div style='display: flex; align-items: center; gap: 8px; margin-bottom: 1.5rem;'>
        <span style='font-size: 2rem;'>⏱️</span>
        <span style='font-size: 1.15rem; font-weight: 700; letter-spacing: -0.02em;'>IE Time Study</span>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("<hr style='margin: 0.5rem 0 1.5rem 0; border-color: var(--border);'>", unsafe_allow_html=True)

    # Load API Key from environment or .env securely
    api_key = load_api_key()
    model_name = "gemini-3.1-pro-preview"

# 6. Base Prompt Configuration
BASE_PROMPT = """You are an Industrial Engineer, Lean Manufacturing Consultant, Six Sigma Black Belt, and AI Manufacturing Analyst.

Your task is to analyze the uploaded manufacturing video as if you were performing a professional industrial time study.

Your objective is to identify every manufacturing activity, calculate its cycle time, and provide productivity insights.

Instructions:
1. Watch the complete video carefully.
2. Detect every distinct manufacturing activity such as:
   - Picking component
   - Walking
   - Reaching
   - Positioning
   - Assembly
   - Tightening
   - Welding
   - Inspection
   - Packaging
   - Waiting
   - Idle
   - Machine interaction
   - Tool change
   - Material handling
   - Finished product placement

3. For every detected activity provide:
   - Activity Name
   - Start Timestamp (in format MM:SS)
   - End Timestamp (in format MM:SS)
   - Duration (in format Xs or X.Xs)
   - Confidence Score

4. Create a complete activity timeline as a Markdown table.

5. Calculate:
   - Total Cycle Time
   - Value Added Time (explain which activities are VA, e.g., Assembly, Fastening)
   - Non Value Added Time (explain which activities are NVA, e.g., Reaching, Unnecessary handling)
   - Idle Time
   - Waiting Time
   - Machine Time
   - Human Working Time

6. Detect bottlenecks.
7. Detect unnecessary motions.
8. Detect excessive walking.
9. Detect repeated movements.
10. Detect ergonomic issues if visible.
11. Compare activities and identify which consumes the most time.
12. Suggest process improvements that could reduce cycle time.
13. Generate a summary report.

You MUST format your output exactly as shown below:

# Video Summary
[Provide a summary of what the video shows, including the overall operation]

# Activity Timeline
| Activity | Start | End | Duration | Confidence Score |
|---|---|---|---|---|
| [Activity Name] | [Start MM:SS] | [End MM:SS] | [Duration] | [Confidence %] |

# Cycle Time Summary
- Total Cycle Time: [X]s
- Value Added Time: [Y]s ([Reasoning])
- Non Value Added Time: [Z]s ([Reasoning])
- Idle Time: [I]s
- Waiting Time: [W]s
- Machine Time: [M]s
- Human Working Time: [H]s

# Bottlenecks
- Primary Bottleneck: [Description]
- Repeated Movements: [Description]
- Ergonomic Issues: [Description]
- Unnecessary Motions: [Description]
- Excessive Walking: [Description]

# AI Recommendations
- [Recommendation 1]
- [Recommendation 2]

# Productivity Score (/100)
[Score]/100

# Estimated Time Savings
[Savings]

# Confidence Level
[Confidence %]
"""

# MOCK DATA FOR DEMO MODE
MOCK_MD_OUTPUT = """# Video Summary
The video shows a manual assembly operation consisting of surface wiping, inserting a metal block into a machined slot, and securing it with a threaded bolt.

# Activity Timeline
| Activity | Start | End | Duration | Confidence Score |
|---|---|---|---|---|
| Cleaning | 00:00 | 00:03 | 3s | 75% |
| Positioning | 00:03 | 00:05 | 2s | 75% |
| Picking component | 00:05 | 00:06 | 1s | 75% |
| Tightening | 00:06 | 00:13 | 7s | 75% |

# Cycle Time Summary
- Total Cycle Time: 13s
- Value Added Time: 9s (Positioning, Tightening)
- Non Value Added Time: 4s (Cleaning, Picking)
- Idle Time: 0s
- Waiting Time: 0s
- Machine Time: 0s
- Human Working Time: 13s

# Bottlenecks
- Primary Bottleneck: Manual tightening consumes the most time (7s), representing over 50% of the cycle.
- Repeated Movements: Manual threading requires repetitive wrist rotation.
- Ergonomic Issues: Minor repetitive wrist strain from manual fastening.
- Unnecessary Motions: Reaching for the bolt is an unnecessary motion that can be optimized.
- Excessive Walking: None detected.

# AI Recommendations
- Replace manual tightening with a powered electric or pneumatic driver to reduce fastening time and wrist strain.
- Pre-stage bolts closer to the assembly point (point-of-use presentation) to eliminate the reaching motion.

# Productivity Score (/100)
65/100

# Estimated Time Savings
5 seconds per cycle

# Confidence Level
75%
"""

# 7. Helper functions to parse values from markdown
def parse_time_to_seconds(t_str):
    t_str = str(t_str).strip()
    t_str = re.sub(r'[^\d:]', '', t_str)
    if not t_str:
        return 0
    parts = t_str.split(':')
    if len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    elif len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    else:
        try:
            return float(t_str)
        except:
            return 0

def parse_duration_to_seconds(dur_str):
    dur_str = str(dur_str).strip().lower()
    # Match decimal or integer numbers
    match = re.search(r'([\d\.]+)', dur_str)
    if match:
        return float(match.group(1))
    return 0.0

def parse_markdown_table(text):
    lines = text.split('\n')
    table_lines = []
    in_table = False
    
    for line in lines:
        if '|' in line:
            if '---|' in line or '--:|' in line or ':-:|' in line:
                continue
            table_lines.append(line)
            
    if not table_lines:
        return None
        
    headers = [c.strip() for c in table_lines[0].split('|') if c.strip()]
    rows = []
    for line in table_lines[1:]:
        cols = [c.strip() for c in line.split('|')]
        # Clean start/end pipes
        if cols and cols[0] == '':
            cols = cols[1:]
        if cols and cols[-1] == '':
            cols = cols[:-1]
        
        # Verify it has columns
        if len(cols) >= len(headers):
            cols = cols[:len(headers)]
            rows.append(cols)
            
    if not rows:
        return None
        
    df = pd.DataFrame(rows, columns=headers)
    
    # Process start/end columns to construct float values
    start_col = None
    end_col = None
    dur_col = None
    
    for c in df.columns:
        if 'start' in c.lower():
            start_col = c
        elif 'end' in c.lower():
            end_col = c
        elif 'duration' in c.lower():
            dur_col = c
            
    if start_col:
        df['Start_Sec'] = df[start_col].apply(parse_time_to_seconds)
    else:
        df['Start_Sec'] = 0.0
        
    if end_col:
        df['End_Sec'] = df[end_col].apply(parse_time_to_seconds)
    elif dur_col:
        df['End_Sec'] = df['Start_Sec'] + df[dur_col].apply(parse_duration_to_seconds)
    else:
        df['End_Sec'] = df['Start_Sec'] + 1.0
        
    if dur_col:
        df['Duration_Sec'] = df[dur_col].apply(parse_duration_to_seconds)
    else:
        df['Duration_Sec'] = df['End_Sec'] - df['Start_Sec']
        
    # Pick activity column
    act_col = df.columns[0]
    df['Activity_Label'] = df[act_col]
    
    return df

def parse_kpi_metrics(text):
    metrics = {
        "Total Cycle Time": "N/A",
        "Value Added Time": "N/A",
        "Non Value Added Time": "N/A",
        "Idle Time": "N/A",
        "Productivity Score": "N/A",
        "Time Savings": "N/A",
        "Confidence Level": "N/A"
    }
    
    # 1. Total Cycle Time
    tc_match = re.search(r"Total Cycle Time\s*:\s*([^\n]+)", text, re.IGNORECASE)
    if tc_match: metrics["Total Cycle Time"] = tc_match.group(1).strip()
    
    # 2. Value Added Time
    va_match = re.search(r"Value Added Time\s*:\s*([^\n]+)", text, re.IGNORECASE)
    if not va_match:
        va_match = re.search(r"Value-Added Time\s*:\s*([^\n]+)", text, re.IGNORECASE)
    if va_match: metrics["Value Added Time"] = va_match.group(1).strip()
    
    # 3. Non Value Added Time
    nva_match = re.search(r"Non\s*Value\s*Added\s*Time\s*:\s*([^\n]+)", text, re.IGNORECASE)
    if not nva_match:
        nva_match = re.search(r"Non-Value-Added Time\s*:\s*([^\n]+)", text, re.IGNORECASE)
    if nva_match: metrics["Non Value Added Time"] = nva_match.group(1).strip()
    
    # 4. Idle Time
    idle_match = re.search(r"Idle Time\s*:\s*([^\n]+)", text, re.IGNORECASE)
    if idle_match: metrics["Idle Time"] = idle_match.group(1).strip()
    
    # 5. Productivity Score
    prod_match = re.search(r"Productivity Score[^\n]*\n+([^\n]+)", text, re.IGNORECASE)
    if not prod_match:
        prod_match = re.search(r"Productivity Score\s*:\s*([^\n]+)", text, re.IGNORECASE)
    if prod_match:
        metrics["Productivity Score"] = prod_match.group(1).strip()
        
    # 6. Time Savings
    savings_match = re.search(r"Estimated Time Savings[^\n]*\n+([^\n]+)", text, re.IGNORECASE)
    if not savings_match:
        savings_match = re.search(r"Estimated Time Savings\s*:\s*([^\n]+)", text, re.IGNORECASE)
    if savings_match:
        metrics["Time Savings"] = savings_match.group(1).strip()
        
    # 7. Confidence Level
    conf_match = re.search(r"Confidence Level[^\n]*\n+([^\n]+)", text, re.IGNORECASE)
    if not conf_match:
        conf_match = re.search(r"Confidence Level\s*:\s*([^\n]+)", text, re.IGNORECASE)
    if conf_match:
        metrics["Confidence Level"] = conf_match.group(1).strip()
        
    return metrics

# 8. Main Application Interface
st.markdown("""
<div style='margin-bottom: 2rem;'>
    <div style='font-size: 2rem; font-weight: 700; letter-spacing: -0.03em;'>⏱️ Industrial Video Time Study Analyst</div>
    <div style='font-size: 0.88rem; color: var(--text-muted); margin-top: 0.2rem;'>
        Automatically dissect manufacturing videos into detailed task cycle times, identify wastes, and retrieve productivity indicators.
    </div>
</div>
""", unsafe_allow_html=True)

# Main Navigation Tabs
tab_dash, tab_report = st.tabs([
    "📊 Interactive Dashboard", 
    "📄 Detailed AI Report"
])

# Initialize session state for storing study results
if "study_output" not in st.session_state:
    st.session_state.study_output = None
if "is_demo" not in st.session_state:
    st.session_state.is_demo = False

custom_prompt = BASE_PROMPT

# TAB 1: Main Interactive Dashboard
with tab_dash:
    # Local video listing
    local_videos = list_local_videos()
    
    # Top Row: Ingestion controller
    ingest_col1, ingest_col2 = st.columns([7, 3])
    
    # Ingestion type toggle
    with ingest_col1:
        input_type = st.radio("Select Video Input Mode", ["Choose from Downloads Folder", "Upload a Custom Video"], horizontal=True)
        
        video_path = None
        uploaded_video = None
        
        if input_type == "Choose from Downloads Folder":
            if local_videos:
                selected_local = st.selectbox("Select local video", local_videos, index=0)
                video_path = os.path.join("/Users/aswin/Downloads", selected_local)
            else:
                st.warning("No video files (.mp4, .mov, .avi, .mkv) found in your Downloads folder.")
        else:
            uploaded_video = st.file_uploader(
                "Upload Manufacturing Operation Video", 
                type=["mp4", "mov", "avi", "mkv"],
                help="Videos containing manual workflows yield high accuracy results."
            )
            
    # Enable analyze button if a video source is available
    has_video_source = (input_type == "Choose from Downloads Folder" and video_path is not None) or (input_type == "Upload a Custom Video" and uploaded_video is not None)
    
    with ingest_col2:
        st.markdown("<div style='height: 48px;'></div>", unsafe_allow_html=True)
        btn_col1, btn_col2 = st.columns(2)
        with btn_col1:
            analyze_clicked = st.button("🚀 Analyze Video", use_container_width=True, disabled=not api_key or not has_video_source)
        with btn_col2:
            demo_clicked = st.button("💡 Load Mock Demo", use_container_width=True)

    # Trigger mock demo load
    if demo_clicked:
        st.session_state.study_output = MOCK_MD_OUTPUT
        st.session_state.is_demo = True
        st.success("Mock demo study loaded! Preview the dashboard layout below.")

    # Trigger Live Video Analysis
    if analyze_clicked and has_video_source:
        st.session_state.is_demo = False
        temp_path = None
        is_temp_file = False
        try:
            if input_type == "Choose from Downloads Folder":
                temp_path = video_path
                is_temp_file = False
            else:
                with st.spinner("Preparing uploaded video file..."):
                    # Save uploaded file to temp file
                    suffix = os.path.splitext(uploaded_video.name)[1]
                    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_vid:
                        temp_vid.write(uploaded_video.read())
                        temp_path = temp_vid.name
                    is_temp_file = True
                
            # Create progress container
            status_container = st.empty()
            
            with status_container.container():
                st.info("Uploading video to File API (this may take a few moments)...")
                
            # Upload video to File API via direct HTTP
            file_meta = upload_file_to_gemini(temp_path, "video/mp4", api_key)
            file_name = file_meta["file"]["name"]
            file_uri = file_meta["file"]["uri"]
            
            # Poll for processing completion
            start_poll = time.time()
            status = get_file_status(file_name, api_key)
            while status.get("state") == "PROCESSING":
                with status_container.container():
                    st.info(f"AI is processing the video frames... (elapsed: {int(time.time() - start_poll)}s)")
                time.sleep(3)
                status = get_file_status(file_name, api_key)
                
            if status.get("state") == "FAILED":
                raise Exception("Video ingestion processing failed.")
                
            # Query the model
            with status_container.container():
                st.info("Analyzing manufacturing activities, timing work steps, and detecting bottlenecks...")
                
            response_json = generate_content_with_file(model_name, file_uri, "video/mp4", custom_prompt, api_key)
            
            # Extract generated text from REST response
            try:
                generated_text = response_json["candidates"][0]["content"]["parts"][0]["text"]
            except Exception as parse_err:
                raise Exception(f"Failed to parse response: {str(parse_err)}. Raw response: {response_json}")
            
            # Save results
            st.session_state.study_output = generated_text
            status_container.empty()
            st.success("Analysis complete! View the results below.")
            
            # Cleanup temp file and remote file
            try:
                if is_temp_file and temp_path:
                    os.unlink(temp_path)
                delete_file_from_gemini(file_name, api_key)
            except Exception as cleanup_err:
                pass # Non-blocking
        except Exception as e:
            st.error(f"Analysis failed: {str(e)}")
            st.info("Make sure your API key is correct and valid. You can test using the 'Load Mock Demo' button.")

    # If results are loaded, render dashboard components
    if st.session_state.study_output:
        raw_text = st.session_state.study_output
        
        # Parse metrics & table
        metrics = parse_kpi_metrics(raw_text)
        df_timeline = parse_markdown_table(raw_text)
        
        # 1. KPI Cards Row
        kpi_col1, kpi_col2, kpi_col3, kpi_col4 = st.columns(4)
        
        with kpi_col1:
            prod_score = metrics["Productivity Score"]
            # Extract number from score if possible
            score_num = re.search(r'(\d+)', prod_score)
            delta_type = "up"
            if score_num:
                num = int(score_num.group(1))
                if num < 60: delta_type = "down"
                elif num < 80: delta_type = "warn"
            metric_card("Productivity Score", prod_score, delta="Score / 100", delta_type=delta_type)
            
        with kpi_col2:
            cycle_time = metrics["Total Cycle Time"]
            metric_card("Total Cycle Time", cycle_time, delta="Total Duration", delta_type="warn")
            
        with kpi_col3:
            va_time = metrics["Value Added Time"]
            # Extract duration part if possible (e.g. 9s)
            va_val = va_time.split('(')[0].strip() if '(' in va_time else va_time
            metric_card("Value-Added Time", va_val, delta="Active VA work", delta_type="up")
            
        with kpi_col4:
            nva_time = metrics["Non Value Added Time"]
            nva_val = nva_time.split('(')[0].strip() if '(' in nva_time else nva_time
            metric_card("Non Value-Added (Waste)", nva_val, delta="Unnecessary motions", delta_type="down")

        st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)
        
        # 2. Main Two Column Dashboard Layout
        dash_col1, dash_col2 = st.columns([5, 5])
        
        with dash_col1:
            # Video Player Panel
            with st.container(border=True):
                st.markdown("""
                <div class="panel-title">🎥 Manufacturing Operation Stream</div>
                <div class="panel-subtitle">Review the raw production process video.</div>
                """, unsafe_allow_html=True)
                
                if st.session_state.is_demo:
                    st.info("Running in Mock Demo Mode. Video playback is disabled. Upload a custom video to view streaming clips.")
                elif input_type == "Choose from Downloads Folder" and video_path:
                    st.video(video_path)
                elif input_type == "Upload a Custom Video" and uploaded_video:
                    st.video(uploaded_video)
                else:
                    st.warning("No video source selected.")
            
            # Interactive Timeline Chart
            with st.container(border=True):
                st.markdown("""
                <div class="panel-title">📊 Activity Timeline Gantt Chart</div>
                <div class="panel-subtitle">Horizontal timeline of manual assembly operations.</div>
                """, unsafe_allow_html=True)
                
                if df_timeline is not None and not df_timeline.empty:
                    # Construct Gantt Plotly chart
                    fig = go.Figure()
                    
                    # Plotly Gantt implementation using horizontal bars
                    colors = ['#2563eb', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4']
                    
                    for idx, row in df_timeline.iterrows():
                        color = colors[idx % len(colors)]
                        fig.add_trace(go.Bar(
                            name=row['Activity_Label'],
                            x=[row['Duration_Sec']],
                            y=[row['Activity_Label']],
                            orientation='h',
                            base=[row['Start_Sec']],
                            marker=dict(color=color, line=dict(color='rgba(0,0,0,0)', width=0)),
                            hovertemplate=f"<b>{row['Activity_Label']}</b><br>" + 
                                          f"Start: {row.get('Start', 'N/A')}<br>" +
                                          f"End: {row.get('End', 'N/A')}<br>" + 
                                          f"Duration: {row.get('Duration', 'N/A')}<br>" + 
                                          f"Confidence: {row.get('Confidence Score', 'N/A')}<extra></extra>",
                            showlegend=False
                        ))
                    
                    fig.update_layout(
                        barmode='stack',
                        xaxis_title="Time (Seconds)",
                        yaxis=dict(
                            autorange="reversed",
                            tickfont=dict(size=11, color="#71717a" if not IS_DARK else "#a1a1aa"),
                        ),
                        xaxis=dict(
                            gridcolor="rgba(0,0,0,0.05)" if not IS_DARK else "rgba(255,255,255,0.05)",
                            zerolinecolor="rgba(0,0,0,0.05)" if not IS_DARK else "rgba(255,255,255,0.05)",
                            tickfont=dict(size=10, color="#71717a" if not IS_DARK else "#a1a1aa"),
                        ),
                        **PLOT_LAYOUT
                    )
                    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
                    
                    # Render the tabular timeline beneath the chart
                    st.markdown("<p style='font-size:0.75rem; color:var(--text-muted); font-weight:600; margin-top:10px;'>DETAILED WORK ELEMENT SHEET:</p>", unsafe_allow_html=True)
                    
                    # Format to a styled HTML Table
                    table_rows = ""
                    for _, r in df_timeline.iterrows():
                        act = r.get('Activity', r.get('Activity_Label'))
                        start = r.get('Start')
                        end = r.get('End')
                        dur = r.get('Duration')
                        conf = r.get('Confidence Score', 'N/A')
                        table_rows += f"<tr><td><strong>{act}</strong></td><td><code style='font-family:JetBrains Mono;'>{start}</code></td><td><code style='font-family:JetBrains Mono;'>{end}</code></td><td>{dur}</td><td><span class='badge badge-blue'>{conf}</span></td></tr>"
                    
                    st.html(f'<div style="overflow-x: auto; width: 100%;"><table class="data-table"><thead><tr><th>Activity</th><th>Start</th><th>End</th><th>Duration</th><th>Confidence</th></tr></thead><tbody>{table_rows}</tbody></table></div>')
                else:
                    st.warning("Failed to parse activity timeline table. Review raw report in 'Detailed AI Report' tab.")

        with dash_col2:
            # Waste Analysis & Bottlenecks
            with st.container(border=True):
                st.markdown("""
                <div class="panel-title">⚠️ Waste Identification & Bottlenecks</div>
                <div class="panel-subtitle">Industrial engineering assessment of manual workflow inefficiencies.</div>
                """, unsafe_allow_html=True)
                
                # Parsing Bottlenecks Section
                bottlenecks_sec = "Not found."
                pattern_bt = r"# Bottlenecks(.*?)(?:# AI Recommendations|# Productivity Score|$)"
                match_bt = re.search(pattern_bt, raw_text, re.DOTALL | re.IGNORECASE)
                if match_bt:
                    bottlenecks_sec = match_bt.group(1).strip()
                st.markdown(bottlenecks_sec)

            # AI Recommendations
            with st.container(border=True):
                st.markdown("""
                <div class="panel-title">💡 Kaizen (AI Recommendations)</div>
                <div class="panel-subtitle">Actionable improvements to reduce cycle time and eliminate waste.</div>
                """, unsafe_allow_html=True)
                
                # Parsing Recommendations Section
                recs_sec = "Not found."
                pattern_recs = r"# AI Recommendations(.*?)(?:# Productivity Score|# Estimated Time Savings|$)"
                match_recs = re.search(pattern_recs, raw_text, re.DOTALL | re.IGNORECASE)
                if match_recs:
                    recs_sec = match_recs.group(1).strip()
                st.markdown(recs_sec)
            
            # Confidence Summary
            with st.container(border=True):
                st.markdown("""
                <div class="panel-title">🎯 Time Study Confidence Profile</div>
                <div class="panel-subtitle">Algorithm metrics and calculated savings metadata.</div>
                """, unsafe_allow_html=True)
                
                sub_col1, sub_col2 = st.columns(2)
                with sub_col1:
                    st.markdown(f"**Estimated Time Savings:** `{metrics['Time Savings']}`")
                with sub_col2:
                    st.markdown(f"**Model Confidence Level:** `{metrics['Confidence Level']}`")

# TAB 2: Detailed Text Report
with tab_report:
    with st.container(border=True):
        st.markdown("""
        <div class="panel-title">📄 Raw Industrial Engineering Time Study Report</div>
        <div class="panel-subtitle">The full markdown document compiled by the AI.</div>
        """, unsafe_allow_html=True)
        
        if st.session_state.study_output:
            st.markdown(st.session_state.study_output)
        else:
            st.info("No report generated yet. Upload a video or load the mock demo in the dashboard tab.")
