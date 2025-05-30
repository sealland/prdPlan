from flask import Flask, jsonify, request
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


@app.route('/api/production_plan/update_by_machine_and_date_range', methods=['POST'])
def update_production_plan_by_machine_and_date_range():
    data = request.get_json()

    if not data:
        return jsonify({"error": "Invalid JSON data"}), 400

    machine_code = data.get('machine_code')
    delete_start_date_str = data.get('delete_start_date')
    delete_end_date_str = data.get('delete_end_date')
    new_plan_data = data.get('new_plan_data')  # นี่คือ Array of Objects

    if not all([machine_code, delete_start_date_str, delete_end_date_str]):
        return jsonify({"error": "Missing required fields: machine_code, delete_start_date, delete_end_date"}), 400

    if new_plan_data is None or not isinstance(new_plan_data, list):
        # อนุญาตให้ new_plan_data เป็น Array ว่างได้
        # แต่ถ้ามาเป็น None หรือไม่ใช่ list เลย ถือว่าผิด Format
        if new_plan_data is None and isinstance(data.get('new_plan_data'), list) and len(
                data.get('new_plan_data')) == 0:
            # กรณีนี้คือ Frontend ส่ง "new_plan_data": [] มา ซึ่งถูกต้อง
            new_plan_data = []  # ทำให้ new_plan_data เป็น empty list จริงๆ
        else:
            return jsonify({"error": "new_plan_data must be a list (can be empty)"}), 400

    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            return jsonify({"error": "Database connection failed"}), 500

        cursor = conn.cursor()

        # --- Start Transaction ---
        # pyodbc โดย default จะ auto-commit ถ้าไม่ได้ตั้ง conn.autocommit = False
        # เพื่อความชัดเจน เราจะควบคุมเอง หรือถ้า DB Driver/Server รองรับ BEGIN TRANSACTION ก็ใช้ได้
        # สำหรับ SQL Server, pyodbc จะอยู่ใน autocommit mode โดย default
        # ถ้าต้องการ Manual commit/rollback: conn.autocommit = False
        # แต่การใช้ try/except แล้ว conn.commit() หรือ conn.rollback() ก็เป็นวิธีที่ใช้ได้
        # สำหรับตอนนี้ เราจะทำ Operations ตามลำดับ และถ้ามี Error จะไม่ Commit

        # 1. Delete existing data in the date range for the specified machine
        sql_delete = """
            DELETE FROM dbo.production_planDev
            WHERE machine = ? AND postingdate >= ? AND postingdate <= ?
        """
        cursor.execute(sql_delete, machine_code, delete_start_date_str, delete_end_date_str)
        # print(f"Deleted rows: {cursor.rowcount}") # For debugging

        # 2. Insert new plan data (if any)
        if new_plan_data:
            # SQL INSERT Statement อ้างอิงตาม CREATE TABLE [dbo].[production_planDev]
            sql_insert_final = """
                       INSERT INTO dbo.production_planDev (
                           machine, station, postingdate, size, ton,                     -- 5
                           protime, htime, description, change, username,                -- 5 (รวมเป็น 10)
                           material_code, approve, approveby, approvedate, status,       -- 5 (รวมเป็น 15)
                           shift, complete, s_time, e_time, bl_grade,                    -- 5 (รวมเป็น 20)
                           rev                                                            -- 1 (รวมเป็น 21)
                       ) VALUES (
                           ?, ?, ?, ?, ?,  -- machine, station, postingdate, size, ton
                           ?, ?, ?, GETDATE(), ?,  -- protime, htime, description, change (auto), username
                           ?, NULL, NULL, NULL, ?,  -- material_code, approve (NULL), approveby (NULL), approvedate (NULL), status
                           ?, ?, ?, ?, ?,  -- shift, complete (0), s_time, e_time, bl_grade
                           NULL            -- rev (NULL)
                       )
                   """
            # จำนวน ? ใน VALUES คือ 17 ตัว (ไม่รวม GETDATE() และ NULL 4 ตัวที่ hardcode)
            # รวมทั้งหมด 21 ค่าที่จะถูกใส่เข้าไปใน 21 คอลัมน์

            for item in new_plan_data:
                # --- Primary Key Components (จาก item และ machine_code หลัก) ---
                # machine (มาจาก machine_code หลัก)
                station = item.get('station')
                postingdate_str = item.get('postingdate')  # ควรเป็น 'YYYY-MM-DD' หรือ 'YYYY-MM-DD HH:MM:SS'
                material_code = item.get('material_code')
                shift_val = item.get('shift')

                # ตรวจสอบ PK Components
                if not all([station, postingdate_str, material_code, shift_val]):
                    raise ValueError(f"Missing Primary Key components in item: {item}")

                # --- Other Columns (จาก item หรือ default/hardcoded) ---
                size = item.get('size')

                ton_val = item.get('ton')
                if ton_val is not None:
                    try:
                        ton_val = float(ton_val)
                    except (ValueError, TypeError):  # เพิ่ม TypeError เผื่อค่าที่ส่งมาไม่ใช่ string/number
                        raise ValueError(f"Invalid value for 'ton' (must be a number) in item: {item}")

                protime = item.get('protime')

                htime_val = item.get('htime')
                if htime_val is not None:
                    try:
                        htime_val = float(htime_val)  # decimal ใน Python ก็ใช้ float ได้ หรือจะใช้ Decimal object
                    except (ValueError, TypeError):
                        raise ValueError(f"Invalid value for 'htime' (must be a number) in item: {item}")

                description = item.get('description')
                # change (จะถูกใส่โดย GETDATE() ใน SQL)
                username_to_insert = 'WebAppUser'  # Default username
                # material_code (ดึงมาแล้วด้านบน)
                # approve, approveby, approvedate (เป็น NULL ใน SQL)
                status_to_insert = 'วางแผนไว้'  # Hardcode status
                # shift_val (ดึงมาแล้วด้านบน)
                complete_to_insert = 0  # Hardcode complete
                s_time = item.get('s_time')
                e_time = item.get('e_time')
                bl_grade = item.get('bl_grade')
                # rev (เป็น NULL ใน SQL)

                # --- Execute Insert ---
                cursor.execute(sql_insert_final,
                               machine_code,  # 1. machine
                               station,  # 2. station
                               postingdate_str,  # 3. postingdate (pyodbc จะจัดการแปลง string เป็น datetime)
                               size,  # 4. size
                               ton_val,  # 5. ton
                               protime,  # 6. protime
                               htime_val,  # 7. htime
                               description,  # 8. description
                               # GETDATE() is 9. change
                               username_to_insert,  # 10. username
                               material_code,  # 11. material_code
                               # NULL, NULL, NULL are 12,13,14. approve, approveby, approvedate
                               status_to_insert,  # 15. status
                               shift_val,  # 16. shift
                               complete_to_insert,  # 17. complete
                               s_time,  # 18. s_time
                               e_time,  # 19. e_time
                               bl_grade  # 20. bl_grade
                               # NULL is 21. rev
                               )

        conn.commit()
        return jsonify({"message": "Production plan updated successfully"}), 200

    except pyodbc.Error as db_err:
        if conn:
            conn.rollback()  # Rollback transaction ถ้าเกิด Database error
        print(f"Database error: {db_err}")
        return jsonify({"error": f"Database error occurred: {str(db_err)}"}), 500
    except ValueError as val_err:  # สำหรับ Error จากการ Validate ข้อมูลของเราเอง
        if conn:
            conn.rollback()
        print(f"Validation error: {val_err}")
        return jsonify({"error": f"Data validation error: {str(val_err)}"}), 400
    except Exception as e:
        if conn:
            conn.rollback()  # Rollback transaction ถ้าเกิด error อื่นๆ
        print(f"An unexpected error occurred: {e}")
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    # debug=True ทำให้ server restart อัตโนมัติเมื่อมีการแก้ไขโค้ด และแสดง error ที่ละเอียดขึ้น
    # อย่าใช้ debug=True ใน production environment!
    app.run(debug=True)