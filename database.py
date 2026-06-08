import os
import psycopg2
from psycopg2.extras import RealDictCursor
DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "127.0.0.1"),
    "port": int(os.environ.get("DB_PORT", 5433)),
    "database": os.environ.get("DB_NAME", "taskdb"),
    "user": os.environ.get("DB_USER", "postgres"),
    "password": os.environ.get("DB_PASSWORD", "mysecretpassword")
}

def get_connection():
    conn = psycopg2.connect(**DB_CONFIG)
    return conn


def get_cursor():
    """Возвращает курсор с RealDictCursor (результаты в виде словарей)"""
    conn = get_connection()
    return conn, conn.cursor(cursor_factory=RealDictCursor)


# import psycopg2
# from psycopg2.extras import RealDictCursor
# DB_CONFIG = {
#     "host": "127.0.0.1",
#     "port": 5433,
#     "database": "taskdb",
#     "user": "postgres",
#     "password": "mysecretpassword"
# }
#
# def get_connection():
#     """Возвращает соединение с базой данных"""
#     return psycopg2.connect(**DB_CONFIG)
#
#
# def get_cursor():
#     """Возвращает курсор с RealDictCursor (результаты в виде словарей)"""
#     conn = get_connection()
#     return conn, conn.cursor(cursor_factory=RealDictCursor)
