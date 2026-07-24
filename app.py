from datetime import datetime
import pandas as pd
import pytz
import streamlit as st
from supabase import create_client

# 1. 頁面基本設定 (寬頁面 layout="wide"，讓三張卡片並排)
st.set_page_config(
    page_title="白卡借用系統", page_icon="💳", layout="wide"
)

# 2. 初始化 Supabase 連線
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    st.error(f"❌ Supabase 連線設定失敗：{e}")
    st.stop()

TAIPEI_TZ = pytz.timezone("Asia/Taipei")


# 時間格式化輔助函式 (裁切為 YYYY-MM-DD HH:MM:SS)
def format_time_str(time_str):
    if not time_str:
        return "-"
    try:
        clean_str = (
            str(time_str)
            .replace("T", " ")
            .split("+")[0]
            .split(".")[0]
            .strip()
        )
        dt = datetime.fromisoformat(clean_str)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(time_str).replace("T", " ")[:19]


# 3. 載入員工名單
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
        return [f"{row['工號']} - {row['姓名']}" for _, row in df.iterrows()]
    except Exception:
        return []


EMP_LIST = load_employees()


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
        st.error(f"❌ 讀取卡片失敗：{e}")
        return []


def borrow_card(card_id, borrower, note, custom_date, custom_time_val):
    sys_now_dt = datetime.now(TAIPEI_TZ)
    sys_now_str = sys_now_dt.strftime("%Y-%m-%d %H:%M:%S")

    # 如果有填寫自訂時間，組合日期與時間；否則使用當下系統時間
    if custom_date and custom_time_val:
        event_time = datetime.combine(
            custom_date, custom_time_val
        ).strftime("%Y-%m-%d %H:%M:%S")
    else:
        event_time = sys_now_str

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
            "created_at": sys_now_str,
            "note": note,
        }
    ).execute()


def return_card(card_id, borrower, note, custom_date, custom_time_val):
    sys_now_dt = datetime.now(TAIPEI_TZ)
    sys_now_str = sys_now_dt.strftime("%Y-%m-%d %H:%M:%S")

    if custom_date and custom_time_val:
        event_time = datetime.combine(
            custom_date, custom_time_val
        ).strftime("%Y-%m-%d %H:%M:%S")
    else:
        event_time = sys_now_str

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
            "created_at": sys_now_str,
            "note": note,
        }
    ).execute()


# --- 主介面 ---
st.title("💳 白卡借用系統")

tab1, tab2 = st.tabs(["📌 卡片借還", "📜 歷史紀錄"])

with tab1:
    cards = get_cards()
    if not cards:
        st.info("💡 目前資料庫中沒有卡片資料。")
    else:
        # 建立 3 欄式佈局，讓卡片開頁面就橫向並排呈現
        cols = st.columns(3)

        for idx, card in enumerate(cards):
            card_id = card["card_id"]
            status = card["status"]
            borrower = card["borrower"]
            borrowed_at = format_time_str(card.get("borrowed_at"))
            note = card.get("note")

            col = cols[idx % 3]

            with col:
                now_dt = datetime.now(TAIPEI_TZ)

                if status == "AVAILABLE":
                    with st.container(border=True):
                        st.subheader(f"🟢 {card_id}")
                        st.caption("狀態：可借用")

                        with st.form(key=f"borrow_form_{card_id}"):
                            if EMP_LIST:
                                borrower_selected = st.selectbox(
                                    "選擇工號與姓名",
                                    options=["-- 請選擇工號與姓名 --"]
                                    + EMP_LIST,
                                    key=f"select_{card_id}",
                                )
                            else:
                                borrower_selected = st.text_input(
                                    "請輸入工號與姓名",
                                    key=f"input_{card_id}",
                                )

                            note_input = st.text_input(
                                "📝 備註 (選填)",
                                placeholder="如：訪客姓名 / 補登說明",
                                key=f"note_{card_id}",
                            )

                            # ⏰ 時間補登開關與填寫欄位
                            need_custom = st.checkbox(
                                "⏰ 補登實際借用時間", key=f"chk_{card_id}"
                            )
                            c_date, c_time = None, None

                            if need_custom:
                                sub_col1, sub_col2 = st.columns(2)
                                with sub_col1:
                                    c_date = st.date_input(
                                        "📅 實際日期",
                                        value=now_dt.date(),
                                        key=f"d_{card_id}",
                                    )
                                with sub_col2:
                                    c_time = st.time_input(
                                        "⏰ 實際時間",
                                        value=now_dt.time(),
                                        key=f"t_{card_id}",
                                    )

                            submit = st.form_submit_button(
                                "確認借用", use_container_width=True
                            )
                            if submit:
                                if (
                                    borrower_selected
                                    == "-- 請選擇工號與姓名 --"
                                    or not borrower_selected
                                ):
                                    st.warning("⚠️ 請選擇或輸入借用人！")
                                else:
                                    borrow_card(
                                        card_id,
                                        borrower_selected,
                                        note_input,
                                        c_date,
                                        c_time,
                                    )
                                    st.success(f"✅ {card_id} 借用成功！")
                                    st.rerun()
                else:
                    with st.container(border=True):
                        st.subheader(f"🔴 {card_id}")
                        st.caption("狀態：借出中")
                        st.markdown(f"👤 **借用人**：{borrower}")
                        if note:
                            st.markdown(f"📝 **備註**：{note}")
                        st.markdown(f"🕒 **借用時間**：\n`{borrowed_at}`")

                        with st.form(key=f"return_form_{card_id}"):
                            return_note = st.text_input(
                                "📝 歸還備註 (選填)",
                                key=f"r_note_{card_id}",
                            )

                            # ⏰ 時間補登開關與填寫欄位
                            need_custom_r = st.checkbox(
                                "⏰ 補登實際歸還時間",
                                key=f"r_chk_{card_id}",
                            )
                            cr_date, cr_time = None, None

                            if need_custom_r:
                                sub_col1, sub_col2 = st.columns(2)
                                with sub_col1:
                                    cr_date = st.date_input(
                                        "📅 實際日期",
                                        value=now_dt.date(),
                                        key=f"rd_{card_id}",
                                    )
                                with sub_col2:
                                    cr_time = st.time_input(
                                        "⏰ 實際時間",
                                        value=now_dt.time(),
                                        key=f"rt_{card_id}",
                                    )

                            submit_r = st.form_submit_button(
                                "歸還卡片", use_container_width=True
                            )
                            if submit_r:
                                return_card(
                                    card_id,
                                    borrower,
                                    return_note,
                                    cr_date,
                                    cr_time,
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
                        "實際借還時間": format_time_str(log.get("timestamp")),
                        "系統填單時間": format_time_str(
                            log.get("created_at", log.get("timestamp"))
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
