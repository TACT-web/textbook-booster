import streamlit as st
import google.generativeai as genai
from PIL import Image
import io, json, time, re, random

# ==========================================
# ① UI・デザイン設定 & 高音質対応音声エンジン
# ==========================================
st.set_page_config(page_title="教科書ブースター V10.4", layout="centered", page_icon="🚀")

# 高音質音声エンジンのJSインジェクション
def inject_speech_script(text, speed):
    clean_text = re.sub(r'\(.*?\)|\[.*?行目\]|[*#/]', '', text).replace('"', "'").replace("\n", " ")
    english_chars = len(re.findall(r'[a-zA-Z]', clean_text))
    is_english = english_chars > (len(clean_text) / 2)
    target_lang = "en-US" if is_english else "ja-JP"
    js_code = f"""
    <script>
        (function() {{
            window.parent.speechSynthesis.cancel();
            const uttr = new SpeechSynthesisUtterance("{clean_text}");
            uttr.rate = {speed};
            const voices = window.parent.speechSynthesis.getVoices();
            let voice = voices.find(v => v.lang === "{target_lang}" && (v.name.includes("Google") || v.name.includes("Natural") || v.name.includes("Siri") || v.name.includes("Online")));
            if (!voice) voice = voices.find(v => v.lang.startsWith("{target_lang.split('-')[0]}"));
            if (voice) {{ uttr.voice = voice; uttr.lang = voice.lang; }} else {{ uttr.lang = "{target_lang}"; }}
            window.parent.speechSynthesis.speak(uttr);
        }})();
    </script>
    """
    st.components.v1.html(js_code, height=0, width=0)

# デザインCSS
st.markdown("""
    <style>
    header {visibility: hidden;}
    [data-testid="stHeader"] { display: none !important; }
    .stApp { background-color: #f0f2f5 !important; }
    .main-title { font-size: min(8vw, 35px); font-weight: 900; color: #1a365d; text-align: center; margin: 5px 0 15px 0; }
    .section-container { margin-bottom: 25px; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.06); background-color: white; }
    .section-band { padding: 12px 20px; color: white; font-weight: bold; font-size: 1.1rem; }
    .band-green { background: linear-gradient(90deg, #2ecc71, #27ae60); }
    .band-blue { background: linear-gradient(90deg, #3498db, #2980b9); }
    .band-pink { background: linear-gradient(90deg, #e91e63, #c2185b); }
    .content-body { padding: 25px; line-height: 1.9; }
    .speech-btn { display: inline-flex; align-items: center; justify-content: center; background: #3498db; color: white; border: none; border-radius: 50%; width: 34px; height: 34px; margin-left: 10px; cursor: pointer; font-size: 16px; vertical-align: middle; }
    .law-notice { background-color: #fff3cd; color: #856404; padding: 12px; border-radius: 8px; font-size: 0.85rem; line-height: 1.5; border: 1px solid #ffeeba; margin-bottom: 15px; }
    </style>
    """, unsafe_allow_html=True)

# セッション管理
if "final_json" not in st.session_state: st.session_state.final_json = None
if "explanation" not in st.session_state: st.session_state.explanation = ""
if "quiz_results" not in st.session_state: st.session_state.quiz_results = {}
if "agreed" not in st.session_state: st.session_state.agreed = False
if "show_speech_icons" not in st.session_state: st.session_state.show_speech_icons = False

TIPS = ["暗記は寝る前の15分が一番効率的！", "集中が切れたら青い色を見るとリラックスできるよ", "音読は脳を一番活性化させる勉強法だよ", "難しい問題は、小さく分解して考えよう"]

# --- ② サイドバー設定 ---
with st.sidebar:
    st.title("⚙️ アプリ設定")
    user_api_key = st.text_input("Gemini API Keyを入力", type="password")
    st.divider()
    st.subheader("📋 学習者設定")
    subject = st.selectbox("① 何を勉強する？", ["英語", "国語", "数学", "理科", "社会", "その他"])
    school_type = st.selectbox("② あなたの学校は？", ["小学生", "中学生", "高校生", "大学生・社会人"])
    grade = st.selectbox("③ 今何年生？", ["1年生", "2年生", "3年生", "4年生", "5年生", "6年生", "なし"])
    age_val = st.select_slider("④ 何歳レベルで解説する？", options=list(range(7, 26)), value=15)
    quiz_count = st.selectbox("⑤ 練習問題はいくつにする？", [3, 5, 10], index=0)
    mode = st.radio("⑥ 今日の解説スタイルは？", ["解説のみ", "対話形式", "自由入力"], horizontal=True)
    custom_style = st.text_input("具体的リクエスト", "") if mode == "自由入力" else ""

# --- A. 著作権同意 ---
if not st.session_state.agreed:
    st.markdown('<div class="main-title">🚀 教科書ブースター V10.4</div>', unsafe_allow_html=True)
    st.error("### ⚠️ 【重要】著作権に関する同意")
    st.markdown("""
    本アプリを利用するにあたり、以下の事項を遵守してください。
    1. **私的使用の範囲内**: 本人学習のみに使用すること。
    2. **公衆送信の禁止**: 解析結果をSNSや掲示板、ブログ等にアップロードしないこと。
    3. **再配布の禁止**: AI回答を他者に配布したり商用利用することを禁じます。
    """)
    if st.button("✅ 同意して学習を開始する", use_container_width=True):
        st.session_state.agreed = True
        st.rerun()
    st.stop()

st.markdown('<div class="law-notice">⚠️ <b>無断転載・公衆送信禁止</b><br>解析結果はあなたのデバイス内でのみ使用可能です。</div>', unsafe_allow_html=True)

# --- B. ステップ1：撮影 ---
st.markdown('<div class="section-container"><div class="section-band band-green">📸 ステップ1：教科書を撮影</div><div class="content-body">', unsafe_allow_html=True)
cam_image = st.camera_input("背面カメラ優先モード", label_visibility="collapsed")
st.markdown('</div></div>', unsafe_allow_html=True)

# --- C. 解析ロジック ---
if cam_image and st.button("✨ この設定で解析を開始！", use_container_width=True):
    if not user_api_key:
        st.error("サイドバーにAPIキーを入力してください。")
    else:
        genai.configure(api_key=user_api_key)
        model = genai.GenerativeModel('gemini-3-flash-preview')

        with st.status("🚀 AI先生が解析中...", expanded=True):
            st.write(f"💡 **豆知識:** {random.choice(TIPS)}")

            subjects_map = {
                "国語": "論理構造を分解し、筆者の主張を明確にしてください。",
                "数学": "公式の根拠を重視し、計算過程を一行ずつ解説してください。",
                "英語": "スラッシュリーディング形式（英文 / 訳）を徹底してください。",
                "理科": "現象のメカニズムを原理・法則から説明してください。",
                "社会": "歴史的背景と現代の繋がりをストーリー化してください。",
                "その他": "要点を3つのポイントに整理して解説してください。"
            }

            prompt = f"""あなたは【{school_type} {grade}】の内容を【{age_val}歳】に教える天才教師です。
            【教科別個別指示（{subject}）】{subjects_map.get(subject, "")}
            【構成】要約、重要語句、解説（[〇行目]と太字で根拠を明示）、ルビ対応。
            練習問題は ###JSON### の後に {quiz_count}問 出力してください。"""

            try:
                img = Image.open(cam_image)
                response = model.generate_content([prompt, img])
                st.session_state.explanation = response.text.split("###JSON###")[0]
                json_str = re.search(r"\{.*\}", response.text.split("###JSON###")[-1], re.DOTALL)
                if json_str: st.session_state.final_json = json.loads(json_str.group())
                st.rerun()
            except Exception as e: st.error(f"解析エラー: {e}")

# --- D. 解説エリア ---
if st.session_state.explanation:
    st.markdown('<div class="section-container"><div class="section-band band-blue">👨‍🏫 AI先生の徹底解説</div><div class="content-body">', unsafe_allow_html=True)
    speed = st.slider("🔊 読み上げ速度", 0.5, 2.0, 1.0, 0.1)
    col_v1, col_v2 = st.columns(2)
    with col_v1:
        if st.button("▶ 全体を聴く", use_container_width=True):
            inject_speech_script(st.session_state.explanation, speed)
    with col_v2:
        if st.button("⏹ 停止", use_container_width=True):
            st.components.v1.html("<script>window.parent.speechSynthesis.cancel();</script>", height=0)
    st.divider()
    sentences = re.split(r'(?<=[。？！])\s*', st.session_state.explanation)
    for s in sentences:
        if s.strip(): st.markdown(s)
    st.markdown('</div></div>', unsafe_allow_html=True)

# --- E. 練習問題エリア ---
if st.session_state.final_json:
    st.markdown('<div class="section-container"><div class="section-band band-pink">📝 練習問題</div><div class="content-body">', unsafe_allow_html=True)
    for i, q in enumerate(st.session_state.final_json.get("quizzes", [])):
        st.write(f"**問 {i+1}: {q.get('question')}**")
        ans = st.radio(f"選択 (問{i+1})", range(len(q.get('options', []))), format_func=lambda x: q.get('options')[x], key=f"q_{i}")
        if st.button(f"答え合わせ (問{i+1})", key=f"check_{i}"):
            if ans == q.get("answer"): st.success(f"正解！⭕ ({q.get('line')})")
            else: st.error(f"不正解❌ 正解は: {q.get('options')[q.get('answer')]} ({q.get('line')})")
    if st.button("🗑️ 学習を終了して戻る", use_container_width=True):
        st.session_state.final_json = st.session_state.explanation = None
        st.session_state.quiz_results = {}
        st.rerun()
    st.markdown('</div></div>', unsafe_allow_html=True)
