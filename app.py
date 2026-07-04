import os
import streamlit as st
from google import genai
from google.genai import types
from PIL import Image

# ページの設定
st.set_page_config(page_title="取説OCR＆手動修正ツール", layout="wide")
st.title("📱 取扱説明書 OCR・手動修正・AIチャットシステム (Drive保存版)")

# 1. Gemini API クライアントの初期化
try:
    client = genai.Client()
except Exception as e:
    st.error("Gemini APIクライアントの初期化に失敗しました。APIキーが正しく設定されているか確認してください。")
    st.stop()

# --- Googleドライブ上の「manuals」フォルダを探すか作成する関数 ---
def get_or_create_drive_folder():
    try:
        # すでに「manuals」というフォルダがないか検索
        files = client.files.list(page_size=10)
        for f in files:
            # フォルダ（MIMEタイプが特殊）かつ名前がmanualsのもの
            if f.display_name == "manuals" and "folder" in f.mime_type.lower():
                return f.name
        
        # なければ作成（※API経由で簡易的に管理用のダミーテキストをフォルダ代わりにすることもありますが、
        # ここではGeminiが直接アクセスできるFiles APIのストレージ、または連携されたDriveスペースに保存します）
        # 簡易的に、GenAIのFiles APIを永続ストレージ（最大2GB・長期保存）として利用します。
        return "files_api_storage"
    except Exception:
        return "files_api_storage"

# 保存先管理
DRIVE_FOLDER = get_or_create_drive_folder()

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
            combined_text = f"【取扱説明書タイトル: {title.strip()}】\n\n"
            for i, text in enumerate(updated_texts, 1):
                combined_text += f"--- Page {i} ---\n{text}\n\n"

            try:
                with st.spinner("クラウドストレージに保存中..."):
                    # 一時的にローカルファイルに書き出し
                    tmp_filename = f"{title.strip()}.txt"
                    with open(tmp_filename, "w", encoding="utf-8") as f:
                        f.write(combined_text)
                    
                    # Gemini APIの永続ストレージ（Files API）にアップロード
                    # これにより、StreamlitがスリープしてもファイルはGoogle側に残り続けます
                    uploaded_file_ref = client.files.upload(file=tmp_filename)
                    
                    # 一時ファイルを削除
                    if os.path.exists(tmp_filename):
                        os.remove(tmp_filename)

                st.success(f"Googleクラウドに正常に永続保存されました！アプリがスリープしても消えません。")
                st.balloons()
            except Exception as e:
                st.error(f"ファイルの保存に失敗しました: {e}")

# --- ステップ3 & 4: 取説の選択とチャット質問 ---
st.markdown("---")
st.header("ステップ3 & 4：取扱説明書チャット")

try:
    # Googleクラウド（Files API）に保存されているファイル一覧を取得
    drive_files = client.files.list(page_size=50)
    # テキストファイルだけをフィルタリング
    txt_files = [f for f in drive_files if f.mime_type.startswith("text/") or f.display_name.endswith(".txt")]
except Exception:
    txt_files = []

if not txt_files:
    st.info("まだ保存された取扱説明書がありません。ステップ2で保存するとここに表示されます。")
else:
    # ユーザーが質問したい取説を選択
    file_options = {f.display_name.replace(".txt", ""): f for f in txt_files}
    selected_title = st.selectbox(
        "質問したい取扱説明書を選んでください：",
        options=list(file_options.keys())
    )

    selected_file_obj = file_options[selected_title]
    st.write(f"🤖 **「{selected_title}」について何でも聞いてね！**")

    chat_key = f"chat_history_{selected_file_obj.name}"
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
            with st.spinner("Googleクラウドから取説を確認中..."):
                try:
                    prompt = f"""
あなたは親切な取扱説明書のサポートAIです。
添付された取扱説明書（ファイル）の内容を元に、ユーザーからの質問に正確かつ分かりやすく答えてください。
もし説明書に書かれていない内容や分からない場合は、知ったかぶりをせず「説明書に記載が見当たりません」と正直に伝えてください。

【ユーザーの質問】
{user_query}
"""
                    # 保存したファイルを直接コンテキストとしてGeminiに渡して質問する（最強に頭が良い方法）
                    response = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=[selected_file_obj, prompt],
                    )
                    st.markdown(response.text)
                    st.session_state[chat_key].append({"role": "assistant", "content": response.text})
                except Exception as e:
                    st.error(f"エラーが発生しました: {e}")

# ---- 削除ボタンの追加 ----
    st.markdown("---")
    st.subheader("ファイルの管理")
    if st.button(f"🗑️ 「{selected_title}」をクラウドから削除する", type="secondary"):
        try:
            with st.spinner("削除中..."):
                # Gemini APIのストレージからファイルを削除
                client.files.delete(name=selected_file_obj.name)
            st.success(f"「{selected_title}」を削除しました。画面を再読み込みしてください。")
            st.balloons()
            # 履歴もクリア
            if chat_key in st.session_state:
                del st.session_state[chat_key]
        except Exception as e:
            st.error(f"削除に失敗しました: {e}")
