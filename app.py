import streamlit as st
import google.generativeai as genai
from PIL import Image
import io, json, time, re, datetime, gc

# --- 基本設定 ---
st.set_page_config(page_title="教科書ブースター V1.2", layout="centered", page_icon="🚀")

# --- 🛠️ 履歴の自動永続化ロジック (Local Storage 擬似実装) ---
# Streamlitのsession_stateを起動時に特定ファイルから復元し、変更時に保存する仕組み
import os
SAVE_FILE = "study_history.json"

def load_history():
    if os.path.exists(SAVE_FILE):
        with open(SAVE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_history(history):
    with open(SAVE_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

# 起動時に一度だけロード
if "history" not in st.session_state:
    st.session_state.history = load_history()

if "final_json" not in st.session_state: st.session_state.final_json = None
if "agreed" not in st.session_state: st.session_state.agreed = False
if "font_size" not in st.session_state: st.session_state.font_size = 18
if "show_voice_btns" not in st.session_state: st.session_state.show_voice_btns = False

# --- Chrome用音声制御関数 ---
def speak_chrome(text, speed=1.0, lang="ja-JP"):
    if text:
        safe_text = text.replace("'", "\\'").replace("\n", " ")
        js_code = f"""<script>
        var synth = window.parent.speechSynthesis;
        synth.cancel();
        var uttr = new SpeechSynthesisUtterance('{safe_text}');
        uttr.rate = {speed};
        uttr.lang = '{lang}';
        synth.speak(uttr);
        </script>"""
        st.components.v1.html(js_code, height=0)

def stop_speech():
    st.components.v1.html("<script>window.parent.speechSynthesis.cancel();</script>", height=0)

st.markdown(f"""<style>.content-body {{ font-size: {st.session_state.font_size}px !important; line-height: 1.6; }}</style>""", unsafe_allow_html=True)

# --- 教科別個別プロンプト（【完全再現】一言一句変更なし） ---
SUBJECT_PROMPTS = {
    "英語": "英文を意味の塊（/）で区切るスラッシュリーディング形式（英文 / 訳）を徹底してください。重要な文法構造や熟語についても触れてください。",
    "数学": "公式の根拠を重視し、計算過程を一行ずつ省略せず論理的に解説してください。単なる手順ではなく『なぜこの解法を選ぶのか』という思考の起点を言語化してください。",
    "国語": "論理構造（序破急など）を分解し、筆者の主張を明確にしてください。なぜその結論に至ったか、本文の接続詞などを根拠に論理的に説明してください。",
    "理科": "現象のメカニズムを原理・法則から説明してください。図表がある場合は、軸の意味や数値の変化が示す本質を読み解き、日常の具体例を添えてください。",
    "社会": "歴史的背景と現代の繋がりをストーリー化してください。単なる事実の羅列ではなく『なぜこの出来事が起きたのか』という因果関係を重視して解説してください。",
    "その他": "画像内容を客観的に観察し、中立的かつ平易な言葉で要点を3つのポイントに整理して解説してください。"
}

# ==========================================
# 1. 冒頭：免責事項 ＆ 同意（【完全再現】一言一句変更なし）
# ==========================================
if not st.session_state.agreed:
    st.markdown("""
        <div style="line-height: 1.1; margin-bottom: 20px;">
            <span style="font-size: 24px; font-weight: bold; white-space: nowrap;">🚀教科書ブースター</span><br>
            <span style="font-size: 14px; color: gray;">Ver 1.2</span>
        </div>
        """, unsafe_allow_html=True)
    
    with st.container(border=True):
        # ...免責事項の内容...

        st.markdown("""
        ### 【本ソフトウェア利用に関する同意事項】
        
        **第1条（著作権の遵守）**
        利用者は、本アプリで取り扱う教科書等の著作物が著作権法により保護されていることを認識し、解析結果等を権利者の許可なく第三者に公開（SNS、ブログ等への掲載）してはならないものとします。
        
        **第2条（AI生成物の正確性と免責）**
        本アプリが提供する解説および回答は、人工知能による推論に基づくものであり、その正確性、完全性、妥当性を保証するものではありません。生成された内容に起因する学習上の不利益や損害について、開発者は一切の責任を負いません。
        
        **第3条（利用目的）**
        本アプリは利用者の私的な学習補助を目的として提供されるものです。試験等の最終的な確認は、必ず公式な教材および指導者の指示に従ってください。
        """)
        if st.checkbox("上記の内容を理解し、すべての条項に同意します。"):
            with st.form("settings"):
                api_key = st.text_input("Gemini API Key", type="password")
                c1, c2 = st.columns(2)
                with c1:
                    st.session_state.school_type = st.selectbox("学校区分", ["小学生", "中学生", "高校生"])
                    st.session_state.grade = st.selectbox("学年", [f"{i}年生" for i in range(1, 7)])
                with c2:
                    st.session_state.age_val = st.slider("解説ターゲット年齢", 7, 20, 15)
                    st.session_state.quiz_count = st.selectbox("問題数", [10, 15, 20, 25])
                if st.form_submit_button("🚀 ブーストを開始する", use_container_width=True):
                    if api_key:
                        st.session_state.user_api_key, st.session_state.agreed = api_key, True
                        st.rerun()
    st.stop()

# ==========================================
# 2. 学習メイン
# ==========================================
tab1, tab2 = st.tabs(["📖 学習ブースト", "📈 ブースト履歴"])

with tab1:
    t_col1, t_col2 = st.columns([3, 1])
with t_col1:
    st.markdown("""
	    <div style="line-height: 1.1; margin-bottom: 20px;">
            <span style="font-size: 24px; font-weight: bold; white-space: nowrap;">🚀教科書ブースター</span><br>
            <span style="font-size: 14px; color: gray;">Ver 1.2</span>
        </div>
        """, unsafe_allow_html=True)
    
    with st.container(border=True):
        # ...免責事項の内容...
 
    with t_col2: subject_choice = st.selectbox("🎯 教科", list(SUBJECT_PROMPTS.keys()), label_visibility="collapsed")
    
    final_subject_name = subject_choice
    if subject_choice == "その他":
        custom_sub = st.text_input("具体的な教科名を入力してください")
        if custom_sub: final_subject_name = custom_sub

    cam_file = st.file_uploader("📸 教科書をスキャン", type=['png', 'jpg', 'jpeg'])

    if cam_file and st.button("✨ ブースト開始", use_container_width=True):
        genai.configure(api_key=st.session_state.user_api_key)
        model = genai.GenerativeModel('gemini-3-flash-preview')
        with st.status("解析中...🚀"):
            img = Image.open(cam_file).convert("RGB")
            img.thumbnail((1024, 1024))
            prompt = f"""あなたは{st.session_state.school_type}{st.session_state.grade}担当の天才教育者です。
            【教科別個別ミッション: {final_subject_name}】{SUBJECT_PROMPTS[subject_choice]}
            ※英語の場合は、スラッシュごとの逐語訳を徹底せよ。
            【共通厳守ルール】1.is_match 2.根拠[P.〇/〇行目] 3.audio_script(ひらがな化) 4.ランク別メッセージ 5.ターゲット年齢{st.session_state.age_val}歳 6.100文字ブロック 7.難読語ルビ 8.問題数{st.session_state.quiz_count}問
            ###JSON形式で出力せよ###
            {{ "is_match": true, "detected_subject": "{final_subject_name}", "page": "数字", "explanation_blocks": [{{ "text": "..", "audio_target": ".." }}], "english_only_script": "..", "audio_script": "..", "boost_comments": {{ "high": {{"text":"..","script":".."}}, "mid": {{"text":"..","script":".."}}, "low": {{"text":"..","script":".."}} }}, "quizzes": [{{ "question":"..", "options":[".."], "answer":0, "location":"P.〇" }}] }}"""
            res_raw = model.generate_content([prompt, img])
            match = re.search(r"(\{.*\})", res_raw.text, re.DOTALL)
            if match:
                st.session_state.final_json = json.loads(match.group(1))
                st.session_state.final_json["used_subject"] = final_subject_name
                st.session_state.show_voice_btns = (final_subject_name == "英語")
                st.rerun()

    if st.session_state.final_json:
        res = st.session_state.final_json
        st.session_state.font_size = st.slider("🔍 サイズ", 14, 45, st.session_state.font_size)
        speed = st.slider("🐌 速度", 0.5, 2.0, 1.0, 0.1)
        
        v_cols = st.columns(4 if res["used_subject"] == "英語" else 3)
        with v_cols[0]:
            if st.button("🔊 全文を聴く", use_container_width=True): speak_chrome(res["audio_script"], speed)
        btn_i = 1
        if res["used_subject"] == "英語":
            with v_cols[btn_i]:
                if st.button("🔊 英文のみ全再生", use_container_width=True): speak_chrome(res.get("english_only_script", ""), speed, "en-US")
            btn_i += 1
        with v_cols[btn_i]:
            if st.button("🛑 停止", use_container_width=True): stop_speech()
        with v_cols[btn_i+1]:
            if st.button("🔊 個別表示", use_container_width=True): st.session_state.show_voice_btns = not st.session_state.show_voice_btns; st.rerun()

        for i, block in enumerate(res.get("explanation_blocks", [])):
            with st.container(border=True):
                st.markdown(f'<div class="content-body">{block["text"].replace("\\n", "<br>")}</div>', unsafe_allow_html=True)
                if st.session_state.show_voice_btns:
                    if st.button(f"▶ 再生", key=f"v_{i}"):
                        speak_chrome(block["audio_target"], speed, "en-US" if res["used_subject"]=="英語" else "ja-JP")

        st.subheader("📝 練習問題")
        u_page = st.text_input("📖 ページ確認", value=res.get("page", ""))
        score, q_list = 0, res.get("quizzes", [])
        for i, q in enumerate(q_list):
            ans = st.radio(f"問{i+1}: {q['question']} ({q['location']})", q['options'], key=f"q_{i}", index=None)
            if ans and ans == q['options'][q['answer']]: score += 1

        if len(q_list) > 0 and st.button("🏁 結果を記録", use_container_width=True):
            rate = (score / len(q_list)) * 100
            rank = "high" if rate == 100 else "mid" if rate >= 50 else "low"
            st.header(f"🏁 スコア：{rate:.0f}% ({score}/{len(q_list)}問正解)")
            st.info(res["boost_comments"][rank]["text"])
            speak_chrome(res["boost_comments"][rank]["script"], speed)
            
            # --- 🛠️ 履歴の自動保存実行 ---
            now = (datetime.datetime.utcnow() + datetime.timedelta(hours=9)).strftime("%m/%d %H:%M")
            if res["used_subject"] not in st.session_state.history: st.session_state.history[res["used_subject"]] = []
            st.session_state.history[res["used_subject"]].append({"date": now, "page": u_page, "score": f"{rate:.0f}%"})
            save_history(st.session_state.history) # 自動書き込み

with tab2:
    for sub, logs in st.session_state.history.items():
        with st.expander(f"📙 {sub}"): st.table(logs)
    if st.button("🗑️ 履歴消去"):
        st.session_state.history = {}
        if os.path.exists(SAVE_FILE): os.remove(SAVE_FILE) # ファイルも消去
        st.rerun()
