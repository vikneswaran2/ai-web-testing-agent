import sys
import os

# asyncio.WindowsProactorEventLoopPolicy is deprecated in Python 3.14+
# Only set if running Python < 3.14 to avoid deprecation warnings
import asyncio
if sys.platform == 'win32':
    import platform
    major, minor = map(int, platform.python_version_tuple()[:2])
    if major == 3 and minor < 14:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
# Try to import enhanced graph, fallback to original if not available
try:
    from agent.enhanced_graph import build_enhanced_batch_graph as build_batch_graph
except ImportError:
    from agent.graph_batch import build_batch_graph

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="AI Agent For Web Testing",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# --- ULTRA-FUTURISTIC CYBERPUNK CSS ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Inter:wght@300;400;600;800&family=JetBrains+Mono&display=swap');
    
    .stApp {
        background: #0f172a;
        background-image: 
            linear-gradient(rgba(99, 102, 241, 0.15) 1px, transparent 1px),
            linear-gradient(90deg, rgba(99, 102, 241, 0.15) 1px, transparent 1px);
        background-size: 50px 50px;
        background-attachment: fixed;
    }
    
    .stApp::after {
        content: "";
        position: fixed;
        top: 0; left: 0; width: 100%; height: 100%;
        background: radial-gradient(circle at 50% 50%, transparent 0%, rgba(15, 23, 42, 0.4) 100%);
        pointer-events: none;
        z-index: 0;
    }

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
        color: #f8fafc;
        letter-spacing: -0.01em;
    }

    .neon-title {
        font-family: 'Orbitron', sans-serif;
        font-weight: 900;
        font-size: 3rem !important;
        text-transform: uppercase;
        letter-spacing: 3px;
        background: linear-gradient(to right, #fff 0%, #818cf8 50%, #c084fc 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-shadow: 0 0 20px rgba(99, 102, 241, 0.4);
        margin: 0;
        padding-top: 10px;
    }

    .glass-card {
        background: rgba(30, 41, 59, 0.7);
        backdrop-filter: blur(20px);
        border: 1px solid rgba(99, 102, 241, 0.3);
        border-radius: 16px;
        padding: 1.8rem;
        margin-bottom: 1.2rem;
        box-shadow: 0 10px 40px rgba(0, 0, 0, 0.4);
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        position: relative;
    }
    
    .glass-card:hover {
        border-color: #818cf8;
        background: rgba(30, 41, 59, 0.85);
        box-shadow: 0 0 30px rgba(99, 102, 241, 0.3);
        transform: translateY(-2px);
    }
    
    .glass-card::before {
        content: "";
        position: absolute;
        top: 0; left: 0; width: 100%; height: 3px;
        background: linear-gradient(90deg, transparent, #818cf8, #c084fc, transparent);
        opacity: 0.6;
    }

    .stButton button {
        background: linear-gradient(90deg, #6366f1 0%, #a855f7 100%) !important;
        color: #fff !important;
        border: none !important;
        border-radius: 12px !important;
        font-family: 'Orbitron', sans-serif !important;
        font-weight: 800 !important;
        text-transform: uppercase !important;
        letter-spacing: 2px !important;
        transition: all 0.4s !important;
        height: 55px !important;
        margin-top: 15px !important;
        box-shadow: 0 4px 15px rgba(99, 102, 241, 0.3) !important;
    }
    
    .stButton button:hover {
        box-shadow: 0 0 25px rgba(99, 102, 241, 0.8) !important;
        transform: scale(1.03) translateY(-2px);
        background: linear-gradient(90deg, #818cf8 0%, #c084fc 100%) !important;
    }

    .stButton button[kind="secondary"] {
        background: rgba(255, 255, 255, 0.05) !important;
        border: 1px solid rgba(255,255,255,0.1) !important;
        color: #cbd5e1 !important;
    }
    
    .stButton button[kind="primary"] {
        background: linear-gradient(90deg, #4f46e5 0%, #7c3aed 100%) !important;
    }

    .stTextArea textarea {
        background: rgba(15, 23, 42, 0.5) !important;
        border: 1px solid rgba(99, 102, 241, 0.3) !important;
        color: #f8fafc !important;
        border-radius: 12px !important;
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 1rem !important;
    }

    [data-testid="stHeader"] { visibility: hidden; pointer-events: none; }
    [data-testid="stSidebar"] { display: none; }
    [data-testid="collapsedControl"] { display: none; }
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    .stDeployButton { display: none; }
    
    ::-webkit-scrollbar { width: 8px; }
    ::-webkit-scrollbar-track { background: #020617; }
    ::-webkit-scrollbar-thumb { background: #1e293b; border-radius: 10px; }
    ::-webkit-scrollbar-thumb:hover { background: #6366f1; }
    </style>
""", unsafe_allow_html=True)

# --- INTERNAL SETTINGS ---
timeout = 10000

# Initialize navigation state
if "active_tab" not in st.session_state:
    st.session_state.active_tab = "start"

# --- MAIN CONTENT ---
header_col1, header_col2 = st.columns([3, 1])
with header_col1:
    st.markdown('<h1 class="neon-title">AI WEB TESTING AGENT</h1>', unsafe_allow_html=True)

with header_col2:
    st.markdown("<div style='height: 25px;'></div>", unsafe_allow_html=True)
    headless = st.toggle("BACKGROUND MODE", value=True, help="Run browser without visual window")

st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)

# Custom Navigation
nav_col1, nav_col2, _ = st.columns([1, 1, 3])
with nav_col1:
    if st.button("🚀 START TESTING", use_container_width=True, type="primary" if st.session_state.active_tab == "start" else "secondary"):
        st.session_state.active_tab = "start"
        st.rerun()
with nav_col2:
    if st.button("📋 VIEW RESULTS", use_container_width=True, type="primary" if st.session_state.active_tab == "results" else "secondary"):
        st.session_state.active_tab = "results"
        st.rerun()

st.markdown("<br>", unsafe_allow_html=True)

if st.session_state.active_tab == "start":
    st.markdown("""
    <div class="glass-card">
        <h3 style="margin-top:0; font-family:'Orbitron', sans-serif; font-size:1.2rem; color:#6366f1; margin-bottom:0;">ENTER YOUR INSTRUCTIONS BELOW</h3>
    </div>
    """, unsafe_allow_html=True)

    instructions = st.text_area(
        "Enter your steps",
        height=180,
        placeholder="Go to https://google.com then search for 'AI Testing'\\nClick the first result\\nVerify the page loaded",
        value=st.session_state.get("draft_instructions", ""),
        label_visibility="collapsed"
    )

    with st.expander("⚙️ ADVANCED SETTINGS", expanded=False):
        col_set1, col_set2 = st.columns(2)

        with col_set1:
            use_ai_parsing = st.checkbox(
                "🤖 AI-Powered Parsing",
                value=True,
                help="Use Grok AI to understand complex instructions. Fallback to pattern matching if disabled."
            )

            custom_timeout = st.number_input(
                "Timeout (ms)",
                min_value=1000,
                max_value=60000,
                value=10000,
                step=1000,
                help="Maximum time to wait for actions to complete"
            )

        with col_set2:
            screenshot_each_step = st.checkbox(
                "📸 Screenshot Each Step",
                value=False,
                help="Capture screenshot after every action (increases execution time)"
            )

            max_retries = st.number_input(
                "Max Retries",
                min_value=0,
                max_value=5,
                value=3,
                help="Number of retry attempts for failed actions"
            )

    col_btn, _ = st.columns([1, 2])
    with col_btn:
        run_btn = st.button("🚀 RUN NOW")

    if run_btn:
        lines = [line.strip() for line in instructions.split("\n") if line.strip()]
        combined_instruction = " then ".join(lines)
        tests = [combined_instruction] if combined_instruction else []

        if not tests:
            st.warning("Please enter at least one step.")
        else:
            with st.status("🤖 INITIALIZING AI AGENT...", expanded=True) as status:
                st.write("📖 Parsing instructions with " + ("AI-powered understanding" if use_ai_parsing else "pattern matching") + "...")

                app = build_batch_graph()

                st.write("🏃 Executing tests with enhanced capabilities...")

                settings = {
                    "headless": headless,
                    "timeout": custom_timeout
                }

                try:
                    from agent.config import Config
                    Config.SCREENSHOT_EACH_STEP = screenshot_each_step
                    Config.MAX_RETRIES = max_retries
                except Exception as config_err:
                    st.warning(f"Config not applied: {config_err}")

                result = app.invoke({
                    "instructions": tests,
                    "settings": settings,
                    "use_ai_parsing": use_ai_parsing
                })

                status.update(label="🎉 ALL TESTS COMPLETED!", state="complete", expanded=False)

            st.session_state.last_result = result
            st.session_state.active_tab = "results"
            st.rerun()

elif st.session_state.active_tab == "results":
    if "last_result" in st.session_state:
        reports = st.session_state.last_result.get("reports", [])
        exec_results = st.session_state.last_result.get("exec_results", [])

        total_tests = len(exec_results)
        parsed_sets = st.session_state.last_result.get("parsed_sets", [])
        total_steps = sum(len(actions) for actions in parsed_sets)
        success_count = sum(1 for r in exec_results if r.get("success", False))
        failed_count = total_tests - success_count

        st.markdown(f"""
        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 25px;">
            <div class="glass-card" style="text-align: center; border-left: 4px solid #6366f1;">
                <p style="color: #6366f1; font-size: 0.65rem; text-transform: uppercase; letter-spacing:2px; font-weight:800; margin-bottom:5px;">📊 TOTAL TESTS</p>
                <h2 style="margin: 0; font-size: 2rem; font-family:'Orbitron'; font-weight:900; color:#fff;">{total_tests}</h2>
            </div>
            <div class="glass-card" style="text-align: center; border-left: 4px solid #3b82f6;">
                <p style="color: #3b82f6; font-size: 0.65rem; text-transform: uppercase; letter-spacing:2px; font-weight:800; margin-bottom:5px;">👣 TOTAL STEPS</p>
                <h2 style="margin: 0; font-size: 2rem; font-family:'Orbitron'; font-weight:900; color:#fff;">{total_steps}</h2>
            </div>
            <div class="glass-card" style="text-align: center; border-left: 4px solid #10b981;">
                <p style="color: #10b981; font-size: 0.65rem; text-transform: uppercase; letter-spacing:2px; font-weight:800; margin-bottom:5px;">✅ SUCCESS RATE</p>
                <h2 style="margin: 0; font-size: 2rem; color: #fff; font-family:'Orbitron'; font-weight:900;">{int((success_count/total_tests)*100) if total_tests > 0 else 0}%</h2>
            </div>
            <div class="glass-card" style="text-align: center; border-left: 4px solid #ef4444;">
                <p style="color: #ef4444; font-size: 0.65rem; text-transform: uppercase; letter-spacing:2px; font-weight:800; margin-bottom:5px;">⚠️ FAILURES</p>
                <h2 style="margin: 0; font-size: 2rem; color: #fff; font-family:'Orbitron'; font-weight:900;">{failed_count}</h2>
            </div>
        </div>
        """, unsafe_allow_html=True)

        for i, (rep, exec_res) in enumerate(zip(reports, exec_results)):
            success = exec_res.get("success", False)
            logs = exec_res.get("logs", [])
            screenshots = exec_res.get("screenshots", [])
            video_path = exec_res.get("video")
            html_report_path = rep['html_report']

            with st.container():
                st.markdown(f"""
                <div style="background: rgba(255,255,255,0.03); border-left: 5px solid {'#10b981' if success else '#ef4444'}; padding: 20px; border-radius: 12px; margin-bottom: 20px; backdrop-filter: blur(10px);">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <h3 style="margin: 0; color: white; font-family:'Orbitron'; letter-spacing:1px;">TEST #{i+1} SUMMARY</h3>
                        <span style="background: {'rgba(16, 185, 129, 0.1)' if success else 'rgba(239, 68, 68, 0.1)'}; color: {'#10b981' if success else '#ef4444'}; padding: 6px 16px; border-radius: 999px; font-size: 0.75rem; font-weight: 800; border: 1px solid {'#10b981' if success else '#ef4444'}; letter-spacing:1px;">
                            {'PASSED' if success else 'FAILED'}
                        </span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                col_left, col_right = st.columns([1.2, 1], gap="medium")

                with col_left:
                    st.markdown("<h4 style='font-family:Orbitron; font-size:0.9rem; color:#6366f1; margin-bottom:15px;'>📋 PROCESS DETAILS</h4>", unsafe_allow_html=True)
                    with st.expander("SEE STEP-BY-STEP LOGS", expanded=not success):
                        for log in logs:
                            if "[ERROR]" in log or "FAILED" in log:
                                st.error(log)
                            elif "[OK]" in log:
                                st.success(log)
                            elif "[WAIT]" in log or "[HEAL]" in log or "[AI" in log:
                                st.warning(log)
                            else:
                                st.info(log)

                    st.markdown("<div style='height:15px;'></div>", unsafe_allow_html=True)

                    btn_col1, btn_col2 = st.columns([1, 1])
                    with btn_col1:
                        if os.path.exists(html_report_path):
                            with open(html_report_path, "rb") as f:
                                st.download_button(
                                    label="🌐 DOWNLOAD HTML",
                                    data=f,
                                    file_name=os.path.basename(html_report_path),
                                    mime="text/html",
                                    key=f"dl_html_{i}",
                                    use_container_width=True
                                )

                    with btn_col2:
                        pdf_path = rep.get("pdf_report")
                        if pdf_path and os.path.exists(pdf_path):
                            with open(pdf_path, "rb") as f:
                                st.download_button(
                                    label="📥 DOWNLOAD PDF",
                                    data=f,
                                    file_name=os.path.basename(pdf_path),
                                    mime="application/pdf",
                                    key=f"dl_pdf_{i}",
                                    use_container_width=True
                                )

                    st.markdown("<div style='height:15px;'></div>", unsafe_allow_html=True)
                    if os.path.exists(html_report_path):
                        with open(html_report_path, "r", encoding="utf-8") as f:
                            html_content = f.read()
                        # st.components.v1.html replaced with st.iframe as per Streamlit deprecation
                        st.iframe(html_content, height=500, scrolling=True)
                    else:
                        st.error("Extended report file missing.")

                with col_right:
                    st.markdown("<h4 style='font-family:Orbitron; font-size:0.9rem; color:#6366f1; margin-bottom:15px;'>🖼️ VISUAL EVIDENCE</h4>", unsafe_allow_html=True)

                    if screenshots:
                        display_screenshots = screenshots[:3]
                        if len(screenshots) > 3:
                            st.caption(f"Showing 3 of {len(screenshots)} screenshots.")
                        cols_sc = st.columns(len(display_screenshots))
                        for idx, sc in enumerate(display_screenshots):
                            with cols_sc[idx]:
                                if os.path.exists(sc):
                                    try:
                                        with open(sc, "rb") as f:
                                            image_bytes = f.read()
                                        # use_container_width replaced with width='stretch'
                                        st.image(image_bytes, width='stretch', caption=f"Capture {idx+1}")
                                    except Exception as e:
                                        st.error(f"Error loading image: {e}")
                                else:
                                    st.warning(f"Image not found: {sc}")

                    if video_path and os.path.exists(video_path):
                        st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)
                        st.markdown("<p style='font-size:0.8rem; color:#94a3b8; font-family:Orbitron;'>VIDEO RECORDING</p>", unsafe_allow_html=True)
                        st.video(video_path)
                    elif not screenshots:
                        st.info("No visual data collected for this test.")

                st.markdown("<div style='height:60px; border-bottom: 1px solid rgba(255,255,255,0.05); margin-bottom:40px;'></div>", unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="glass-card" style="text-align:center; padding:100px 0;">
            <p style="color:#94a3b8;">NO TESTS RUN YET. START TESTING TO SEE RESULTS.</p>
        </div>
        """, unsafe_allow_html=True)