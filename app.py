import streamlit as st
import google.generativeai as genai
from PIL import Image
import io, json, time, re, datetime, gc

# --- 基本設定 ---
APP_TITLE = "教科書ブースター 🚀"
st.set_page_config(page_title=APP_TITLE, layout="centered", page_icon="🚀")

# アイコン背景白・ホーム画面名固定
st.markdown(f"""
    <head>
        <meta name="apple-mobile-web-app-title" content="{APP_TITLE}">
        <meta name="apple-mobile-web-app-capable" content="yes">
        <meta name="theme-color" content="#FFFFFF">
        <link rel="apple-touch-icon" href="https://cdnjs.cloudflare.com/ajax/libs/twemoji/14.0.2/72x72/1f680.png">
    </head>
""", unsafe_allow_html=True)

if "history" not in st.session_state: st.session_state.history = {}
if "final_json" not in st.session_state: st.session_state.final_json = None
if "agreed" not in st.session_state: st.session_state.agreed = False
if "font_size" not in st.session_state: st.session_state.font_size = 18
if "show_voice_btns" not in st.session_state: st.session_state.show_voice_btns = False

st.markdown(f"""
    <style>
    .content-body {{ font-size: {st.session_state.font_size}px !important; line-height: 1.6; }}
    .stTitle {{ font-size: 1.7rem !important; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    </style>
""", unsafe_allow_html=True)

# --- 教科別個別プロンプト（【完全再現】一言一句変更なし） ---
SUBJECT_PROMPTS = {
    "英語": "英文を意味の塊（/）で区切るスラッシュリーディング形式（英文 / 訳）を徹底してください。重要な文法構造や熟語についても触れてください。",
    "数学": "公式の根拠を重視し、計算過程を一行ずつ省略せず論理的に解説してください。単なる手順ではなく『なぜこの解法を選ぶのか』という思考の起点を言語化してください。",
    "国語": "論理構造（序破急など）を分解し、筆者の主張を明確にしてください。なぜその結論に至ったか、本文の接続詞などを根拠に論理的に説明してください。",
    "理科": "現象のメカニズムを原理・法則から説明してください。図表がある場合は、軸の意味や数値の変化が示す本質を読み解き、日常の具体例を添えてください。",
    "社会": "歴史的背景と現代の繋がりをストーリー化してください。単なる事実の羅列ではなく『なぜこの出来事が起きたのか』という因果関係を重視して解説してください。",
    "その他": "画像内容を客観的に観察し、中立的かつ平易な言葉で要点を3つのポイントに整理して解説してください。"
}

# --- 音声合成エンジン（Silk/Safari対応版） ---
def inject_speech_script(text_list=None, speed=1.0, stop=False, is_english=False):
    if stop:
        js_code = "<script>window.parent.speechSynthesis.cancel();</script>"
    else:
        if isinstance(text_list, str): text_list = [text_list]
        json_texts = json.dumps(text_list, ensure_ascii=False)
        lang = "en-US" if is_english else "ja-JP"
        js_code = f"""
        <script>
            (function() {{
                const synth = window.parent.speechSynthesis;
                synth.cancel();
                const texts = {json_texts};
                const speak = () => {{
                    texts.forEach((txt) => {{
                        const uttr = new SpeechSynthesisUtterance(txt.replace(/\\\\n/g, ' '));
                        uttr.rate = {speed};
                        uttr.lang = "{lang}";
                        synth.speak(uttr);
                    }});
                }};
                if (synth.getVoices().length === 0) {{
                    window.parent.speechSynthesis.onvoiceschanged = speak;
                }} else {{ speak(); }}
            }})();
        </script>
        """
    st.components.v1.html(js_code, height=0, width=0)

# ==========================================
# 1. 冒頭：免責事項 ＆ 同意（【完全再現】一言一句変更なし）
# ==========================================
if not st.session_state.agreed:
    st.title("🚀 教科書ブースター V1.2")
    with st.container(border=True):
        st.markdown("""
        ### 【本ソフトウェア利用に関する同意事項】
        
        **第1条（著作権の遵守）**
        利用者は、本アプリで取り扱う教科書等の著作物が著作権法により保護されていることを認識し、解析結果等を権利者の許可なく第三者に公開（SNS、ブログ等への掲載）してはならないものとします。
        
        **第2条（AI生成物の正確性と免責）**
        本アプリが提供する解説および回答は、人工知能による推論に基づくものであり、その正確性、完全性、妥当性を保証するものではありません。生成された内容に起因する学習上の不利益や損害について、開発者は一切の責任を負いません。
        
        **第3条（利用目的）**
        本アプリは利用者の私的な学習補助を目的として提供されるものです。試験等の最終的な確認は、必ず公式な教材および指導者の指示に従ってください。
        """)
        agree_check = st.checkbox("上記の内容を理解し、すべての条項に同意します。")

    if agree_check:
        with st.form("init_form"):
            st.subheader("🛠️ 学習ブースト設定")
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
                else: st.error("APIキーを入力してください。")
    st.stop()

# ==========================================
# 2. 学習メイン機能
# ==========================================
tab1, tab2 = st.tabs(["📖 学習ブースト", "📈 ブースト履歴"])

with tab1:
    t_col1, t_col2 = st.columns([3, 1])
    with t_col1: st.title("🚀 教科書ブースター")
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
            
            # プロンプト（【完全再現】一言一句変更なし）
            prompt = f"""あなたは{st.session_state.school_type}{st.session_state.grade}担当の天才教育者です。
            
            【教科別個別ミッション: {final_subject_name}】
            {SUBJECT_PROMPTS[subject_choice]}
            ※英語の場合は、スラッシュごとの逐語訳（直訳）を徹底し、返り読みをしない順序で[ 英文 / 訳 ]の形式を厳守せよ。

            【共通厳守ルール】
            1. 画像内の教科が「{final_subject_name}」に関連しない場合は is_match: false として即終了せよ。
            2. 根拠箇所を必ず [P.〇 / 〇行目] の形式で本文末尾に太字で付加せよ。
            3. audio_scriptは記号や数式を自然な日本語の読み（ひらがな）に変換せよ。
            4. 正答率別のブーストメッセージ(high, mid, low)を音声台本付きで作れ。
            5. 解説は{st.session_state.age_val}歳に最適な言葉を選べ。
            6. 出力は100文字前後のブロックに分け、英語なら「英文\\n解説」の構成にせよ。
            7. 年齢別ルビ: 常用漢字には振らず、難読語にのみ「漢字(かんじ)」でルビを振れ。1ブロックにつきルビは最大2箇所。
            8. 問題数指定: 練習問題(quizzes)は必ず「{st.session_state.quiz_count}問」生成すること。

            ###JSON形式で出力せよ###
            {{
                "is_match": true,
                "detected_subject": "{final_subject_name}",
                "page": "数字",
                "explanation_blocks": [
                    {{"text": "本文・英文\\n解説", "audio_target": "再生用テキスト(英語なら英文のみ)"}}
                ],
                "audio_script": "解説全文の台本",
                "boost_comments": {{"high":{{"text":"..","script":".."}},"mid":{{"text":"..","script":".."}},"low":{{"text":"..","script":".."}}}},
                "quizzes": [{{ "question":"..", "options":["A","B","C","D"], "answer":0, "location":"P.〇" }}]
            }}"""
            
            res_raw = model.generate_content([prompt, img])
            del img; gc.collect()
            res_json = json.loads(re.search(r"\{.*\}", res_raw.text, re.DOTALL).group())
            res_json["used_subject"] = final_subject_name
            st.session_state.final_json = res_json
            st.session_state.show_voice_btns = (final_subject_name == "英語")
            st.rerun()

    if st.session_state.final_json:
        res = st.session_state.final_json
        speed = st.slider("🐌 音声速度調整", 0.5, 2.0, 1.0, 0.1)
        col_v1, col_v2, col_v3 = st.columns(3)
        with col_v1: 
            if st.button("🔊 再生", use_container_width=True): inject_speech_script(res["audio_script"], speed)
        with col_v2:
            if st.button("🛑 停止", use_container_width=True): inject_speech_script(stop=True)
        with col_v3:
            if st.button("🎙️ 個別音声切替", use_container_width=True): st.session_state.show_voice_btns = not st.session_state.show_voice_btns; st.rerun()

        st.session_state.font_size = st.slider("🔍 文字サイズ調整", 14, 45, st.session_state.font_size)
        st.divider()
        for i, block in enumerate(res.get("explanation_blocks", [])):
            with st.container(border=True):
                st.markdown(f'<div class="content-body">{block["text"].replace("\\n", "<br>")}</div>', unsafe_allow_html=True)
                if st.session_state.show_voice_btns:
                    if st.button(f"▶ 個別再生", key=f"v_{i}"): inject_speech_script(block["audio_target"], speed, is_english=(res.get("used_subject")=="英語"))

        st.subheader("📝 練習問題")
        score, q_list = 0, res.get("quizzes", [])
        for i, q in enumerate(q_list):
            ans = st.radio(f"問{i+1}: {q['question']} ({q['location']})", q['options'], key=f"q_{i}", index=None)
            if ans:
                if ans == q['options'][q['answer']]:
                    st.success("⭕ 正解！"); score += 1
                else: st.error(f"❌ 不正解。正解は「{q['options'][q['answer']]}」")

        if len(q_list) > 0 and st.button("🏁 完了記録", use_container_width=True):
            rate = (score / len(q_list)) * 100
            rank = "high" if rate == 100 else "mid" if rate >= 50 else "low"
            st.success(res["boost_comments"][rank]["text"])
            inject_speech_script(res["boost_comments"][rank]["script"], speed)
            jst_now = (datetime.datetime.utcnow() + datetime.timedelta(hours=9)).strftime("%m/%d %H:%M")
            if res.get("used_subject") not in st.session_state.history: st.session_state.history[res.get("used_subject")] = []
            st.session_state.history[res.get("used_subject")].append({"date": jst_now, "score": f"{rate:.0f}%"})

with tab2:
    for sub, logs in st.session_state.history.items():
        with st.expander(f"📙 {sub}"): st.table(logs)
