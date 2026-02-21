import streamlit as st
import google.generativeai as genai
from PIL import Image
import io, json, time, re, datetime

# --- 基本設定 & 画面構成 ---
st.set_page_config(page_title="教科書ブースター V10.7", layout="centered", page_icon="🚀")

if "history" not in st.session_state: st.session_state.history = {}
if "final_json" not in st.session_state: st.session_state.final_json = None
if "agreed" not in st.session_state: st.session_state.agreed = False
if "font_size" not in st.session_state: st.session_state.font_size = 18

# --- 教科別・解析詳細プロンプト（添付ファイルの仕様を継承） ---
SUBJECT_PROMPTS = {
    "英語": "本文の全文和訳を必ず含め、重要な文法事項を3つ抽出せよ。英単語の読み（発音）も audio_script に反映せよ。",
    "数学": "解法のステップを論理的に分解し、計算過程を省略せずに解説せよ。数式は audio_script で『～の二乗』等に完全変換せよ。",
    "国語": "文章の要約、重要な語彙の意味、筆者の主張を整理せよ。難読漢字の読みを audio_script に含めよ。",
    "理科": "図説や実験結果の考察を重視せよ。現象の原理を科学的根拠（[P.〇/〇行目]）に基づいて説明せよ。",
    "社会": "歴史的背景、地理的特徴、統計資料（表やグラフ）の意味を解説せよ。専門用語の定義を明確にせよ。"
}

# --- 音声合成エンジン ---
def inject_speech_script(text, speed):
    clean_text = text.replace('"', "'").replace("\n", " ")
    js_code = f"""
    <script>
        (function() {{
            window.parent.speechSynthesis.cancel();
            const uttr = new SpeechSynthesisUtterance("{clean_text}");
            uttr.rate = {speed};
            const voices = window.parent.speechSynthesis.getVoices();
            let voice = voices.find(v => v.lang === "ja-JP" && (v.name.includes("Google") || v.name.includes("Natural")));
            if (!voice) voice = voices.find(v => v.lang.startsWith("ja"));
            uttr.voice = voice;
            uttr.lang = "ja-JP";
            window.parent.speechSynthesis.speak(uttr);
        }})();
    </script>
    """
    st.components.v1.html(js_code, height=0, width=0)

# --- スタイル設定 ---
st.markdown(f"<style>.content-body {{ font-size: {st.session_state.font_size}px; line-height: 1.8; }}</style>", unsafe_allow_html=True)

# ==========================================
# 1. 同意 ＆ 設定
# ==========================================
if not st.session_state.agreed:
    st.title("🚀 教科書ブースター V10.7")
    with st.container(border=True):
        st.markdown("""### 【重要】本ソフトウェア利用に関する同意事項
**第1条（著作権の遵守）** <br>利用者は、本アプリで取り扱う教科書等の著作物が著作権法により保護されていることを認識し、解析結果等を権利者の許可なく第三者に公開（SNS、ブログ等への掲載）してはならないものとします。
**第2条（AI生成物の正確性と免責）** <br>アプリが提供する解説および回答は、人工知能による推論に基づくものであり、その正確性、完全性、妥当性を保証するものではありません。生成された内容に起因する学習上の不利益や損害について、開発者は一切の責任を負いません。""")
**第3条（利用目的）** <br>本アプリは利用者の私的な学習補助を目的として提供されるものです。試験等の最終的な確認は、必ず公式な教材および指導者の指示に従ってください。        
        if st.checkbox("法的事項に同意してブーストを開始する"):
            api_key = st.text_input("Gemini API Key", type="password")
            c1, c2 = st.columns(2)
            with c1:
                st.session_state.school_type = st.selectbox("学校", ["小学生", "中学生", "高校生"])
                st.session_state.grade = st.selectbox("学年", [f"{i}年" for i in range(1, 7)])
            with c2:
                st.session_state.age_val = st.slider("解説年齢", 7, 20, 15)
                st.session_state.quiz_count = st.selectbox("問題数", [3, 5, 10])
            
            if st.button("🚀 ブースト開始"):
                if api_key: st.session_state.update({"user_api_key": api_key, "agreed": True}); st.rerun()
                else: st.error("APIキーを入力してください")
    st.stop()

# ==========================================
# 2. メイン機能
# ==========================================
tab1, tab2 = st.tabs(["📖 学習", "📈 履歴"])

with tab1:
    sub = st.selectbox("🎯 教科", list(SUBJECT_PROMPTS.keys()))
    cam_file = st.camera_input("スキャン")

    if cam_file and st.button("✨ 解析"):
        genai.configure(api_key=st.session_state.user_api_key)
        model = genai.GenerativeModel('gemini-3-flash-preview')
        
        with st.status("教科別プロンプトを適用して解析中...🚀"):
            # 【重要】教科別の個別指示(SUBJECT_PROMPTS[sub])を埋め込み
            prompt = f"""あなたは{st.session_state.school_type}{st.session_state.grade}の天才教師です。
            【個別ミッション: {sub}】
            {SUBJECT_PROMPTS[sub]}
            
            【共通ルール】
            1. 教科が「{sub}」でなければ即座にis_match:falseで終了せよ。
            2. 根拠を必ず [P.〇 / 〇行目] で明示せよ。
            3. audio_scriptは記号や数式を自然な日本語（ひらがな）に変換せよ。
            4. 正答率別のブーストメッセージ(high, mid, low)を音声台本付きで作れ。
            
            ###JSON###
            {{
                "is_match": true, "detected_subject": "教科名", "page": "数字",
                "explanation": "解説全文", "audio_script": "読み上げ台本",
                "boost_comments": {{"high":{{"text":"..","script":".."}},"mid":{{"text":"..","script":".."}},"low":{{"text":"..","script":".."}}}},
                "quizzes": [{{"question":"..","options":["A","B","C","D"],"answer":0,"location":"P.〇/〇行"}}]
            }}"""
            
            res_raw = model.generate_content([prompt, Image.open(cam_file)])
            res_json = json.loads(re.search(r"\{.*\}", res_raw.text, re.DOTALL).group())
            
            if not res_json.get("is_match"): st.error(f"教科不一致:判定{res_json['detected_subject']}"); st.stop()
            st.session_state.final_json = res_json
            st.rerun()

    if st.session_state.final_json:
        res = st.session_state.final_json
        st.session_state.font_size = st.slider("🔍 視認性ブースト", 14, 45, st.session_state.font_size)
        
        st.markdown(f'<div class="content-body">{res["explanation"]}</div>', unsafe_allow_html=True)
        if st.button("🔊 音声解説"): inject_speech_script(res["audio_script"], 1.0)

        st.divider()
        st.subheader("📝 クイズ")
        page_num = st.text_input("📖 ページ", value=res.get("page", ""))
        score = 0
        for i, q in enumerate(res["quizzes"]):
            ans = st.radio(f"問{i+1} ({q['location']})", q['options'], key=f"q_{i}")
            if q['options'].index(ans) == q['answer']: score += 1
        
        if st.button("🏁 判定"):
            rate = (score / len(res["quizzes"])) * 100
            rank = "high" if rate == 100 else "mid" if rate >= 50 else "low"
            st.success(res["boost_comments"][rank]["text"])
            inject_speech_script(res["boost_comments"][rank]["script"], 1.1)
            
            # 履歴保存
            if sub not in st.session_state.history: st.session_state.history[sub] = []
            st.session_state.history[sub].append({"date": datetime.datetime.now().strftime("%m/%d %H:%M"), "page": page_num, "score": f"{rate:.0f}%"})
