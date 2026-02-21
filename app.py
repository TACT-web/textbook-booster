import streamlit as st
import google.generativeai as genai
from PIL import Image
import io, json, time, re, datetime

# --- 基本設定 ---
st.set_page_config(page_title="教科書ブースター V1.1", layout="centered", page_icon="🚀")

if "history" not in st.session_state: st.session_state.history = {}
if "final_json" not in st.session_state: st.session_state.final_json = None
if "agreed" not in st.session_state: st.session_state.agreed = False
if "font_size" not in st.session_state: st.session_state.font_size = 18
if "show_blocks" not in st.session_state: st.session_state.show_blocks = False

# --- 添付ファイル仕様継承：教科別個別プロンプト (一言一句変更なし) ---
SUBJECT_PROMPTS = {
    "英語": "英文を意味の塊（/）で区切るスラッシュリーディング形式（英文 / 訳）を徹底してください。重要な文法構造や熟語についても触れてください。",
    "数学": "公式の根拠を重視し、計算過程を一行ずつ省略せず論理的に解説してください。単なる手順ではなく『なぜこの解法を選ぶのか』という思考の起点を言語化してください。",
    "国語": "論理構造（序破急など）を分解し、筆者の主張を明確にしてください。なぜその結論に至ったか、本文の接続詞などを根拠に論理的に説明してください。",
    "理科": "現象のメカニズムを原理・法則から説明してください。図表がある場合は、軸の意味や数値の変化が示す本質を読み解き、日常の具体例を添えてください。",
    "社会": "歴史的背景と現代の繋がりをストーリー化してください。単なる事実の羅列ではなく『なぜこの出来事が起きたのか』という因果関係を重視して解説してください。",
    "その他": "画像内容を客観的に観察し、中立的かつ平易な言葉で要点を3つのポイントに整理して解説してください。"
}

# --- 音声合成エンジン（速度調整・言語切り替え機能） ---
def inject_speech_script(text=None, speed=1.0, stop=False, is_english=False):
    if stop:
        js_code = "<script>window.parent.speechSynthesis.cancel();</script>"
    else:
        clean_text = text.replace('"', "'").replace("\n", " ")
        lang = "en-US" if is_english else "ja-JP"
        js_code = f"""
        <script>
            (function() {{
                window.parent.speechSynthesis.cancel();
                const uttr = new SpeechSynthesisUtterance("{clean_text}");
                uttr.rate = {speed};
                const voices = window.parent.speechSynthesis.getVoices();
                let voice = voices.find(v => v.lang === "{lang}");
                if (!voice && "{lang}" === "ja-JP") voice = voices.find(v => v.lang.startsWith("ja"));
                uttr.voice = voice;
                uttr.lang = "{lang}";
                window.parent.speechSynthesis.speak(uttr);
            }})();
        </script>
        """
    st.components.v1.html(js_code, height=0, width=0)

# --- スタイル適用 ---
st.markdown(f"<style>.content-body {{ font-size: {st.session_state.font_size}px; line-height: 1.8; }}</style>", unsafe_allow_html=True)

# ==========================================
# 1. 冒頭：厳格な免責事項 ＆ 同意（第1条〜第3条 厳守）
# ==========================================
if not st.session_state.agreed:
    st.title("🚀 教科書ブースター V1.1")
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
        st.subheader("🛠️ 学習ブースト設定")
        api_key = st.text_input("Gemini API Key", type="password")
        c1, c2 = st.columns(2)
        with c1:
            st.session_state.school_type = st.selectbox("学校区分", ["小学生", "中学生", "高校生"])
            st.session_state.grade = st.selectbox("学年", [f"{i}年生" for i in range(1, 7)])
        with c2:
            st.session_state.age_val = st.slider("解説ターゲット年齢", 7, 20, 15)
            st.session_state.quiz_count = st.selectbox("問題数", [3, 5, 10, 15, 20])

        if st.button("🚀 ブーストを開始する", use_container_width=True):
            if api_key:
                st.session_state.user_api_key = api_key
                st.session_state.agreed = True
                st.rerun()
            else: st.error("APIキーを入力してください。")
    st.stop()

# ==========================================
# 2. 学習メイン機能
# ==========================================
tab1, tab2 = st.tabs(["📖 学習ブースト", "📈 ブースト履歴"])

with tab1:
    subject_choice = st.selectbox("🎯 ターゲット教科", list(SUBJECT_PROMPTS.keys()))
    
    final_subject_name = subject_choice
    if subject_choice == "その他":
        custom_subject = st.text_input("具体的な教科名を入力してください")
        if custom_subject: final_subject_name = custom_subject

    cam_file = st.camera_input("教科書をスキャン")

    if cam_file and st.button("✨ ブースト開始"):
        genai.configure(api_key=st.session_state.user_api_key)
        model = genai.GenerativeModel('gemini-3-flash-preview')
        
        with st.status("教科別ロジックを適用中...🚀"):
            prompt = f"""あなたは{st.session_state.school_type}{st.session_state.grade}担当の天才教育者です。
            
            【教科別個別ミッション: {final_subject_name}】
            {SUBJECT_PROMPTS[subject_choice]}

            【共通厳守ルール】
            1. 画像内の教科が「{final_subject_name}」に関連しない場合は is_match: false として即終了せよ。
            2. 根拠箇所を必ず [P.〇 / 〇行目] の形式で本文末尾に太字で付加せよ。
            3. audio_scriptは記号や数式を自然な日本語の読み（ひらがな）に変換せよ。
            4. 正答率別のブーストメッセージ(high, mid, low)を音声台本付きで作れ。
            5. 解説は{st.session_state.age_val}歳に最適な言葉を選べ。
            6. **内容の深さと構造**: 解説の質を落とさず深く解説せよ。出力は100文字前後のブロックに分け、英語なら「英文(改行)解説」の構成にせよ。
            7. **年齢別ルビ(厳格化)**: 相手は{st.session_state.age_val}歳。常用漢字には振らず、難読語にのみ「漢字(かんじ)」でルビを振る。1ブロックにつきルビは最大3箇所に絞れ。
            8. **問題数指定**: 練習問題(quizzes)は必ず「{st.session_state.quiz_count}問」生成すること。

            ###JSON###
            {{
                "is_match": true, "detected_subject": "{final_subject_name}", "page": "数字",
                "explanation": "解説全文", 
                "explanation_blocks": [
                    {{"text": "本文・英文\\n解説", "audio_target": "英文のみ、または本文のみ"}}
                ],
                "audio_script": "解説全文の台本(全文読み上げ用)",
                "boost_comments": {{"high":{{"text":"..","script":".."}},"mid":{{"text":"..","script":".."}},"low":{{"text":"..","script":".."}}}},
                "quizzes": [{{ "question":"..", "options":["A","B","C","D"], "answer":0, "location":"P.〇/〇行目" }}]
            }}"""
            
            img = Image.open(cam_file)
            res_raw = model.generate_content([prompt, img])
            res_json = json.loads(re.search(r"\{.*\}", res_raw.text, re.DOTALL).group())
            
            if not res_json.get("is_match"):
                st.error(f"🚫 教科不一致: 判定結果は「{res_json['detected_subject']}」です。")
                st.stop()
            
            res_json["used_subject"] = final_subject_name
            st.session_state.final_json = res_json
            st.session_state.show_blocks = False
            st.rerun()

    if st.session_state.final_json:
        res = st.session_state.final_json
        target_sub = res.get("used_subject", "不明")
        
        # --- 音声・視認性設定 ---
        with st.sidebar:
            st.header("⚙️ 音声・表示設定")
            speech_speed = st.slider("🐌 音声速度", 0.5, 2.0, 1.0, 0.1)
            st.session_state.font_size = st.slider("🔍 文字サイズ", 14, 45, st.session_state.font_size)

        with st.container(border=True):
            # 音声操作ボタン配置
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                if st.button("🔊 全文再生", use_container_width=True):
                    inject_speech_script(res["audio_script"], speech_speed)
            with col_b:
                if st.button("🛑 停止", use_container_width=True):
                    inject_speech_script(stop=True)
            with col_c:
                if st.button("🎙️ ブロック別音声", use_container_width=True):
                    st.session_state.show_blocks = not st.session_state.show_blocks

            st.divider()
            
            # 全文表示 (V1.1仕様)
            st.markdown(f'<div class="content-body">{res["explanation"]}</div>', unsafe_allow_html=True)
            
            # ブロック表示 (切り替え仕様)
            if st.session_state.show_blocks:
                st.info("💡 各ブロックの音声を個別に再生できます")
                for i, block in enumerate(res.get("explanation_blocks", [])):
                    with st.container(border=True):
                        st.markdown(f'<div class="content-body">{block["text"].replace("\\n", "<br>")}</div>', unsafe_allow_html=True)
                        is_eng = (target_sub == "英語")
                        label = "🔤 英文を再生" if is_eng else "🔊 本文を再生"
                        if st.button(label, key=f"blk_{i}"):
                            inject_speech_script(block["audio_target"], speech_speed, is_english=is_eng)

        # --- クイズセクション ---
        st.subheader(f"📝 ブースト・チェック ({len(res['quizzes'])}問)")
        user_page = st.text_input("📖 ページ番号確認", value=res.get("page", ""))
        score = 0
        for i, q in enumerate(res["quizzes"]):
            ans = st.radio(f"問{i+1}: {q['question']} ({q['location']})", q['options'], key=f"q_{i}")
            if q['options'].index(ans) == q['answer']: score += 1
        
        if st.button("🏁 判定", use_container_width=True):
            rate = (score / len(res["quizzes"])) * 100
            rank = "high" if rate == 100 else "mid" if rate >= 50 else "low"
            fb = res["boost_comments"][rank]
            st.metric("正答率", f"{rate:.0f}%")
            st.success(fb["text"])
            inject_speech_script(fb["script"], speech_speed)
            
            # ログ保存 (自由入力教科名対応)
            if target_sub not in st.session_state.history: st.session_state.history[target_sub] = []
            st.session_state.history[target_sub].append({
                "date": datetime.datetime.now().strftime("%m/%d %H:%M"), 
                "page": user_page, 
                "score": f"{rate:.0f}%"
            })

with tab2:
    st.header("📈 ブースト履歴")
    for sub, logs in st.session_state.history.items():
        with st.expander(f"📙 {sub} の記録"): st.table(logs)
    if st.button("🗑️ 履歴をリセット"): st.session_state.history = {}; st.rerun()
