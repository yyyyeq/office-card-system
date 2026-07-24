from datetime import datetime
import pandas as pd
import pytz
import streamlit as st
from supabase import create_client

# 1. 頁面基本設定
st.set_page_config(
    page_title="辦公室備用卡管理系統", page_icon="💳", layout="centered"
)

# 2. 初始化 Supabase 連線
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# 設為台北時區
TAIPEI_TZ = pytz.timezone("Asia/Taipei")


# 3. 載入員工工號對照表 (使用 cache 避免重複讀取)
@st.cache_data
def load_employee_data():
    try:
        df = pd.read_excel("employees.xlsx")
        # 轉成字串並去除前後空格
        df["工號"] = df["工號"].astype(str).str.strip()
        df["姓名"] = df["姓名"].astype(str).str.strip()
        # 轉成字典方便快速查找: {'E001': '王小明', ...}
        emp_dict = dict(zip(df["工號"], df["姓名"]))
        return emp_dict
    except Exception as e:
        st.error(f"讀取 employees.xlsx 失敗，請確認檔案格式是否正確：{e}")
        return {}


EMP_DICT = load_employee_data()


# --- 輔助函式 ---
def get_cards():
    response = (
        supabase.table("cards")
        .select("*")
        .order("card_id", desc=False)
        .execute()
    )
    return response.data


def borrow_card(card_id, borrower):
    now_iso = datetime.now(TAIPEI_TZ).isoformat()
    supabase.table("cards").update(
        {"status": "BORROWED", "borrower": borrower, "borrowed_at": now_iso}
    ).eq("card_id", card_id).execute()

    supabase.table("borrow_logs").insert(
        {
            "card_id": card_id,
            "borrower": borrower,
            "action": "BORROW",
            "timestamp": now_iso,
        }
    ).execute()


def return_card(card_id, borrower):
    now_iso = datetime.now(TAIPEI_TZ).isoformat()
    supabase.table("cards").update(
        {"status": "AVAILABLE", "borrower": None, "borrowed_at": None}
    ).eq("card_id", card_id).execute()

    supabase.table("borrow_logs").insert(
        {
            "card_id": card_id,
            "borrower": borrower,
            "action": "RETURN",
            "timestamp": now_iso,
        }
    ).execute()


def format_time(time_str):
    if not time_str:
        return ""
    try:
        dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
        return dt.astimezone(TAIPEI_TZ).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return time_str


# --- 主介面 ---
st.title("💳 辦公室備用卡管理系統")

tab1, tab2 = st.tabs(["📌 卡片借還", "📜 歷史紀錄"])

with tab1:
    cards = get_cards()
    for card in cards:
        card_id = card["card_id"]
        status = card["status"]
        borrower = card["borrower"]
        borrowed_at = format_time(card["borrowed_at"])

        if status == "AVAILABLE":
            with st.container(border=True):
                st.subheader(f"🟢 {card_id}（可借用）")
                with st.form(key=f"borrow_form_{card_id}"):
                    emp_id_input = (
                        st.text_input(
                            "請輸入工號",
                            placeholder="例如：E001",
                            key=f"input_{card_id}",
                        )
                        .strip()
                        .upper()
                    )
                    submit = st.form_submit_button("確認借用")

                    if submit:
                        if not emp_id_input:
                            st.warning("⚠️ 請輸入工號！")
                        elif emp_id_input in EMP_DICT:
                            emp_name = EMP_DICT[emp_id_input]
                            borrower_info = f"{emp_name} ({emp_id_input})"
                            borrow_card(card_id, borrower_info)
                            st.success(f"✅ {card_id} 借用成功！借用人：{borrower_info}")
                            st.rerun()
                        else:
                            st.error("❌ 找不到此工號，請確認工號是否正確！")
        else:
            with st.container(border=True):
                st.subheader(f"🔴 {card_id}（借出中）")
                st.write(f"**借用人**：{borrower}")
                st.write(f"**借出時間**：{borrowed_at}")
                if st.button("歸還卡片", key=f"return_{card_id}"):
                    return_card(card_id, borrower)
                    st.success(f"✅ {card_id} 已成功歸還！")
                    st.rerun()

with tab2:
    st.subheader("📜 歷史借還紀錄 (前50筆)")
    logs_res = (
        supabase.table("borrow_logs")
        .select("timestamp, card_id, borrower, action")
        .order("id", desc=True)
        .limit(50)
        .execute()
    )

    if logs_res.data:
        formatted_logs = []
        for log in logs_res.data:
            formatted_logs.append(
                {
                    "時間": format_time(log["timestamp"]),
                    "卡號": log["card_id"],
                    "借用人": log["borrower"],
                    "動作": "借出" if log["action"] == "BORROW" else "歸還",
                }
            )
        st.dataframe(formatted_logs, use_container_width=True)
    else:
        st.info("尚無借還紀錄")