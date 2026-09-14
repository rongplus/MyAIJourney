import sqlite3
from datetime import date
from pathlib import Path

DB_PATH = Path(__file__).with_name("account_book.db")

def connect_db(db_path=DB_PATH):
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("CREATE TABLE IF NOT EXISTS accounts (id INTEGER PRIMARY KEY AUTOINCREMENT, entry_date TEXT NOT NULL, description TEXT NOT NULL, category TEXT NOT NULL, amount REAL NOT NULL CHECK(amount >= 0))")
    connection.commit()
    return connection

def add_account(entry_date, description, category, amount, db_path=DB_PATH):
    date.fromisoformat(entry_date)
    amount = float(amount)
    if not description.strip() or amount < 0:
        raise ValueError("description is required and amount must be non-negative")
    with connect_db(db_path) as connection:
        cursor = connection.execute("INSERT INTO accounts(entry_date, description, category, amount) VALUES (?, ?, ?, ?)", (entry_date, description.strip(), category.strip() or "其他", amount))
    return cursor.lastrowid

def delete_account(account_id, db_path=DB_PATH):
    with connect_db(db_path) as connection:
        cursor = connection.execute("DELETE FROM accounts WHERE id = ?", (int(account_id),))
    return cursor.rowcount == 1

def list_accounts(month=None, db_path=DB_PATH):
    with connect_db(db_path) as connection:
        query = "SELECT * FROM accounts ORDER BY entry_date, id"
        params = ()
        if month:
            query = "SELECT * FROM accounts WHERE entry_date LIKE ? ORDER BY entry_date, id"
            params = (f"{month}%",)
        return [dict(row) for row in connection.execute(query, params).fetchall()]

def monthly_report(month, db_path=DB_PATH):
    rows = list_accounts(month, db_path)
    by_category = {}
    for row in rows:
        by_category[row["category"]] = by_category.get(row["category"], 0) + row["amount"]
    return {"month": month, "count": len(rows), "total": sum(by_category.values()), "by_category": by_category}

def launch_ui():
    import gradio as gr
    with gr.Blocks(title="记账助手") as demo:
        gr.Markdown("# 记账助手")
        entry_date = gr.Textbox(label="日期", value=date.today().isoformat())
        description = gr.Textbox(label="说明")
        category = gr.Textbox(label="分类", value="其他")
        amount = gr.Number(label="金额", minimum=0)
        output = gr.JSON(label="账目")
        add = gr.Button("添加账目")
        add.click(lambda d, s, c, a: (add_account(d, s, c, a), list_accounts(d[:7]))[1], [entry_date, description, category, amount], output)
    demo.launch()

if __name__ == "__main__":
    launch_ui()
