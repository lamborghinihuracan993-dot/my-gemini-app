import os
import streamlit as st
from google import genai
from PIL import Image

# ページの設定
st.set_page_config(page_title="取説OCR＆手動修正ツール", layout="wide")
st.title("📱 取扱説明書 OCR・手動修正・AIチャットシステム")

# 1. Gemini API クライアントの初期化
try:
    client = genai.Client()
except Exception as e:
    st.error("Gemini APIクライアントの初期化に失敗しました。APIキーが正しく設定されているか確認してください。")
    st.stop()

# ローカルの一時保存フォルダ（念のためのバックアップ・即時反映用）
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
            combined_text = f"【取扱説明書タイトル: {title.strip()}】\n\n"
            for i, text in enumerate(updated_texts, 1):
                combined_text += f"--- Page {i} ---\n{text}\n\n"

            try:
                with st.spinner("クラウドストレージに保存中..."):
                    filename = f"{title.strip()}.txt"
                    local_path = os.path.join(SAVE_DIR, filename)
                    
                    # 1. ローカル（Streamlit側）に保存（これで即時にチャットで選べるようになります）
                    with open(local_path, "w", encoding="utf-8") as f:
                        f.write(combined_text)
                    
                    # 2. Gemini APIの永続ストレージにもバックアップアップロード
                    client.files.upload(file=local_path)

                st.success(f"Googleクラウドに正常に永続保存されました！")
                st.balloons()
                # 画面を強制的に再実行して即時反映させる
                st.rerun()
            except Exception as e:
                st.error(f"ファイルの保存に失敗しました: {e}")


# --- ステップ3 & 4: 取説の選択とチャット質問 ---
st.markdown("---")
st.header("ステップ3 & 4：取扱説明書チャット")

# クラウド上のファイル同期を待ちつつ、ローカルと両方からファイル名を集める（最強のハイブリッド方式）
txt_files = []
if os.path.exists(SAVE_DIR):
    txt_files = [f for f in os.listdir(SAVE_DIR) if f.endswith(".txt")]

try:
    drive_files = client.files.list(page_size=50)
    for f in drive_files:
        if f.display_name.endswith(".txt") and f.display_name not in txt_files:
            txt_files.append(f.display_name)
except Exception:
    pass

if not txt_files:
    st.info("まだ保存された取扱説明書がありません。ステップ2で保存するとここに表示されます。")
else:
    # ユーザーが質問したい取説を選択
    selected_file = st.selectbox(
        "質問したい取扱説明書を選んでください：",
        options=txt_files,
        format_func=lambda x: x.replace(".txt", "")
    )

    display_title = selected_file.replace(".txt", "")
    st.write(f"🤖 **「{display_title}」について何でも聞いてね！**")

    chat_key = f"chat_history_{selected_file}"
    if chat_key not in st.session_state:
        st.session_state[chat_key] = []

    for message in st.session_state[chat_key]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if user_query := st.chat_input(f"「{display_title}」への質問を入力..."):
        with st.chat_message("user"):
            st.markdown(user_query)
        st.session_state[chat_key].append({"role": "user", "content": user_query})

        with st.chat_message("assistant"):
            with st.spinner("取説を確認中..."):
                try:
                    # ローカルにある場合はローカルから読み込み、ない場合はクラウドから探す
                    local_path = os.path.join(SAVE_DIR, selected_file)
                    manual_text = ""
                    
                    if os.path.exists(local_path):
                        with open(local_path, "r", encoding="utf-8") as f:
                            manual_text = f.read()
                    else:
                        # クラウドから該当ファイルを探してテキストを取得
                        drive_files = client.files.list(page_size=50)
                        target_file_obj = None
                        for f in drive_files:
                            if f.display_name == selected_file:
                                target_file_obj = f
                                break
                        
                        if target_file_obj:
                            # クラウドのファイルをそのままGeminiに渡すためにオブジェクトを使用
                            manual_text = f"※クラウド上のファイル「{selected_file}」を参照中"
                
                    prompt = f"""
あなたは親切な取扱説明書のサポートAIです。
提供された以下の取扱説明書の内容を元に、ユーザーからの質問に正確かつ分かりやすく答えてください。
もし説明書に書かれていない内容や分からない場合は、知ったかぶりをせず「説明書に記載が見当たりません」と正直に伝えてください。

【取扱説明書の内容】
{manual_text if '※' not in manual_text else ''}

【ユーザーの質問】
{user_query}
"""
                    # テキストまたはクラウドオブジェクトを使ってコンテンツ生成
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
    if st.button(f"🗑️ 「{display_title}」を削除する", type="secondary"):
        try:
            with st.spinner("削除中..."):
                # ローカルから削除
                local_path = os.path.join(SAVE_DIR, selected_file)
                if os.path.exists(local_path):
                    os.remove(local_path)
                
                # クラウドから削除
                drive_files = client.files.list(page_size=50)
                for f in drive_files:
                    if f.display_name == selected_file:
                        client.files.delete(name=f.name)
                        break
                        
            st.success(f"「{display_title}」を削除しました。")
            st.rerun()
        except Exception as e:
            st.error(f"削除に失敗しました: {e}")
