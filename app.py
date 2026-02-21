import streamlit as st
import google.generativeai as genai
from PIL import Image
import io, json, time, re, random

# ==========================================
# ① 基本設定 & デザイン & 音声エンジン
# ==========================================
st.set_page_config(page_title="教科書ブースター V10.4", layout="centered", page_icon="🚀")

def inject_speech_script(text, speed):
    # ルビ「漢字(かんじ)」のカッコ内を除去する正規表現を強化
    clean_text = re.sub(r'\(.*?\)', '', text)
    # その他の記号や改行をクリーンアップ
    clean_text = re.sub(r'\[.*?行目\]|[*#/]', '', clean_text).replace('"', "'").replace("\n", " ")
    
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
    .law-notice { background-color: #fff3cd; color: #856404; padding: 15px; border-radius: 8px; font-size: 0.9rem; border: 1px solid #ffeeba; margin-bottom: 20px; }
    .agree-text { text-align: center; font-weight: bold; font-size: 1.2rem; color: #d32f2f; line-height: 1.4; margin-bottom: 20px; }
    </style>
    """, unsafe_allow_html=True)

if "final_json" not in st.session_state: st.session_state.final_json = None
if "explanation" not in st.session_state: st.session_state.explanation = ""
if "agreed" not in st.session_state: st.session_state.agreed = False

# --- A. 初期設定 ＆ 同意画面（一括統合） ---
if not st.session_state.agreed:
    st.markdown('<div class="main-title">🚀 教科書ブースター V10.4</div>', unsafe_allow_html=True)
    
    # 視認性を高めた3行メッセージ
    st.markdown("""
    <div class="agree-text">
        最初に個人設定と<br>
        著作権保護の同意を<br>
        お願いします。
    </div>
    """, unsafe_allow_html=True)
    
    user_api_key = st.text_input("🔑 Gemini API Keyを入力 (使用モデル: gemini-2.0-flash)", type="password", placeholder="AIzaSy...")
    
    st.divider()
    
    col_a, col_b = st.columns(2)
    with col_a:
        st.session_state.school_type = st.selectbox("② あなたの学校は？", ["小学生", "中学生", "高校生", "大学生・社会人"])
        st.session_state.grade = st.selectbox("③ 今何年生？", ["1年生", "2年生", "3年生", "4年生", "5年生", "6年生", "なし"])
    with col_b:
        st.session_state.age_val = st.select_slider("④ 何歳レベルで解説する？", options=list(range(7, 26)), value=15)
        st.session_state.quiz_count = st.selectbox("⑤ 練習問題の数", [5, 10, 15, 20], index=2) # デフォルト15問
    
    st.session_state.mode = st.radio("⑥ 今日の解説スタイルは？", ["解説のみ", "対話形式", "自由入力"], horizontal=True)
    st.session_state.custom_style = st.text_input("具体的リクエスト", "") if st.session_state.mode == "自由入力" else ""

    st.markdown("""
    <div style="background-color: #f8f9fa; padding: 15px; border-radius: 10px; font-size: 0.85rem; border: 1px solid #ddd;">
    <strong>【著作権および利用に関する重要事項】</strong><br>
    本アプリは、ユーザーが所有する教科書等の学習を支援するためのツールです。利用にあたっては以下の条件に同意したものとみなされます。<br><br>
    1. <strong>私的使用の遵守</strong>：本アプリで生成された回答や画像解析結果は、利用者本人の学習目的以外（営利目的、または第三者への提供）には使用できません。<br>
    2. <strong>公衆送信の禁止</strong>：教科書の画像や、本アプリによる解析結果（文章・問題）をインターネット上のSNS、掲示板、ブログ等へ転載・アップロードすることを固く禁じます。<br>
    3. <strong>権利の尊重</strong>：解析対象となる著作物の著作者の権利を侵害しないよう、適切な範囲内で利用してください。<br>
    4. <strong>再配布・商用利用の禁止</strong>：AIによる生成内容を、自身の教材として販売したり、無断で配布したりすることはできません。
    </div>
    """, unsafe_allow_html=True)
    
    if st.button("✅ 設定と著作権事項に同意して開始", use_container_width=True):
        if not user_api_key:
            st.warning("APIキーを入力してください。")
        else:
            st.session_state.user_api_key = user_api_key
            st.session_state.agreed = True
            st.rerun()
    st.stop()

# --- B. メイン画面：教科指定 ＆ 撮影 ---
st.markdown('<div class="law-notice">⚠️ <b>無断転載・公衆送信禁止</b>：解析結果の外部公開は法律で禁じられています。</div>', unsafe_allow_html=True)

st.markdown('<div class="section-container"><div class="section-band band-green">📸 教科指定と撮影</div><div class="content-body">', unsafe_allow_html=True)

subject = st.selectbox("🎯 学習する教科を選択してください", ["英語", "国語", "数学", "理科", "社会", "その他"])

st.write("👇 教科書を撮影してください")
st.caption("（切り替えアイコン🔄が表示される場合は、<br>タップして背面カメラを選択してください）", unsafe_allow_html=True)

cam_image = st.camera_input("カメラ起動", label_visibility="collapsed")

st.markdown('</div></div>', unsafe_allow_html=True)

# --- C. 解析（Gemini 2.0 Flash 指定） ---
if cam_image and st.button("✨ AI先生の解析をリクエスト", use_container_width=True):
    genai.configure(api_key=st.session_state.user_api_key)
    # 3-flash-previewの後継である2.0-flashを指定
    model = genai.GenerativeModel('gemini-3-flash-preview')
    with st.status("🚀 最先端AIが教科書を読み解いています...", expanded=True):
        subjects_map = {
            "国語": "論理構造を分解し、筆者の主張を接続詞などの根拠に基づき論理的に説明してください。",
            "数学": "公式の根拠を重視し、計算過程を一行ずつ省略せず、なぜその解法を選ぶのかを言語化してください。",
            "英語": "スラッシュリーディング形式（英文 / 訳）を徹底し、重要な文法や熟語を解説してください。",
            "理科": "現象のメカニズムを原理・法則から説明し、日常の具体例を添えてください。",
            "社会": "歴史的背景と現代の繋がりをストーリー化し、因果関係を重視して解説してください。",
            "その他": "要点を3つのポイントに整理して分かりやすく解説してください。"
        }
        
        full_prompt = f"""あなたは【{st.session_state.school_type} {st.session_state.grade}】の内容を【{st.session_state.age_val}歳】に教える天才教師です。
【教科別指示（{subject}）】{subjects_map.get(subject, "")}
【絶対遵守】
1. ルビ：{st.session_state.age_val}歳向けに全ての未習漢字へ「漢字(かんじ)」の形式でルビを振る。
2. 根拠：本文の該当箇所を **[〇行目]** と太字で示す。
3. 構成：【要約】【重要語句】【解説】の順。
4. 練習問題：解説内には書かず、最後に ###JSON### の後に必ず【{st.session_state.quiz_count}問】作成すること。
###JSON###
{{"quizzes": [{{"question": "問題文", "options": ["選1","選2","選3","選4"], "answer": 0, "line": "〇行目"}}]}}"""

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

# --- D. 解説表示 & 再生機能（部分音声はボタン格納型） ---
if st.session_state.explanation:
    st.markdown('<div class="section-container"><div class="section-band band-blue">👨‍🏫 AI先生の徹底解説</div><div class="content-body">', unsafe_allow_html=True)
    speed = st.slider("🔊 読み上げ速度", 0.5, 2.0, 1.0)
    c1, c2 = st.columns(2)
    with c1:
        if st.button("▶ 全体を再生", use_container_width=True): inject_speech_script(st.session_state.explanation, speed)
    with c2:
        if st.button("⏹ 停止", use_container_width=True): st.components.v1.html("<script>window.parent.speechSynthesis.cancel();</script>", height=0)
    
    st.divider()
    
    # 文章ごとに分割
    sentences = re.split(r'(?<=[。？！])\s*', st.session_state.explanation)
    for i, s in enumerate(sentences):
        if s.strip():
            # 部分読み上げをボタン内に隠す（視認性向上）
            with st.expander(s, expanded=True):
                if st.button("🔊 この文を聴く", key=f"v_{i}"):
                    inject_speech_script(s, speed)
    st.markdown('</div></div>', unsafe_allow_html=True)

# --- E. 練習問題（修正・安定化） ---
if st.session_state.final_json:
    st.markdown('<div class="section-container"><div class="section-band band-pink">📝 練習問題</div><div class="content-body">', unsafe_allow_html=True)
    quizzes = st.session_state.final_json.get("quizzes", [])
    for i, q in enumerate(quizzes):
        st.write(f"**問{i+1}: {q.get('question', '')}**")
        opts = q.get('options', ["A", "B", "C", "D"])
        ans = st.radio(f"選択 (問{i+1})", opts, key=f"q_{i}", label_visibility="collapsed")
        if st.button(f"答え合わせ (問{i+1})", key=f"b_{i}"):
            correct_idx = q.get('answer', 0)
            if opts.index(ans) == correct_idx:
                st.success(f"正解！⭕ ({q.get('line', '')})")
            else:
                st.error(f"不正解❌ 正解は: {opts[correct_idx]} ({q.get('line', '')})")
    
    if st.button("🗑️ 学習をリセットして最初に戻る", use_container_width=True):
        st.session_state.final_json = st.session_state.explanation = None
        st.rerun()
    st.markdown('</div></div>', unsafe_allow_html=True)
