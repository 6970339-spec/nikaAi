import sqlite3
import pandas as pd

DB_PATH = "bot.db"
OUTPUT_FILE = "bot_dump.xlsx"

# подключаемся к базе
conn = sqlite3.connect(DB_PATH)

# получаем список всех таблиц
tables = pd.read_sql(
    "SELECT name FROM sqlite_master WHERE type='table'",
    conn
)["name"].tolist()

if not tables:
    print("В базе нет таблиц")
    conn.close()
    exit()

# записываем каждую таблицу в отдельный лист Excel
with pd.ExcelWriter(OUTPUT_FILE, engine="openpyxl") as writer:
    for table in tables:
        df = pd.read_sql(f"SELECT * FROM {table}", conn)
        df.to_excel(writer, sheet_name=table[:31], index=False)
        print(f"Экспортирована таблица: {table}")

conn.close()

print(f"\n✅ Готово! Файл сохранён как {OUTPUT_FILE}")
