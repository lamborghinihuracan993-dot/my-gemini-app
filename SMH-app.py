import os
import streamlit as st
from google import genai
from google.genai import types
from PIL import Image
import uuid

# ページの設定（スマホで見やすいよう、wideではなく独自にスタイルを当てます）
st.set_page_config(page_title="ファイルOCR＆AIチャット", layout="centered")

# 📱 スマホでの文字化け・巨大化を防ぐカスタムCSSの注入
st.markdown("""
    <style>
    /* タイトルとヘッダーの文字サイズをスマホ向けに自動調整 */
    h1 {
        font-size: 1.8rem !important;
        line-height: 1.3 !important;
        padding-bottom: 10px;
    }
    h2 {
        font-size: 1.4rem !important;
        margin-top: 20px !important;
    }
    h3 {
        font-size: 1.1rem !important;
    }
    /* テキストボックスやボタンの余白をスマホ向けに最適化 */
    .stButton > button {
        width: 100% !important; /* スマホでボタンを押しやすく */
    }
    /* 全体のフォントをスッキリさせる */
    html, body, [class*="css"] {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    </style>
""", unsafe_allow_html=True)

st.title("📱 ファイル OCR＆AIチャット")

# 1. Gemini API クライアントの初期化
try:
    client = genai.Client()
except Exception as e:
    st.error("Gemini APIクライアントの初期化に失敗しました。APIキーが正しく設定されているか確認してください。")
    st.stop()

# ローカルの一時保存フォルダ（即時反映用）
SAVE_DIR = "documents"
if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)

# セッション状態（State）の初期化
if "ocr_results" not in st.session_state:
    st.session_state.ocr_results = {}


# --- ステップ1: 写真アップロードとOCR ---
st.header("ステップ1：画像・写真のアップロード")

uploaded_files = st.file_uploader(
    "テキストが含まれる画像を選んでください（複数可）",
    type=["png", "jpg", "jpeg"],
    accept_multiple_files=True,
)

if uploaded_files:
    if st.button("AIで文字を読み取る（OCR実行）"):
        st.session_state.ocr_results = {}
        for uploaded_file in uploaded_files:
            with st.spinner(f"「{uploaded_file.name}」を解析中..."):
                try:
                    image = Image.open(uploaded_file)
                    response = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=[
                            image,
                            "画像に含まれているすべてのテキストを正確に書き起こしてください。テキストのみを出力してください。",
                        ],
                    )
                    st.session_state.ocr_results[uploaded_file.name] = response.text
                except Exception as e:
                    st.error(f"「{uploaded_file.name}」の解析中にエラーが発生しました: {e}")
        st.success("文字読み込みが完了しました！")


# --- ステップ2: 手動修正と保存 ---
if st.session_state.ocr_results:
    st.markdown("---")
    st.header("ステップ2：内容の確認・修正と保存")

    title = st.text_input("ファイル・書類のタイトル", placeholder="例：〇〇のメール、会議メモ")

    st.subheader("読み取り結果の確認・修正")
    updated_texts = []
    for filename, text in st.session_state.ocr_results.items():
        st.write(f"📄 **元ファイル: {filename}**")
        edited_text = st.text_area(
            label=f"編集ボックス ({filename})",
            value=text,
            height=200,
            key=f"text_area_{filename}",
            label_visibility="collapsed",
        )
        updated_texts.append(edited_text)
        st.write("")

    if st.button("修正内容をクラウドに安全に保存する", type="primary"):
        if not title.strip():
            st.error("保存するには「ファイル・書類のタイトル」を入力してください。")
        else:
            combined_text = f"TITLE:{title.strip()}\n"
            combined_text += f"【ファイルタイトル: {title.strip()}】\n\n"
            for i, text in enumerate(updated_texts, 1):
                combined_text += f"--- Page {i} ---\n{text}\n\n"

            try:
                with st.spinner("クラウドストレージに保存中..."):
                    unique_id = str(uuid.uuid4())[:8]
                    filename = f"doc_{unique_id}.txt"
                    local_path = os.path.join(SAVE_DIR, filename)
                    
                    with open(local_path, "w", encoding="utf-8") as f:
                        f.write(combined_text)
                    
                    client.files.upload(file=local_path)

                st.success(f"クラウドに正常に永続保存されました！")
                st.balloons()
                st.rerun()
            except Exception as e:
                st.error(f"ファイルの保存に失敗しました: {e}")


# --- ステップ3 & 4: ファイルの選択とチャット質問 ---
st.markdown("---")
st.header("ステップ3 & 4：ファイルについて質問")

raw_files = []
if os.path.exists(SAVE_DIR):
    raw_files = [f for f in os.listdir(SAVE_DIR) if f.endswith(".txt")]

try:
    drive_files = client.files.list(config=types.ListFilesConfig(page_size=50))
    for f in drive_files:
        if f.display_name.endswith(".txt") and f.display_name not in raw_files:
            raw_files.append(f.display_name)
except Exception:
    pass

file_options = {}

for f_name in raw_files:
    local_path = os.path.join(SAVE_DIR, f_name)
    try:
        if os.path.exists(local_path):
            with open(local_path, "r", encoding="utf-8") as f:
                first_line = f.readline().strip()
                if first_line.startswith("TITLE:"):
                    display_name = first_line.replace("TITLE:", "")
                    file_options[display_name] = f_name
        else:
            file_options[f_name] = f_name
    except Exception:
        file_options[f_name] = f_name

if not file_options:
    st.info("まだ保存されたファイルがありません。ステップ2で保存するとここに表示されます。")
else:
    selected_title = st.selectbox(
        "質問・参照したいファイルを選択：",
        options=list(file_options.keys())
    )
    selected_file = file_options[selected_title]

    st.write(f"🤖 **「{selected_title}」について質問してね**")

    chat_key = f"chat_history_{selected_file}"
    if chat_key not in st.session_state:
        st.session_state[chat_key] = []

    for message in st.session_state[chat_key]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if user_query := st.chat_input("質問や指示を入力..."):
        with st.chat_message("user"):
            st.markdown(user_query)
        st.session_state[chat_key].append({"role": "user", "content": user_query})

        with st.chat_message("assistant"):
            with st.spinner("ファイルを確認中..."):
                try:
                    local_path = os.path.join(SAVE_DIR, selected_file)
                    manual_text = ""
                    target_file_obj = None
                    
                    if os.path.exists(local_path):
                        with open(local_path, "r", encoding="utf-8") as f:
                            manual_text = f.read()
                    else:
                        drive_files = client.files.list(config=types.ListFilesConfig(page_size=50))
                        for f in drive_files:
                            if f.display_name == selected_file:
                                target_file_obj = f
                                break
                        if target_file_obj:
                            manual_text = "※クラウド上のファイルを参照中"
                
                    prompt = f"""
あなたはユーザーをサポートする親切で優秀なAIアシスタントです。
提供された以下のファイルの内容をベースにして、ユーザーからの質問に正確に答えたり、指示に沿った対応を行ってください。
記載がない一般的な知識についての質問などの場合は、ファイルに記載がない旨を伝えた上で、あなたの持つ知識をもとにサポートしてください。

【対象のファイル内容】
{manual_text if target_file_obj is None else ''}

【ユーザーからの質問・指示】
{user_query}
"""
                    if os.path.exists(local_path):
                        response = client.models.generate_content(
                            model="gemini-2.5-flash",
                            contents=prompt,
                        )
                    else:
                        response = client.models.generate_content(
                            model="gemini-2.5-flash",
                            contents=[target_file_obj, prompt],
                        )
                        
                    st.markdown(response.text)
                    st.session_state[chat_key].append({"role": "assistant", "content": response.text})
                except Exception as e:
                    st.error(f"エラーが発生しました: {e}")

    # ---- 削除ボタン ----
    st.markdown("---")
    st.subheader("ファイルの管理")
    if st.button(f"🗑️ 「{selected_title}」を削除する", type="secondary"):
        try:
            with st.spinner("削除中..."):
                local_path = os.path.join(SAVE_DIR, selected_file)
                if os.path.exists(local_path):
                    os.remove(local_path)
                
                drive_files = client.files.list(config=types.ListFilesConfig(page_size=50))
                for f in drive_files:
                    if f.display_name == selected_file:
                        client.files.delete(name=f.name)
                        break
                        
            st.success(f"「{selected_title}」を削除しました。")
            st.rerun()
        except Exception as e:
            st.error(f"削除に失敗しました: {e}")