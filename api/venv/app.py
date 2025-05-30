from flask import Flask, jsonify
from flask_cors import CORS
import pyodbc

app = Flask(__name__)
CORS(app)
# --- การตั้งค่าการเชื่อมต่อ SQL Server ---
# !!! 중요: กรุณาแก้ไขค่าเหล่านี้ให้ตรงกับ SQL Server ของคุณ !!!
# และระวังเรื่อง Security หากนำโค้ดนี้ไปใช้จริง ควรดึงค่าเหล่านี้มาจาก Environment Variables หรือ Config File
DB_CONFIG = {
    'driver': '{ODBC Driver 17 for SQL Server}', # หรือ Driver อื่นๆ ที่คุณมี เช่น {SQL Server}
    'server': '192.168.100.222',         # เช่น localhost, MYSERVER\SQLEXPRESS
    'database': 'CEO_REPORT',
    'uid': 'sa',                     # ถ้าใช้ Windows Authentication อาจไม่ต้องใส่ uid/pwd
    'pwd': '',
    # ถ้าใช้ Windows Authentication (Trusted Connection) ให้ uncomment บรรทัดล่าง และ comment uid/pwd ออก
    # 'trusted_connection': 'yes',
}

def get_db_connection():
    """สร้าง Connection ไปยัง SQL Server"""
    conn_str = (
        f"DRIVER={DB_CONFIG['driver']};"
        f"SERVER={DB_CONFIG['server']};"
        f"DATABASE={DB_CONFIG['database']};"
    )
    if 'trusted_connection' in DB_CONFIG and DB_CONFIG['trusted_connection'] == 'yes':
        conn_str += "Trusted_Connection=yes;"
    else:
        conn_str += f"UID={DB_CONFIG['uid']};PWD={DB_CONFIG['pwd']};"

    try:
        conn = pyodbc.connect(conn_str)
        return conn
    except pyodbc.Error as ex:
        sqlstate = ex.args[0]
        print(f"Error connecting to database: {sqlstate}")
        # ในสถานการณ์จริง อาจจะ log error หรือ re-raise exception
        # สำหรับตอนนี้ เราจะ print error และ return None
        return None

@app.route('/api/production_plans', methods=['GET'])
def get_production_plans():
    conn = None # Initialize conn to None
    try:
        conn = get_db_connection()
        if conn is None:
            return jsonify({"error": "Database connection failed"}), 500

        cursor = conn.cursor()
        cursor.execute("""
            SELECT  machine, station, postingdate, material_code, size, ton
            FROM dbo.production_planDev
            ORDER BY postingdate desc , machine asc
        """) # เพิ่ม ORDER BY เพื่อให้ข้อมูลเรียงตามวันที่และเครื่องจักร

        # ดึงชื่อคอลัมน์จาก cursor.description
        columns = [column[0] for column in cursor.description]
        # สร้าง list of dictionaries
        results = []
        for row in cursor.fetchall():
            results.append(dict(zip(columns, row)))

        return jsonify(results)

    except pyodbc.Error as e:
        # Log the error or handle it more gracefully
        print(f"Database query error: {e}")
        return jsonify({"error": "An error occurred while fetching data"}), 500
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    # debug=True ทำให้ server restart อัตโนมัติเมื่อมีการแก้ไขโค้ด และแสดง error ที่ละเอียดขึ้น
    # อย่าใช้ debug=True ใน production environment!
    app.run(debug=True)