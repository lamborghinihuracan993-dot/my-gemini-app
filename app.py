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
    st.error(
        "Gemini APIクライアントの初期化に失敗しました。APIキーが正しく設定されているか確認してください。"
    )
    st.stop()

# 保存先ディレクトリの作成（なければ作成）
SAVE_DIR = "manuals"
if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)

# セッション状態（State）の初期化
if "ocr_results" not in st.session_state:
    st.session_state.ocr_results = {}  # {ファイル名: テキスト}


# --- ステップ1: 写真アップロードとOCR ---
st.header("ステップ1：写真アップロードとOCR")

uploaded_files = st.file_uploader(
    "取扱説明書の画像をアップロードしてください（複数同時選択可）",
    type=["png", "jpg", "jpeg"],
    accept_multiple_files=True,
)

if uploaded_files:
    if st.button("AIで文字を読み取る（OCR実行）"):
        st.session_state.ocr_results = {}  # 結果をリセット

        for uploaded_file in uploaded_files:
            with st.spinner(f"「{uploaded_file.name}」を解析中..."):
                try:
                    image = Image.open(uploaded_file)

                    # Gemini API (gemini-2.5-flash) を呼び出し
                    response = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=[
                            image,
                            "画像に含まれているすべてのテキストを、レイアウトをできるだけ維持して正確に書き起こしてください。余計な解説や挨拶は含めず、テキストのみを出力してください。",
                        ],
                    )

                    # 結果をセッションに保存
                    st.session_state.ocr_results[uploaded_file.name] = (
                        response.text
                    )

                except Exception as e:
                    st.error(f"「{uploaded_file.name}」の解析中にエラーが発生しました: {e}")

        st.success("すべての画像の文字読み込みが完了しました！")


# --- ステップ2: クライアント側での手動修正と保存 ---
if st.session_state.ocr_results:
    st.markdown("---")
    st.header("ステップ2：手動修正と保存")

    # タイトル入力欄
    title = st.text_input(
        "取説のタイトル（例：電子レンジ）", placeholder="ここにタイトルを入力"
    )

    st.subheader("読み取り結果の確認・修正")
    st.caption("AIが誤認識している部分は、以下のボックス内で直接修正できます。")

    # 各ページ（画像）ごとの編集エリアを表示
    updated_texts = []
    for filename, text in st.session_state.ocr_results.items():
        st.write(f"📄 **元ファイル: {filename}**")

        # ユーザーが編集可能なテキストエリア
        edited_text = st.text_area(
            label=f"編集ボックス ({filename})",
            value=text,
            height=250,
            key=f"text_area_{filename}",
            label_visibility="collapsed",
        )
        updated_texts.append(edited_text)
        st.write("")  # レイアウト用のスペース（エラー修正済み）

    # 保存ボタン
    if st.button("修正内容をサーバーに保存する", type="primary"):
        if not title.strip():
            st.error("保存するには「取説のタイトル」を入力してください。")
        else:
            # 全ページのテキストを結合
            combined_text = ""
            for i, text in enumerate(updated_texts, 1):
                combined_text += f"--- Page {i} ---\n{text}\n\n"

            file_path = os.path.join(SAVE_DIR, f"{title.strip()}.txt")
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(combined_text)

                st.success(
                    f"正常に保存されました！\n保存先: `{file_path}`"
                )
                st.balloons()
            except Exception as e:
                st.error(f"ファイルの保存に失敗しました: {e}")


# --- ステップ3 & 4: 取説の選択とチャット質問 ---
st.markdown("---")
st.header("ステップ3 & 4：取扱説明書チャット")

# サーバー内に保存されている.txtファイルの一覧を取得
if os.path.exists(SAVE_DIR):
    txt_files = [f for f in os.listdir(SAVE_DIR) if f.endswith(".txt")]
else:
    txt_files = []

if not txt_files:
    st.info(
        "まだ保存された取扱説明書がありません。ステップ2で保存するとここに表示されます。"
    )
else:
    # ユーザーが質問したい取説を選択するセレクトボックス
    selected_file = st.selectbox(
        "質問したい取扱説明書を選んでください：",
        options=txt_files,
        format_func=lambda x: x.replace(".txt", ""),  # 拡張子を表示しない
    )

    st.write(f"🤖 **「{selected_file.replace('.txt', '')}」について何でも聞いてね！**")

    # チャット履歴の初期化（選択中のファイルごとに独立）
    chat_key = f"chat_history_{selected_file}"
    if chat_key not in st.session_state:
        st.session_state[chat_key] = []

    # 過去のチャット履歴を表示
    for message in st.session_state[chat_key]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # チャット入力欄
    if user_query := st.chat_input(
        f"「{selected_file.replace('.txt', '')}」への質問を入力..."
    ):
        # ユーザーの質問を表示＆履歴に追加
        with st.chat_message("user"):
            st.markdown(user_query)
        st.session_state[chat_key].append({"role": "user", "content": user_query})

        # 選択された.txtファイルの中身を読み込む
        file_path = os.path.join(SAVE_DIR, selected_file)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                manual_text = f.read()

            # AIによる回答生成
            with st.chat_message("assistant"):
                with st.spinner("取扱説明書を確認中..."):
                    prompt = f"""
あなたは親切な取扱説明書のサポートAIです。
提供された以下の取扱説明書の内容を元に、ユーザーからの質問に正確かつ分かりやすく答えてください。
もし説明書に書かれていない内容や分からない場合は、知ったかぶりをせず「説明書に記載が見当たりません」と正直に伝えてください。

【取扱説明書の内容】
{manual_text}

【ユーザーの質問】
{user_query}
"""
                    response = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=prompt,
                    )

                    st.markdown(response.text)

            # AIの回答を履歴に追加
            st.session_state[chat_key].append(
                {"role": "assistant", "content": response.text}
            )

        except Exception as e:
            st.error(f"エラーが発生しました: {e}")