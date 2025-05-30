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
    # รับ query parameters
    station_param_key = 'station'
    station_filter = request.args.get(station_param_key)
    start_date_filter = request.args.get('startDate')  # ชื่อ parameter ควรตรงกับที่ Frontend จะส่ง
    end_date_filter = request.args.get('endDate')

    print(f"--- Debug get_production_plans ---")
    print(f"Request Args: {request.args}")  # Print request.args ทั้งหมดออกมาดู
    print(f"Value for key '{station_param_key}': {station_filter}")
    print(f"Type of value for key '{station_param_key}': {type(station_filter)}")

    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            return jsonify({"error": "Database connection failed"}), 500

        cursor = conn.cursor()

        # สร้าง SQL query เบื้องต้น
        sql_query = "SELECT machine, station, postingdate, material_code, size, ton, description, protime, htime, shift, s_time, e_time, bl_grade, rev, username FROM dbo.production_planDev"  # เพิ่มคอลัมน์ที่ต้องการให้ครบ

        conditions = []
        params = []

        if station_filter and station_filter.strip() != '' and station_filter.lower() != 'none':
            conditions.append("station = ?")
            params.append(station_filter.strip())  # ใช้ .strip() เพื่อตัด space ที่อาจจะติดมา
            print(f"Condition added: station = ?, Param: {station_filter.strip()}")
        else:
            print(f"No valid station filter applied. station_filter was: '{station_filter}'")
        if start_date_filter:
            conditions.append("postingdate >= ?")
            params.append(start_date_filter)
        if end_date_filter:
            conditions.append("postingdate <= ?")
            params.append(end_date_filter)

        if conditions:
            sql_query += " WHERE " + " AND ".join(conditions)

        sql_query += " ORDER BY postingdate, station, machine, s_time"  # หรือการเรียงลำดับที่คุณต้องการ

        cursor.execute(sql_query, *params)  # ใช้ *params เพื่อ unpack list

        columns = [column[0] for column in cursor.description]
        results = []
        for row in cursor.fetchall():
            results.append(dict(zip(columns, row)))

        return jsonify(results)

    except pyodbc.Error as e:
        print(f"Database query error: {e}")
        return jsonify({"error": "An error occurred while fetching data"}), 500
    finally:
        if conn:
            conn.close()


@app.route('/api/production_plan/update_by_machine_and_date_range', methods=['POST'])
def update_production_plan_data():
    data = request.get_json()

    if not station_code:  # ถ้ายังใช้ key "machine_code" จาก frontend แต่หมายถึง station
        station_code = data.get('machine_code')  # fallback หรือบังคับให้ frontend เปลี่ยน

    delete_start_date_str = data.get('delete_start_date')
    delete_end_date_str = data.get('delete_end_date')
    new_plan_data = data.get('new_plan_data')

    if not all([station_code, delete_start_date_str, delete_end_date_str]):
        return jsonify({"error": "Missing required fields: station_code, delete_start_date, delete_end_date"}), 400

    if new_plan_data is None or not isinstance(new_plan_data, list):
        # อนุญาตให้ new_plan_data เป็น Array ว่างได้
        # แต่ถ้ามาเป็น None หรือไม่ใช่ list เลย ถือว่าผิด Format
        if new_plan_data is None and isinstance(data.get('new_plan_data'), list) and len(
                data.get('new_plan_data')) == 0:
            # กรณีนี้คือ Frontend ส่ง "new_plan_data": [] มา ซึ่งถูกต้อง
            new_plan_data = []  # ทำให้ new_plan_data เป็น empty list จริงๆ
        else:
            return jsonify({"error": "new_plan_data must be a list (can be empty)"}), 400
    print(f"Received new_plan_data type: {type(new_plan_data)}")  # ดู type
    print(f"Received new_plan_data content: {new_plan_data}")  # ดูเนื้อหา
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
                    WHERE station = ? AND postingdate >= ? AND postingdate <= ?
                """
        cursor.execute(sql_delete, station_code, delete_start_date_str, delete_end_date_str)
        # print(f"Deleted rows: {cursor.rowcount}") # For debugging

        # 2. Insert new plan data
        if new_plan_data:
            sql_insert_final = """
                        INSERT INTO dbo.production_planDev (
                            machine, station, postingdate, size, ton,
                            protime, htime, description, change, username,
                            material_code, approve, approveby, approvedate, status,
                            shift, complete, s_time, e_time, bl_grade,
                            rev
                        ) VALUES ( ?, ?, ?, ?, ?, ?, ?, ?, GETDATE(), ?, ?, NULL, NULL, NULL, ?, ?, ?, ?, ?, ?, NULL )
                    """
            for item in new_plan_data:
                # PK Components
                machine_val = item.get('machine')  # machine ยังคงต้องมีในแต่ละ item
                # station_val = item.get('station') # station จะใช้ station_code หลัก
                postingdate_str = item.get('postingdate')
                material_code = item.get('material_code')
                shift_val = item.get('shift')

                # **สำคัญ:** ตรวจสอบ PK ที่จำเป็น
                if not all([machine_val, postingdate_str, material_code, shift_val]):
                    raise ValueError(
                        f"Missing PK components (machine, postingdate, material_code, shift) in item: {item}")

                # --- Other Columns (จาก item หรือ default/hardcoded) ---
                size = item.get('size')
                ton_val = item.get('ton')
                if ton_val is not None:
                    try:
                        ton_val = float(ton_val)
                    except (ValueError, TypeError):
                        raise ValueError(f"Invalid 'ton' in {item}")

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
                               machine_val,  # machine จาก item
                               station_code,  # station จาก parameter หลัก
                               postingdate_str,
                               size, ton_val,
                               item.get('protime'), item.get('htime'), item.get('description'),
                               'WebAppUser',  # username
                               material_code,
                               'วางแผนไว้',  # status
                               shift_val,
                               0,  # complete
                               item.get('s_time'), item.get('e_time'), item.get('bl_grade')
                               )

        conn.commit()
        return jsonify({"message": "Production plan updated successfully for station: " + station_code}), 200

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