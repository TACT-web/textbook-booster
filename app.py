import streamlit as st
import google.generativeai as genai
from PIL import Image
import io, json, time, re, datetime

# --- 基本設定 ---
st.set_page_config(page_title="教科書ブースター V1.2", layout="centered", page_icon="🚀")

if "history" not in st.session_state: st.session_state.history = {}
if "final_json" not in st.session_state: st.session_state.final_json = None
if "agreed" not in st.session_state: st.session_state.agreed = False
if "font_size" not in st.session_state: st.session_state.font_size = 18
if "show_voice_btns" not in st.session_state: st.session_state.show_voice_btns = False

# CSSによるスタイル制御（タイトル1行化とフォントサイズ連動）
st.markdown(f"""
    <style>
    .content-body {{ font-size: {st.session_state.font_size}px !important; line-height: 1.6; }}
    .stTitle {{ font-size: 1.7rem !important; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    </style>
""", unsafe_allow_html=True)

# --- 添付ファイル仕様継承：教科別個別プロンプト（一言一句変更なし） ---
SUBJECT_PROMPTS = {
    [cite_start]"英語": "英文を意味の塊（/）で区切るスラッシュリーディング形式（英文 / 訳）を徹底してください。重要な文法構造や熟語についても触れてください。", [cite: 1]
    [cite_start]"数学": "公式の根拠を重視し、計算過程を一行ずつ省略せず論理的に解説してください。単なる手順ではなく『なぜこの解法を選ぶのか』という思考の起点を言語化してください。", [cite: 1]
    [cite_start]"国語": "論理構造（序破急など）を分解し、筆者の主張を明確にしてください。なぜその結論に至ったか、本文の接続詞などを根拠に論理的に説明してください。", [cite: 1]
    [cite_start]"理科": "現象のメカニズムを原理・法則から説明してください。図表がある場合は、軸の意味や数値の変化が示す本質を読み解き、日常の具体例を添えてください。", [cite: 1]
    [cite_start]"社会": "歴史的背景と現代の繋がりをストーリー化してください。単なる事実の羅列ではなく『なぜこの出来事が起きたのか』という因果関係を重視して解説してください。", [cite: 1]
    [cite_start]"その他": "画像内容を客観的に観察し、中立的かつ平易な言葉で要点を3つのポイントに整理して解説してください。" [cite: 1]
}

# --- 音声合成エンジン ---
def inject_speech_script(text_list=None, speed=1.0, stop=False, is_english=False):
    if stop:
        [cite_start]js_code = "<script>window.parent.speechSynthesis.cancel();</script>" [cite: 2]
    else:
        [cite_start]if isinstance(text_list, str): text_list = [text_list] [cite: 2]
        [cite_start]json_texts = json.dumps(text_list, ensure_ascii=False) [cite: 2]
        [cite_start]lang = "en-US" if is_english else "ja-JP" [cite: 2]
        js_code = f"""
        <script>
            (function() {{
                const synth = window.parent.speechSynthesis;
                synth.cancel();
                const texts = {json_texts};
                texts.forEach((txt) => {{
                    const uttr = new SpeechSynthesisUtterance(txt.replace(/\\\\n/g, ' '));
                    uttr.rate = {speed};
                    uttr.lang = "{lang}";
                    const voices = synth.getVoices();
                    let voice = voices.find(v => v.lang === "{lang}" && (v.name.includes("Google") || v.name.includes("Natural")));
                    if (!voice) voice = voices.find(v => v.lang.startsWith("{lang.split('-')[0]}"));
                    uttr.voice = voice;
                    synth.speak(uttr);
                }});
            }})();
        </script>
        [cite_start]""" [cite: 3, 4, 5, 6, 7]
    st.components.v1.html(js_code, height=0, width=0)

# ==========================================
# 1. 冒頭：厳格な免責事項 ＆ 同意（第1条〜第3条 厳守）
# ==========================================
if not st.session_state.agreed:
    st.title("🚀 教科書ブースター V1.2")
    with st.container(border=True):
        st.markdown("""
        ### 【本ソフトウェア利用に関する同意事項】
        
        **第1条（著作権の遵守）**
        [cite_start]利用者は、本アプリで取り扱う教科書等の著作物が著作権法により保護されていることを認識し、解析結果等を権利者の許可なく第三者に公開（SNS、ブログ等への掲載）してはならないものとします。 [cite: 7]
        
        **第2条（AI生成物の正確性と免責）**
        [cite_start]本アプリが提供する解説および回答は、人工知能による推論に基づくものであり、その正確性、完全性、妥当性を保証するものではありません。生成された内容に起因する学習上の不利益や損害について、開発者は一切の責任を負いません。 [cite: 7]
        
        **第3条（利用目的）**
        [cite_start]本アプリは利用者の私的な学習補助を目的として提供されるものです。試験等の最終的な確認は、必ず公式な教材および指導者の指示に従ってください。 [cite: 8]
        """)
        agree_check = st.checkbox("上記の内容を理解し、すべての条項に同意します。")

    if agree_check:
        st.subheader("🛠️ 学習ブースト設定")
        api_key = st.text_input("Gemini API Key", type="password")
        c1, c2 = st.columns(2)
        with c1:
            [cite_start]st.session_state.school_type = st.selectbox("学校区分", ["小学生", "中学生", "高校生"]) [cite: 9]
            [cite_start]st.session_state.grade = st.selectbox("学年", [f"{i}年生" for i in range(1, 7)]) [cite: 9]
        with c2:
            [cite_start]st.session_state.age_val = st.slider("解説ターゲット年齢", 7, 20, 15) [cite: 9]
            [cite_start]st.session_state.quiz_count = st.selectbox("問題数", [10, 15, 20, 25]) [cite: 9]

        if st.button("🚀 ブーストを開始する", use_container_width=True):
            if api_key:
                [cite_start]st.session_state.user_api_key = api_key [cite: 10]
                st.session_state.agreed = True
                st.rerun()
            else: st.error("APIキーを入力してください。")
    st.stop()

# ==========================================
# 2. 学習メイン機能
# ==========================================
tab1, tab2 = st.tabs(["📖 学習ブースト", "📈 ブースト履歴"])

with tab1:
    t_col1, t_col2 = st.columns([3, 1])
    with t_col1:
        st.title("🚀 教科書ブースター")
    with t_col2:
        [cite_start]subject_choice = st.selectbox("🎯 ターゲット教科", list(SUBJECT_PROMPTS.keys()), label_visibility="collapsed") [cite: 10]
    
    final_subject_name = subject_choice
    if subject_choice == "その他":
        [cite_start]custom_subject = st.text_input("具体的な教科名を入力してください") [cite: 11]
        if custom_subject: final_subject_name = custom_subject

    # エラー回避のため、capture引数を削除した標準形式に変更
    cam_file = st.file_uploader("📸 教科書をスキャン", type=['png', 'jpg', 'jpeg'])

    if cam_file and st.button("✨ ブースト開始", use_container_width=True):
        genai.configure(api_key=st.session_state.user_api_key)
        [cite_start]model = genai.GenerativeModel('gemini-3-flash-preview') [cite: 11]
        
        with st.status("解析中...🚀"):
            prompt = f"""あなたは{{st.session_state.school_type}}{{st.session_state.grade}}担当の天才教育者です。
            
            【教科別個別ミッション: {{final_subject_name}}】
            {{SUBJECT_PROMPTS[subject_choice]}}
            [cite_start]※英語の場合は、スラッシュごとの逐語訳（直訳）を徹底し、返り読みをしない順序で[ 英文 / 訳 ]の形式を厳守せよ。 [cite: 12]

            【共通厳守ルール】
            1. [cite_start]画像内の教科が「{{final_subject_name}}」に関連しない場合は is_match: false として即終了せよ。 [cite: 12]
            2. [cite_start]根拠箇所を必ず [P.〇 / 〇行目] の形式で本文末尾に太字で付加せよ。 [cite: 12]
            3. [cite_start]audio_scriptは記号や数式を自然な日本語の読み（ひらがな）に変換せよ。 [cite: 12]
            4. [cite_start]正答率別のブーストメッセージ(high, mid, low)を音声台本付きで作れ。 [cite: 13]
            5. [cite_start]解説は{{st.session_state.age_val}}歳に最適な言葉を選べ。 [cite: 13]
            6. [cite_start]出力は100文字前後のブロックに分け、英語なら「英文\\\\n解説」の構成にせよ。 [cite: 13]
            7. [cite_start]年齢別ルビ: 常用漢字には振らず、難読語にのみ「漢字(かんじ)」でルビを振れ。1ブロックにつきルビは最大2箇所。 [cite: 13]
            8. [cite_start]問題数指定: 練習問題(quizzes)は必ず「{{st.session_state.quiz_count}}問」生成すること。 [cite: 13]

            ###JSON形式で出力せよ###
            {{
                "is_match": true,
                "detected_subject": "{{final_subject_name}}",
                "page": "数字",
                "explanation_blocks": [
                    {{"text": "本文・英文\\\\n解説", "audio_target": "再生用テキスト(英語なら英文のみ)"}}
                ],
                "audio_script": "解説全文の台本",
                "boost_comments": {{"high":{{"text":"..","script":".."}},"mid":{{"text":"..","script":".."}},"low":{{"text":"..","script":".."}}}},
                "quizzes": [{{ "question":"..", "options":["A","B","C","D"], "answer":0, "location":"P.〇" }}]
            [cite_start]}}""" [cite: 14, 15]
            
            img = Image.open(cam_file)
            [cite_start]res_raw = model.generate_content([prompt, img]) [cite: 15]
            [cite_start]json_str = re.search(r"\{.*\}", res_raw.text, re.DOTALL).group() [cite: 15]
            [cite_start]res_json = json.loads(json_str) [cite: 15]
            
            if not res_json.get("is_match"):
                [cite_start]st.error(f"🚫 教科不一致: {{res_json['detected_subject']}}") [cite: 16]
                [cite_start]st.stop() [cite: 17]
            
            res_json["used_subject"] = final_subject_name
            st.session_state.final_json = res_json
            [cite_start]st.session_state.show_voice_btns = (final_subject_name == "英語") [cite: 17]
            st.rerun()

    if st.session_state.final_json:
        res = st.session_state.final_json
        target_sub = res.get("used_subject", "不明")
        [cite_start]is_eng = (target_sub == "英語") [cite: 18]
        
        with st.container(border=True):
            [cite_start]speech_speed = st.slider("🐌 音声速度調整", 0.5, 2.0, 1.0, 0.1) [cite: 18]
            col_a, col_b, col_c, col_d = st.columns(4)
            with col_a:
                if st.button("🔊 音声再生", use_container_width=True):
                    [cite_start]inject_speech_script(res["audio_script"], speech_speed) [cite: 19]
            with col_b:
                if st.button("🛑 音声停止", use_container_width=True):
                    [cite_start]inject_speech_script(stop=True) [cite: 19]
            with col_c:
                [cite_start]btn_label = "🎙️ 個別音声:ON" if st.session_state.show_voice_btns else "🎙️ 個別音声:OFF" [cite: 20]
                if st.button(btn_label, use_container_width=True):
                    [cite_start]st.session_state.show_voice_btns = not st.session_state.show_voice_btns [cite: 20]
            with col_d:
                if is_eng and st.button("⏩ 英文を連続再生", use_container_width=True):
                    [cite_start]eng_texts = [b["audio_target"] for b in res["explanation_blocks"]] [cite: 21]
                    [cite_start]inject_speech_script(eng_texts, speech_speed, is_english=True) [cite: 21]

            [cite_start]st.session_state.font_size = st.slider("🔍 文字サイズ調整", 14, 45, st.session_state.font_size) [cite: 21]
            st.divider()
            
            for i, block in enumerate(res.get("explanation_blocks", [])):
                [cite_start]with st.container(border=True): [cite: 22]
                    [cite_start]st.markdown(f'<div class="content-body">{{block["text"].replace("\\\\n", "<br>")}}</div>', unsafe_allow_html=True) [cite: 22]
                    if st.session_state.show_voice_btns:
                        v_col1, v_col2, _ = st.columns([1, 1, 2])
                        [cite_start]with v_col1: [cite: 23]
                            if st.button(f"▶ 再生", key=f"play_{{i}}"):
                                [cite_start]inject_speech_script(block["audio_target"], speech_speed, is_english=is_eng) [cite: 23]
                        [cite_start]with v_col2: [cite: 24]
                            if st.button(f"🔄 リフレッシュ", key=f"refresh_{{i}}"):
                                [cite_start]inject_speech_script(stop=True) [cite: 24]
                                [cite_start]st.rerun() [cite: 25]

        st.subheader(f"📝 ブースト・チェック")
        [cite_start]user_page = st.text_input("📖 ページ番号確認", value=res.get("page", "")) [cite: 25]
        quizzes = res.get("quizzes", [])
        score = 0
        answered_count = 0

        for i, q in enumerate(quizzes):
            [cite_start]q_id = f"q_fixed_{{i}}_{{final_subject_name}}" [cite: 26]
            [cite_start]ans = st.radio(f"問{{i+1}}: {{q.get('question')}} ({{q.get('location')}})", q.get('options'), key=q_id, index=None) [cite: 26]
            
            if ans:
                answered_count += 1
                correct_idx = q.get('answer')
                [cite_start]correct_val = q.get('options')[correct_idx] [cite: 27]
                if ans == correct_val:
                    [cite_start]st.success(f"⭕ 正解！") [cite: 27]
                    score += 1
                else:
                    [cite_start]st.error(f"❌ 残念。正解は「{{correct_val}}」です。") [cite: 28]

        if answered_count == len(quizzes) and len(quizzes) > 0:
            if st.button("🏁 最終結果を記録する", use_container_width=True, type="primary"):
                rate = (score / len(quizzes)) * 100
                rank = "high" if rate == 100 else "mid" if rate >= 50 else "low"
                [cite_start]fb = res["boost_comments"][rank] [cite: 29]
                [cite_start]st.metric("今回の達成率", f"{{rate:.0f}}%") [cite: 29]
                [cite_start]st.success(fb["text"]) [cite: 29]
                [cite_start]inject_speech_script(fb["script"], speech_speed) [cite: 29]
                
                [cite_start]jst_now = datetime.datetime.utcnow() + datetime.timedelta(hours=9) [cite: 30]
                [cite_start]if target_sub not in st.session_state.history: st.session_state.history[target_sub] = [] [cite: 30]
                st.session_state.history[target_sub].append({
                    "date": jst_now.strftime("%m/%d %H:%M"),
                    "page": user_page,
                    [cite_start]"score": f"{{rate:.0f}}%" [cite: 31]
                })

with tab2:
    st.header("📈 ブースト履歴 (JST)")
    for sub, logs in st.session_state.history.items():
        [cite_start]with st.expander(f"📙 {{sub}} の記録"): st.table(logs) [cite: 32]
    if st.button("🗑️ 履歴をリセット"):
        st.session_state.history = {}
        [cite_start]st.rerun() [cite: 32]

# GitHub ログイン用リンク: https://github.com/login
