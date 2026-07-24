from datetime import datetime
import pandas as pd
import pytz
import streamlit as st
from supabase import create_client

# 1. 頁面基本設定
st.set_page_config(
    page_title="白卡借用系統", page_icon="💳", layout="centered"
)

# 2. 初始化 Supabase 連線
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    st.error(f"❌ Supabase 連線設定失敗，請檢查 Secrets：{e}")
    st.stop()

TAIPEI_TZ = pytz.timezone("Asia/Taipei")


# 3. 載入員工名單 (增加讀取與清理邏輯)
@st.cache_data
def load_employees():
    try:
        df = pd.read_excel("employees.xlsx")
        df["工號"] = df["工號"].astype(str).str.strip()
        df["姓名"] = df["姓名"].astype(str).str.strip()
        df = df[
            (df["工號"] != "nan")
            & (df["姓名"] != "nan")
            & (df["工號"] != "")
            & (df["姓名"] != "")
        ]
        emp_list = [
            f"{row['工號']} - {row['姓名']}" for _, row in df.iterrows()
        ]
        return emp_list
    except Exception as e:
        st.warning(
            f"⚠️ 讀取 employees.xlsx 時遇到問題：{e}（系統將允許手動輸入）"
        )
        return []


EMP_LIST = load_employees()


# --- 輔助函式 ---
def get_cards():
    try:
        res = (
            supabase.table("cards")
            .select("*")
            .order("card_id", desc=False)
            .execute()
        )
        return res.data
    except Exception as e:
        st.error(f"❌ 讀取卡片資料庫失敗：{e}")
        return []


def borrow_card(card_id, borrower, note, custom_time):
    sys_now = datetime.now(TAIPEI_TZ).isoformat()
    event_time = (
        custom_time.strftime("%Y-%m-%d %H:%M:%S")
        if custom_time
        else datetime.now(TAIPEI_TZ).strftime("%Y-%m-%d %H:%M:%S")
    )

    supabase.table("cards").update(
        {
            "status": "BORROWED",
            "borrower": borrower,
            "borrowed_at": event_time,
            "note": note,
        }
    ).eq("card_id", card_id).execute()

    supabase.table("borrow_logs").insert(
        {
            "card_id": card_id,
            "borrower": borrower,
            "action": "BORROW",
            "timestamp": event_time,
            "created_at": sys_now,
            "note": note,
        }
    ).execute()


def return_card(card_id, borrower, note, custom_time):
    sys_now = datetime.now(TAIPEI_TZ).isoformat()
    event_time = (
        custom_time.strftime("%Y-%m-%d %H:%M:%S")
        if custom_time
        else datetime.now(TAIPEI_TZ).strftime("%Y-%m-%d %H:%M:%S")
    )

    supabase.table("cards").update(
        {
            "status": "AVAILABLE",
            "borrower": None,
            "borrowed_at": None,
            "note": None,
        }
    ).eq("card_id", card_id).execute()

    supabase.table("borrow_logs").insert(
        {
            "card_id": card_id,
            "borrower": borrower,
            "action": "RETURN",
            "timestamp": event_time,
            "created_at": sys_now,
            "note": note,
        }
    ).execute()


# --- 主介面 ---
st.title("💳 白卡借用系統")

tab1, tab2 = st.tabs(["📌 卡片借還", "📜 歷史紀錄"])

with tab1:
    cards = get_cards()
    if not cards:
        st.info("💡 目前資料庫中沒有卡片資料，請確認 Supabase 的 cards 資料表。")

    for card in cards:
        card_id = card["card_id"]
        status = card["status"]
        borrower = card["borrower"]
        borrowed_at = card["borrowed_at"]
        note = card.get("note")

        if status == "AVAILABLE":
            with st.container(border=True):
                st.subheader(f"🟢 {card_id}（可借用）")
                with st.form(key=f"borrow_form_{card_id}"):
                    if EMP_LIST:
                        borrower_selected = st.selectbox(
                            "選擇工號與姓名",
                            options=["-- 請選擇工號與姓名 --"] + EMP_LIST,
                            key=f"select_{card_id}",
                        )
                    else:
                        borrower_selected = st.text_input(
                            "請輸入工號與姓名", key=f"input_{card_id}"
                        )

                    note_input = st.text_input(
                        "📝 備註 (如：訪客姓名 / 補登說明)",
                        key=f"note_{card_id}",
                    )

                    col1, col2 = st.columns([1, 1])
                    with col1:
                        use_custom = st.checkbox(
                            "⏰ 自訂實際借用時間", key=f"chk_{card_id}"
                        )
                    with col2:
                        custom_dt = None
                        if use_custom:
                            custom_dt = st.datetime_input(
                                "選擇時間", key=f"dt_{card_id}"
                            )

                    submit = st.form_submit_button("確認借用")
                    if submit:
                        if (
                            borrower_selected == "-- 請選擇工號與姓名 --"
                            or not borrower_selected
                        ):
                            st.warning("⚠️ 請選擇或輸入借用人！")
                        else:
                            borrow_card(
                                card_id,
                                borrower_selected,
                                note_input,
                                custom_dt,
                            )
                            st.success(f"✅ {card_id} 借用成功！")
                            st.rerun()
        else:
            with st.container(border=True):
                st.subheader(f"🔴 {card_id}（借出中）")
                st.write(
                    f"👤 **借用人**：{borrower} "
                    + (f"（備註：{note}）" if note else "")
                )
                st.write(f"🕒 **借用時間**：{borrowed_at}")

                with st.form(key=f"return_form_{card_id}"):
                    return_note = st.text_input(
                        "📝 歸還備註 (選填)", key=f"r_note_{card_id}"
                    )
                    col1, col2 = st.columns([1, 1])
                    with col1:
                        use_custom_r = st.checkbox(
                            "⏰ 自訂實際歸還時間", key=f"r_chk_{card_id}"
                        )
                    with col2:
                        custom_dt_r = None
                        if use_custom_r:
                            custom_dt_r = st.datetime_input(
                                "選擇時間", key=f"r_dt_{card_id}"
                            )

                    submit_r = st.form_submit_button("歸還卡片")
                    if submit_r:
                        return_card(
                            card_id, borrower, return_note, custom_dt_r
                        )
                        st.success(f"✅ {card_id} 已成功歸還！")
                        st.rerun()

with tab2:
    st.subheader("📜 歷史借還紀錄 (前50筆)")
    try:
        logs_res = (
            supabase.table("borrow_logs")
            .select("timestamp, created_at, card_id, borrower, action, note")
            .order("id", desc=True)
            .limit(50)
            .execute()
        )

        if logs_res.data:
            formatted_logs = []
            for log in logs_res.data:
                formatted_logs.append(
                    {
                        "實際借還時間": log.get("timestamp", ""),
                        "系統填單時間": log.get(
                            "created_at", log.get("timestamp", "")
                        ),
                        "卡號": log.get("card_id", ""),
                        "工號與姓名": log.get("borrower", ""),
                        "動作": (
                            "借出"
                            if log.get("action") == "BORROW"
                            else "歸還"
                        ),
                        "備註": (
                            log.get("note") if log.get("note") else "-"
                        ),
                    }
                )
            st.dataframe(formatted_logs, use_container_width=True)
        else:
            st.info("尚無借還紀錄")
    except Exception as e:
        st.error(f"❌ 讀取歷史紀錄失敗：{e}")
