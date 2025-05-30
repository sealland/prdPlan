from flask import Flask, jsonify, request
from flask_cors import CORS
from datetime import datetime
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


def parse_gantt_task_id(task_id_str):
    try:
        print(f"--- Attempting to parse task_id: '{task_id_str}' ---")  # Log ID ที่ได้รับ
        parts = task_id_str.split('_')
        print(f"Split parts: {parts}")
        print(f"Number of parts: {len(parts)}")

        if len(parts) < 6 or parts[0] != 'task':  # คาดหวังอย่างน้อย 6 ส่วน: task, M, S, MC, Date, Shift
            print(f"Parse Error: Invalid format - Expected at least 6 parts starting with 'task'.")
            return None

        # ดึงค่าแต่ละส่วนออกมา
        machine_val = parts[1]
        station_val = parts[2]
        material_code_val = parts[3]
        postingdate_str_val = parts[4]
        shift_val_val = parts[5]  # อาจจะมีส่วน index ต่อท้ายถ้า len(parts) > 6

        print(f"Extracted Machine: '{machine_val}'")
        print(f"Extracted Station: '{station_val}'")
        print(f"Extracted Material Code: '{material_code_val}'")
        print(f"Extracted Posting Date String: '{postingdate_str_val}'")
        print(f"Extracted Shift: '{shift_val_val}'")

        # ตรวจสอบค่า Fallback หรือค่าที่ไม่ต้องการ
        fallback_values = ['NO_MACHINE', 'NO_STATION', 'NO_MAT', 'NO_DATE', 'INVALID_DATE_FOR_ID', 'NO_SHIFT',
                           'undefined', 'null', '']

        pk_dict = {
            'machine': machine_val if machine_val not in fallback_values else None,
            'station': station_val if station_val not in fallback_values else None,
            'material_code': material_code_val if material_code_val not in fallback_values else None,
            'postingdate': postingdate_str_val if postingdate_str_val not in fallback_values else None,
            'shift': shift_val_val if shift_val_val not in fallback_values else None
        }
        print(f"PK Dict after initial assignment and fallback check: {pk_dict}")

        # Validate postingdate format
        if pk_dict['postingdate']:
            try:
                datetime.strptime(pk_dict['postingdate'], '%Y-%m-%d')
                print(f"Posting date '{pk_dict['postingdate']}' is valid format.")
            except ValueError:
                print(f"Parse Error: Invalid date format for postingdate '{pk_dict['postingdate']}'")
                pk_dict['postingdate'] = None  # ทำให้เป็น None ถ้า Format ผิด

        # ตรวจสอบว่า PKs ที่จำเป็น (หลังจาก Validate ทั้งหมด) มีค่าหรือไม่
        required_pks = ['machine', 'station', 'material_code', 'postingdate', 'shift']
        missing_pks = [k for k in required_pks if not pk_dict.get(k)]  # หา key ที่ค่าเป็น None หรือ Falsy

        if missing_pks:
            print(f"Parse Error: One or more critical PKs are missing/invalid after parsing. Missing: {missing_pks}")
            print(f"Final pk_dict before returning None due to missing PKs: {pk_dict}")
            return None  # ถ้า PK ตัวใดตัวหนึ่งที่จำเป็นหายไป ก็ไม่ควรดำเนินการต่อ

        print(f"Successfully parsed PKs: {pk_dict}")
        return pk_dict
    except Exception as e:
        print(f"Exception during parsing task_id '{task_id_str}': {e}")
        return None


@app.route('/api/gantt_task/update_schedule', methods=['PUT'])
def update_gantt_task_schedule():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON data from request"}), 400

    task_id_from_frontend = data.get('task_id')
    new_start_posting_date_str = data.get('new_start_posting_date')  # Frontend ส่ง 'YYYY-MM-DD'
    s_time_to_use_from_payload = data.get('s_time_to_use')
    e_time_to_use_from_payload = data.get('e_time_to_use')
    target_machine_from_payload = data.get('new_machine_id')

    print(f"--- Debug update_gantt_task_schedule (Received Payload) ---")
    print(f"task_id: '{task_id_from_frontend}'")
    print(f"new_start_posting_date: '{new_start_posting_date_str}'")
    print(f"s_time_to_use: '{s_time_to_use_from_payload}'")
    print(f"e_time_to_use: '{e_time_to_use_from_payload}'")
    print(f"new_machine_id: '{target_machine_from_payload}'")

    if not all([task_id_from_frontend, new_start_posting_date_str]):
        return jsonify({"error": "Missing required fields in payload: task_id, new_start_posting_date"}), 400

    original_pks = parse_gantt_task_id(task_id_from_frontend)
    if not original_pks:  # parse_gantt_task_id จะจัดการเรื่อง PK ไม่ครบหรือ Format ผิดแล้ว
        return jsonify({"error": f"Invalid or unparsable task_id: {task_id_from_frontend}"}), 400

    print(f"Parsed Original PKs: {original_pks}")

    # กำหนดค่าที่จะใช้ในการ Update/Insert
    final_target_machine = target_machine_from_payload if target_machine_from_payload and target_machine_from_payload.strip() else \
    original_pks['machine']
    final_new_posting_date = new_start_posting_date_str  # ควรจะเป็น 'YYYY-MM-DD' ที่ Valid

    # s_time และ e_time จะใช้ค่าจาก payload ถ้ามี, หรือ default (ถ้าไม่มี)
    # ใน Logic Delete-Insert เราจะดึง s_time, e_time จาก old_data_row อีกที
    # ถ้า s_time/e_time_to_use_from_payload มีค่า ก็จะใช้ค่านั้นตอน Insert ใหม่
    # ถ้าไม่มี ก็จะใช้ s_time/e_time จาก old_data_row

    default_username = 'WebAppUser_GanttEdit'
    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            print("ERROR: Database connection failed in update_gantt_task_schedule")
            return jsonify({"error": "Database connection could not be established"}), 503

        cursor = conn.cursor()
        conn.autocommit = False  # เริ่ม Transaction Control แบบ Manual

        # 1. ดึงข้อมูล "ที่ไม่ใช่ PK" และ s_time, e_time ของแถวเดิมมาเก็บไว้
        sql_select_old_data = """
            SELECT size, ton, protime, htime, description, username, 
                   approve, approveby, approvedate, status, complete, 
                   s_time, e_time, bl_grade, rev 
            FROM dbo.production_planDev
            WHERE machine = ? AND station = ? AND material_code = ? AND postingdate = ? AND shift = ?
        """
        print(f"Executing SELECT for old data with PKs: {original_pks}")
        cursor.execute(sql_select_old_data,
                       original_pks['machine'], original_pks['station'],
                       original_pks['material_code'], original_pks['postingdate'],
                       original_pks['shift'])
        old_data_row = cursor.fetchone()
        print(f"Old data row fetched: {old_data_row}")

        if not old_data_row:
            conn.rollback()  # ไม่จำเป็นถ้ายังไม่ได้ทำ Operation อื่น แต่ใส่ไว้ก็ไม่เสียหาย
            print("ERROR: Original task not found to update with given PKs.")
            return jsonify({"error": "Original task not found. It might have been deleted or changed."}), 404

        # กำหนด s_time, e_time สำหรับ Record ใหม่
        # ถ้า Frontend ส่ง s_time_to_use/e_time_to_use มา (เช่น ผู้ใช้แก้ไขเวลาใน Gantt ที่ละเอียด) ก็ใช้ค่านั้น
        # ถ้าไม่ ให้ใช้ค่าเดิมจาก old_data_row (ถ้ามี)
        # ถ้า old_data_row ก็ไม่มี (เช่น เป็น Task 'หยุดผลิต') ก็อาจจะต้องใส่ Default หรือ NULL
        s_time_for_new_record = s_time_to_use_from_payload if s_time_to_use_from_payload and str(
            s_time_to_use_from_payload).strip() else (old_data_row.s_time if old_data_row.s_time else None)
        e_time_for_new_record = e_time_to_use_from_payload if e_time_to_use_from_payload and str(
            e_time_to_use_from_payload).strip() else (old_data_row.e_time if old_data_row.e_time else None)
        print(f"s_time_for_new_record: '{s_time_for_new_record}', e_time_for_new_record: '{e_time_for_new_record}'")

        # 2. ลบแถวเดิม
        sql_delete_old = """
            DELETE FROM dbo.production_planDev
            WHERE machine = ? AND station = ? AND material_code = ? AND postingdate = ? AND shift = ?
        """
        print(f"Executing DELETE for old data with PKs: {original_pks}")
        cursor.execute(sql_delete_old,
                       original_pks['machine'], original_pks['station'],
                       original_pks['material_code'], original_pks['postingdate'],
                       original_pks['shift'])
        print(f"Rows deleted: {cursor.rowcount}")

        if cursor.rowcount == 0:
            conn.rollback()
            print(
                "ERROR: Failed to delete original task record (rowcount 0 after successful select). This should not happen.")
            return jsonify({"error": "Failed to delete original task record. Concurrent modification?"}), 500

        # 3. Insert แถวใหม่
        sql_insert_new = """
            INSERT INTO dbo.production_planDev (
                machine, station, postingdate, size, ton,
                protime, htime, description, change, username,
                material_code, approve, approveby, approvedate, status,
                shift, complete, s_time, e_time, bl_grade, rev
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, GETDATE(), ?, ?, NULL, NULL, NULL, ?, ?, ?, ?, ?, ?, NULL)
        """
        # ค่าที่จะ Insert (ตรวจสอบลำดับให้ตรงกับ ? ใน SQL)
        insert_params = (
            final_target_machine, original_pks['station'], final_new_posting_date,
            old_data_row.size, old_data_row.ton, old_data_row.protime, old_data_row.htime,
            old_data_row.description, default_username, original_pks['material_code'],
            # approve, approveby, approvedate (เป็น NULL ใน SQL)
            old_data_row.status,  # หรือ status ใหม่ถ้ามีการส่งมา
            original_pks['shift'],
            old_data_row.complete,  # หรือ complete ใหม่ถ้ามีการส่งมา
            s_time_for_new_record,
            e_time_for_new_record,
            old_data_row.bl_grade
        )
        print(f"Preparing to INSERT new record with params: {insert_params}")
        cursor.execute(sql_insert_new, *insert_params)  # ใช้ * เพื่อ unpack tuple

        conn.commit()
        print("INFO: Transaction committed successfully.")
        return jsonify({
            "message": f"Task schedule moved/updated successfully.",
            "new_task_id": f"task_{final_target_machine}_{original_pks['station']}_{original_pks['material_code']}_{final_new_posting_date}_{original_pks['shift']}"
        }), 200

    except pyodbc.Error as db_err:
        if conn: conn.rollback()
        native_error_str = ""
        sql_state = db_err.args[0] if len(db_err.args) > 0 else "Unknown SQLSTATE"
        if len(db_err.args) > 1: native_error_str = str(db_err.args[1])

        print(
            f"DATABASE ERROR CAUGHT: SQLSTATE={sql_state}, Message={native_error_str if native_error_str else str(db_err)}")

        if sql_state == '23000' and "(2627)" in native_error_str:  # Duplicate Key
            return jsonify({
                               "error": "Failed to update: A task with the new schedule (PK combination) already exists."}), 409  # Conflict
        elif sql_state == '22007' and "Conversion failed" in native_error_str:  # Conversion Error
            return jsonify({"error": f"Database conversion error: {native_error_str}"}), 400

        return jsonify({"error": f"Database error occurred. SQLSTATE: {sql_state}"}), 500

    except ValueError as val_err:
        if conn: conn.rollback()
        print(f"VALIDATION ERROR CAUGHT: {val_err}")
        return jsonify({"error": f"Data validation error: {str(val_err)}"}), 400

    except Exception as e:
        if conn: conn.rollback()
        print(f"UNEXPECTED ERROR CAUGHT: {e}")
        traceback.print_exc()
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

    finally:
        if conn:
            conn.autocommit = True  # คืนค่า autocommit (ถ้าจำเป็น)
            conn.close()
            print("INFO: Database connection closed.")
        else:
            print("WARN: conn was None in finally block for update_gantt_task_schedule.")

    # Fallback return, ไม่ควรจะมาถึงตรงนี้ถ้า Logic ถูกต้อง
    print(
        "CRITICAL ERROR: Function update_gantt_task_schedule ended without a return statement inside try/except blocks!")
    return jsonify({"error": "Server encountered an unexpected issue processing the request."}), 500

if __name__ == '__main__':
    # debug=True ทำให้ server restart อัตโนมัติเมื่อมีการแก้ไขโค้ด และแสดง error ที่ละเอียดขึ้น
    # อย่าใช้ debug=True ใน production environment!
    app.run(debug=True)