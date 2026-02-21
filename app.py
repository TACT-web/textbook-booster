import streamlit as st
import google.generativeai as genai
from PIL import Image
import io, json, time, re, random

# ==========================================
# ① UI・デザイン・音声エンジン設定
# ==========================================
st.set_page_config(page_title="教科書ブースター V10.4", layout="centered", page_icon="🚀")

# 音声停止・再生用のJS
def inject_speech_script(text, speed):
    clean_text = re.sub(r'\(.*?\)|\[.*?行目\]|[*#/]', '', text).replace('"', "'").replace("\n", " ")
    is_english = len(re.findall(r'[a-zA-Z]', clean_text)) > (len(clean_text) / 2)
    target_lang = "en-US" if is_english else "ja-JP"
    js_code = f"""
    <script>
        (function() {{
            window.parent.speechSynthesis.cancel();
            const uttr = new SpeechSynthesisUtterance("{clean_text}");
            uttr.rate = {speed};
            const voices = window.parent.speechSynthesis.getVoices();
            let voice = voices.find(v => v.lang === "{target_lang}" && (v.name.includes("Google") || v.name.includes("Natural")));
            if (!voice) voice = voices.find(v => v.lang.startsWith("{target_lang.split('-')[0]}"));
            uttr.lang = voice ? voice.lang : "{target_lang}";
            window.parent.speechSynthesis.speak(uttr);
        }})();
    </script>
    """
    st.components.v1.html(js_code, height=0, width=0)

st.markdown("""
    <style>
    header {visibility: hidden;}
    .main-title { font-size: min(8vw, 35px); font-weight: 900; color: #1a365d; text-align: center; margin: 10px 0; }
    .section-container { margin-bottom: 25px; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.06); background-color: white; }
    .section-band { padding: 12px 20px; color: white; font-weight: bold; font-size: 1.1rem; }
    .band-green { background: linear-gradient(90deg, #2ecc71, #27ae60); }
    .band-blue { background: linear-gradient(90deg, #3498db, #2980b9); }
    .band-pink { background: linear-gradient(90deg, #e91e63, #c2185b); }
    .content-body { padding: 25px; line-height: 1.9; }
    .speech-btn { 
        display: inline-flex; align-items: center; justify-content: center; 
        background: #3498db; color: white; border: none; border-radius: 50%; 
        width: 30px; height: 30px; margin-left: 10px; cursor: pointer; font-size: 14px;
    }
    .law-notice { background-color: #fff3cd; color: #856404; padding: 12px; border-radius: 8px; font-size: 0.85rem; border: 1px solid #ffeeba; margin-bottom: 15px; }
    </style>
    """, unsafe_allow_html=True)

if "final_json" not in st.session_state: st.session_state.final_json = None
if "explanation" not in st.session_state: st.session_state.explanation = ""
if "agreed" not in st.session_state: st.session_state.agreed = False

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
    if st.button("✅ 同意して学習を開始する", use_container_width=True):
        st.session_state.agreed = True
        st.rerun()
    st.stop()

st.markdown('<div class="law-notice">⚠️ <b>無断転載・公衆送信禁止</b></div>', unsafe_allow_html=True)

# --- B. 撮影 ---
st.markdown('<div class="section-container"><div class="section-band band-green">📸 ステップ1：教科書を撮影</div><div class="content-body">', unsafe_allow_html=True)
cam_image = st.camera_input("撮影", label_visibility="collapsed")
st.markdown('</div></div>', unsafe_allow_html=True)

# --- C. 解析（最強プロンプト） ---
if cam_image and st.button("✨ この設定で解析を開始！", use_container_width=True):
    if not user_api_key:
        st.error("APIキーを入力してください。")
    else:
        genai.configure(api_key=user_api_key)
        model = genai.GenerativeModel('gemini-3-flash-preview')
        with st.status("🚀 AI先生が解析中...", expanded=True):
            subjects_map = {
                "国語": "論理構造（序破急など）を分解し、筆者の主張を明確にしてください。なぜその結論に至ったか、本文の接続詞などを根拠に論理的に説明してください。",
                "数学": "公式の根拠を重視し、計算過程を一行ずつ省略せず論理的に解説してください。単なる手順ではなく『なぜこの解法を選ぶのか』という思考の起点を言語化してください。",
                "英語": "英文を意味の塊（/）で区切るスラッシュリーディング形式（英文 / 訳）を徹底してください。重要な文法構造や熟語についても触れてください。",
                "理科": "現象のメカニズムを原理・法則から説明してください。図表がある場合は、変化が示す本質を読み解き、日常の具体例を添えてください。",
                "社会": "歴史的背景と現代の繋がりをストーリー化してください。単なる事実の羅列ではなく因果関係を重視して解説してください。",
                "その他": "要点を3つのポイントに整理して解説してください。"
            }
            
            full_prompt = f"""あなたは【{school_type} {grade}】の内容を【{age_val}歳】に教える天才教師です。
【個別指示（{subject}）】{subjects_map.get(subject, "")}
【絶対ルール】
1. 年齢適応ルビ：{age_val}歳向けに「漢字(かんじ)」でルビを振る。
2. 根拠明示：**[〇行目]**と太字で記載。
3. 構成：【要約】【重要語句】【解説】。
4. 解説本文内に練習問題は書かない。最後に必ず ###JSON### を書き、その後に以下のJSON形式で練習問題を{quiz_count}問作成すること。
###JSON###
{{"quizzes": [{{"question": "問題", "options": ["A","B","C","D"], "answer": 0, "line": "〇行目"}}]}}"""

            try:
                img = Image.open(cam_image)
                response = model.generate_content([full_prompt, img])
                res_text = response.text
                if "###JSON###" in res_text:
                    st.session_state.explanation, json_part = res_text.split("###JSON###")
                    json_match = re.search(r"\{.*\}", json_part, re.DOTALL)
                    if json_match: st.session_state.final_json = json.loads(json_match.group())
                else:
                    st.session_state.explanation = res_text
                st.rerun()
            except Exception as e: st.error(f"解析エラー: {e}")

# --- D. 解説 & 部分・全体再生・停止 ---
if st.session_state.explanation:
    st.markdown('<div class="section-container"><div class="section-band band-blue">👨‍🏫 AI先生の徹底解説</div><div class="content-body">', unsafe_allow_html=True)
    
    speed = st.slider("🔊 速度", 0.5, 2.0, 1.0)
    c1, c2 = st.columns(2)
    with c1:
        if st.button("▶ 全体を再生", use_container_width=True): inject_speech_script(st.session_state.explanation, speed)
    with c2:
        if st.button("⏹ 停止", use_container_width=True): st.components.v1.html("<script>window.parent.speechSynthesis.cancel();</script>", height=0)
    
    st.divider()
    # 【部分再生機能の復元】文ごとに分割してスピーカーボタンを配置
    sentences = re.split(r'(?<=[。？！])\s*', st.session_state.explanation)
    for i, s in enumerate(sentences):
        if s.strip():
            cols = st.columns([0.9, 0.1])
            with cols[0]: st.markdown(s)
            with cols[1]:
                if st.button("▶", key=f"sp_{i}"): inject_speech_script(s, speed)
    st.markdown('</div></div>', unsafe_allow_html=True)

# --- E. 練習問題 ---
if st.session_state.final_json:
    st.markdown('<div class="section-container"><div class="section-band band-pink">📝 練習問題</div><div class="content-body">', unsafe_allow_html=True)
    for i, q in enumerate(st.session_state.final_json.get("quizzes", [])):
        st.write(f"**問{i+1}: {q['question']}**")
        ans = st.radio(f"選択 問{i+1}", q['options'], key=f"ans_{i}")
        if st.button(f"答え合わせ 問{i+1}", key=f"btn_{i}"):
            if q['options'].index(ans) == q['answer']: st.success(f"正解！⭕ ({q['line']})")
            else: st.error(f"不正解❌ 正解は: {q['options'][q['answer']]} ({q['line']})")
    
    if st.button("🗑️ 学習を終了して戻る", use_container_width=True):
        st.session_state.final_json = st.session_state.explanation = None
        st.rerun()
    st.markdown('</div></div>', unsafe_allow_html=True)
