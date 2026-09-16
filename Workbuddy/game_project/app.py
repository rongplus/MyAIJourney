import sqlite3
from datetime import datetime
from gradio import Interface, Input, Button, Textbox, Markdown, outputs, Column

app_title = "简易记账应用"

def create_db_connection(db_path):
    conn = None
    try:
        conn = sqlite3.connect(db_path)
    except sqlite3.Error as e:
        print(e)
    return conn

def init_db(conn):
    with conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY,
                date TEXT,
                description TEXT,
                amount REAL
            )
        ''')

def add_account(conn, date, description, amount):
    sql = ''' INSERT INTO accounts(date, description, amount)
              VALUES(?,?,?) '''
    cur = conn.cursor()
    cur.execute(sql, (date, description, amount))
    return cur.lastrowid

def delete_account(conn, id):
    sql = 'DELETE FROM accounts WHERE id=?'
    cur = conn.cursor()
    cur.execute(sql, (id,))

def get_accounts(conn):
    cur = conn.cursor()
    cur.execute("SELECT * FROM accounts")
    rows = cur.fetchall()
    return rows

def generate_monthly_report(conn, month, year):
    cur = conn.cursor()
    cur.execute("SELECT * FROM accounts WHERE strftime('%Y-%m', date) = ?", (f'{year}-{month:02}',))
    rows = cur.fetchall()
    total = sum(row[3] for row in rows)
    return f"月度报表：{month}/{year}\n总收入：{total}"

def main():
    db_path = "accounts.db"
    conn = create_db_connection(db_path)
    init_db(conn)

    def add_account_callback(date, description, amount):
        add_account(conn, date, description, amount)
        return "账目已添加"

    def delete_account_callback(id):
        delete_account(conn, id)
        return "账目已删除"

    def get_accounts_callback():
        rows = get_accounts(conn)
        return rows

    def generate_report_callback(month, year):
        return generate_monthly_report(conn, month, year)

    def on_close():
        conn.close()

    with Interface(
        title=app_title,
        description="简易记账应用",
        layout="vertical",
        css="body { background-color: #f0f0f0; }",
        examples=[],
    ) as iface:
        with Column():
            date_input = Input(type="date", label="日期", placeholder="选择日期")
            description_input = Input(type="text", label="说明", placeholder="输入说明")
            amount_input = Input(type="number", label="金额", placeholder="输入金额")
            add_button = Button("添加账目")
            add_button.click(
                fn=add_account_callback,
                inputs=[date_input, description_input, amount_input],
                outputs=Textbox()
            )

            with Column():
                id_input = Input(type="number", label="账目ID", placeholder="输入ID")
                delete_button = Button("删除账目")
                delete_button.click(
                    fn=delete_account_callback,
                    inputs=[id_input],
                    outputs=Textbox()
                )

            with Column():
                get_button = Button("查看账目")
                get_button.click(
                    fn=get_accounts_callback,
                    outputs=outputs.DataFrame()
                )

            with Column():
                month_input = Input(type="number", label="月份", placeholder="输入月份")
                year_input = Input(type="number", label="年份", placeholder="输入年份")
                report_button = Button("生成月度报表")
                report_button.click(
                    fn=generate_report_callback,
                    inputs=[month_input, year_input],
                    outputs=Textbox()
                )

        iface.launch()

if __name__ == "__main__":
    main()