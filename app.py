import os
import streamlit as st
from google import genai
from PIL import Image
import uuid

# ページの設定
st.set_page_config(page_title="取説OCR＆手動修正ツール", layout="wide")
st.title("📱 取扱説明書 OCR・手動修正・AIチャットシステム")

# 1. Gemini API クライアントの初期化
try:
    client = genai.Client()
except Exception as e:
    st.error("Gemini APIクライアントの初期化に失敗しました。APIキーが正しく設定されているか確認してください。")
    st.stop()

# ローカルの一時保存フォルダ（即時反映用）
SAVE_DIR = "manuals"
if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)

# セッション状態（State）の初期化
if "ocr_results" not in st.session_state:
    st.session_state.ocr_results = {}


# --- ステップ1: 写真アップロードとOCR ---
st.header("ステップ1：写真アップロードとOCR")

uploaded_files = st.file_uploader(
    "取扱説明書の画像をアップロードしてください（複数同時選択可）",
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
        st.success("すべての画像の文字読み込みが完了しました！")


# --- ステップ2: 手動修正と保存 ---
if st.session_state.ocr_results:
    st.markdown("---")
    st.header("ステップ2：手動修正と保存")

    title = st.text_input("取説のタイトル（例：電子レンジ）", placeholder="ここにタイトルを入力")

    st.subheader("読み取り結果の確認・修正")
    updated_texts = []
    for filename, text in st.session_state.ocr_results.items():
        st.write(f"📄 **元ファイル: {filename}**")
        edited_text = st.text_area(
            label=f"編集ボックス ({filename})",
            value=text,
            height=250,
            key=f"text_area_{filename}",
            label_visibility="collapsed",
        )
        updated_texts.append(edited_text)
        st.write("")

    if st.button("修正内容をGoogleクラウドに安全に保存する", type="primary"):
        if not title.strip():
            st.error("保存するには「取説のタイトル」を入力してください。")
        else:
            # 1行目に日本語タイトルを隠し持たせる
            combined_text = f"TITLE:{title.strip()}\n"
            combined_text += f"【取扱説明書タイトル: {title.strip()}】\n\n"
            for i, text in enumerate(updated_texts, 1):
                combined_text += f"--- Page {i} ---\n{text}\n\n"

            try:
                with st.spinner("クラウドストレージに保存中..."):
                    # エラー回避のためファイル名は英語(ランダムID)にする
                    unique_id = str(uuid.uuid4())[:8]
                    filename = f"manual_{unique_id}.txt"
                    local_path = os.path.join(SAVE_DIR, filename)
                    
                    # 1. ローカルに保存
                    with open(local_path, "w", encoding="utf-8") as f:
                        f.write(combined_text)
                    
                    # 2. Gemini APIの永続ストレージにアップロード
                    client.files.upload(file=local_path)

                st.success(f"Googleクラウドに正常に永続保存されました！")
                st.balloons()
                st.rerun()
            except Exception as e:
                st.error(f"ファイルの保存に失敗しました: {e}")


# --- ステップ3 & 4: 取説の選択とチャット質問 ---
st.markdown("---")
st.header("ステップ3 & 4：取扱説明書チャット")

# ファイル名リストを集める
raw_files = []
if os.path.exists(SAVE_DIR):
    raw_files = [f for f in os.listdir(SAVE_DIR) if f.endswith(".txt")]

try:
    # 💥 page_sizeを仕様通りの config=types.ListFilesConfig(limit=50) に修正
    drive_files = client.files.list(config=types.ListFilesConfig(limit=50))
    for f in drive_files:
        if f.display_name.endswith(".txt") and f.display_name not in raw_files:
            raw_files.append(f.display_name)
except Exception:
    pass

# 日本語タイトルを抜き出す
file_options = {}  # { "日本語タイトル": "実際の英数字ファイル名.txt" }

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
    st.info("まだ保存された取扱説明書がありません。ステップ2で保存するとここに表示されます。")
else:
    selected_title = st.selectbox(
        "質問したい取扱説明書を選んでください：",
        options=list(file_options.keys())
    )
    selected_file = file_options[selected_title]

    st.write(f"🤖 **「{selected_title}」について何でも聞いてね！**")

    chat_key = f"chat_history_{selected_file}"
    if chat_key not in st.session_state:
        st.session_state[chat_key] = []

    for message in st.session_state[chat_key]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if user_query := st.chat_input(f"「{selected_title}」への質問を入力..."):
        with st.chat_message("user"):
            st.markdown(user_query)
        st.session_state[chat_key].append({"role": "user", "content": user_query})

        with st.chat_message("assistant"):
            with st.spinner("取説を確認中..."):
                try:
                    local_path = os.path.join(SAVE_DIR, selected_file)
                    manual_text = ""
                    target_file_obj = None
                    
                    if os.path.exists(local_path):
                        with open(local_path, "r", encoding="utf-8") as f:
                            manual_text = f.read()
                    else:
                        # 💥 一覧取得のバグ修正
                        drive_files = client.files.list(config=types.ListFilesConfig(limit=50))
                        for f in drive_files:
                            if f.display_name == selected_file:
                                target_file_obj = f
                                break
                        if target_file_obj:
                            manual_text = "※クラウド上のファイルを参照中"
                
                    prompt = f"""
あなたは親切な取扱説明書のサポートAIです。
提供された以下の取扱説明書の内容を元に、ユーザーからの質問に正確かつ分かりやすく答えてください。
もし説明書に書かれていない内容や分からない場合は、知ったかぶりをせず「説明書に記載が見当たりません」と正直に伝えてください。

【取扱説明書の内容】
{manual_text if target_file_obj is None else ''}

【ユーザーの質問】
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
                
                # 💥 一覧取得のバグ修正
                drive_files = client.files.list(config=types.ListFilesConfig(limit=50))
                for f in drive_files:
                    if f.display_name == selected_file:
                        client.files.delete(name=f.name)
                        break
                        
            st.success(f"「{display_title}」を削除しました。")
            st.rerun()
        except Exception as e:
            st.error(f"削除に失敗しました: {e}")
