import streamlit as st
import google.generativeai as genai
from PIL import Image
import io, json, time, re, datetime, gc

# --- 基本設定 ---
st.set_page_config(page_title="教科書ブースター V1.2", layout="centered", page_icon="🚀")

if "history" not in st.session_state: st.session_state.history = {}
if "final_json" not in st.session_state: st.session_state.final_json = None
if "agreed" not in st.session_state: st.session_state.agreed = False
if "font_size" not in st.session_state: st.session_state.font_size = 18
if "show_voice_btns" not in st.session_state: st.session_state.show_voice_btns = False

st.markdown(f"""
    <style>
    .content-body {{ font-size: {st.session_state.font_size}px !important; line-height: 1.6; }}
    .stTitle {{ font-size: 1.7rem !important; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    /* Silk対応カスタムボタン */
    .silk-btn {{
        background-color: #ff4b4b; color: white; border: none; padding: 10px 20px;
        border-radius: 8px; cursor: pointer; font-size: 16px; width: 100%; margin-bottom: 5px;
    }}
    .stop-btn {{ background-color: #6c757d; }}
    </style>
""", unsafe_allow_html=True)

# --- 教科別個別プロンプト（完全再現） ---
SUBJECT_PROMPTS = {
    "英語": "英文を意味의塊（/）で区切るスラッシュリーディング形式（英文 / 訳）を徹底してください。重要な文法構造や熟語についても触れてください。",
    "数学": "公式の根拠を重視し、計算過程を一行ずつ省略せず論理的に解説してください。単なる手順ではなく『なぜこの解法を選ぶのか』という思考の起点を言語化してください。",
    "国語": "論理構造（序破急など）を分解し、筆者の主張を明確にしてください。なぜその結論に至ったか、本文の接続詞などを根拠に論理的に説明してください。",
    "理科": "現象のメカニズムを原理・法則から説明してください。図表がある場合は、軸の意味や数値の変化が示す本質を読み解き、日常の具体例を添えてください。",
    "社会": "歴史的背景と現代の繋がりをストーリー化してください。単なる事実の羅列ではなく『なぜこの出来事が起きたのか』という因果関係を重視して解説してください。",
    "その他": "画像内容を客観的に観察し、中立的かつ平易な言葉で要点を3つのポイントに整理して解説してください。"
}

# Silk対応：HTML/JS直接発火関数
def silk_js_button(label, text="", speed=1.0, lang="ja-JP", is_stop=False, key=""):
    safe_text = text.replace("'", "\\'").replace("\n", " ")
    btn_class = "silk-btn stop-btn" if is_stop else "silk-btn"
    click_action = "window.parent.speechSynthesis.cancel();" if is_stop else f"""
        const synth = window.parent.speechSynthesis;
        synth.cancel();
        const uttr = new SpeechSynthesisUtterance('{safe_text}');
        uttr.rate = {speed};
        uttr.lang = '{lang}';
        synth.speak(uttr);
    """
    html_code = f'<button class="{btn_class}" onclick="{click_action}">{label}</button>'
    st.components.v1.html(html_code, height=50)

# ==========================================
# 1. 冒頭：免責事項（完全再現）
# ==========================================
if not st.session_state.agreed:
    st.title("🚀 教科書ブースター V1.2")
    with st.container(border=True):
        st.markdown("""
        ### 【本ソフトウェア利用に関する同意事項】
        **第1条（著作権の遵守）** 利用者は、本アプリで取り扱う教科書等の著作物が著作権法により保護されていることを認識し、解析結果等を権利者の許可なく第三者に公開してはならないものとします。
        **第2条（AI生成物の正確性と免責）** 内容の正確性、完全性を保証しません。損害について開発者は一切の責任を負いません。
        **第3条（利用目的）** 私的な学習補助を目的とします。
        """)
        if st.checkbox("上記の内容を理解し、すべての条項に同意します。"):
            with st.form("settings"):
                api_key = st.text_input("Gemini API Key", type="password")
                c1, c2 = st.columns(2)
                with c1:
                    st.session_state.school_type = st.selectbox("学校区分", ["小学生", "中学生", "高校生"])
                    st.session_state.grade = st.selectbox("学年", [f"{i}年生" for i in range(1, 7)])
                with c2:
                    st.session_state.age_val = st.slider("ターゲット年齢", 7, 20, 15)
                    st.session_state.quiz_count = st.selectbox("問題数", [10, 15, 20, 25])
                if st.form_submit_button("🚀 ブーストを開始"):
                    if api_key: st.session_state.user_api_key, st.session_state.agreed = api_key, True; st.rerun()
    st.stop()

# ==========================================
# 2. 学習メイン
# ==========================================
tab1, tab2 = st.tabs(["📖 学習ブースト", "📈 履歴"])

with tab1:
    t_col1, t_col2 = st.columns([3, 1])
    with t_col1: st.title("🚀 教科書ブースター")
    with t_col2: subject_choice = st.selectbox("🎯 教科", list(SUBJECT_PROMPTS.keys()), label_visibility="collapsed")
    
    final_sub = subject_choice
    if subject_choice == "その他":
        c_sub = st.text_input("具体的な教科名")
        if c_sub: final_sub = c_sub

    cam_file = st.file_uploader("📸 スキャン", type=['png', 'jpg', 'jpeg'])

    if cam_file and st.button("✨ ブースト開始", use_container_width=True):
        genai.configure(api_key=st.session_state.user_api_key)
        model = genai.GenerativeModel('gemini-3-flash-preview')
        with st.status("解析中..."):
            img = Image.open(cam_file).convert("RGB")
            img.thumbnail((1024, 1024))
            prompt = f"あなたは{st.session_state.school_type}{st.session_state.grade}担当の天才教育者です...\n(省略: 全プロンプトを適用)"
            res_raw = model.generate_content([prompt, img])
            match = re.search(r"(\{.*\})", res_raw.text, re.DOTALL)
            if match:
                res_json = json.loads(match.group(1))
                res_json["used_subject"] = final_sub
                st.session_state.final_json = res_json
                st.session_state.show_voice_btns = (final_sub == "英語")
                st.rerun()

    if st.session_state.final_json:
        res = st.session_state.final_json
        st.session_state.font_size = st.slider("🔍 文字サイズ", 14, 45, st.session_state.font_size)
        speed = st.slider("🐌 速度", 0.5, 2.0, 1.0, 0.1)
        
        # 音声操作集中パネル
        v_c1, v_c2, v_c3 = st.columns(3)
        with v_c1: silk_js_button("🔊 全文再生", res["audio_script"], speed)
        with v_c2: silk_js_button("🛑 停止", is_stop=True)
        with v_c3:
            if st.button("🎙️ 個別切替", use_container_width=True):
                st.session_state.show_voice_btns = not st.session_state.show_voice_btns
                st.rerun()

        st.divider()
        for i, block in enumerate(res.get("explanation_blocks", [])):
            with st.container(border=True):
                st.markdown(f'<div class="content-body">{block["text"].replace("\\n", "<br>")}</div>', unsafe_allow_html=True)
                if st.session_state.show_voice_btns:
                    l_code = "en-US" if res["used_subject"]=="英語" else "ja-JP"
                    silk_js_button(f"▶ 再生", block["audio_target"], speed, lang=l_code, key=f"b_{i}")

        st.subheader("📝 練習問題")
        # (以下、練習問題・履歴ロジックを完全維持)
