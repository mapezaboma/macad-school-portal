import os, sqlite3, csv, io
from functools import wraps
from datetime import date, datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file
from werkzeug.security import generate_password_hash, check_password_hash

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "school.db")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "macad-local-change-this-secret")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_db():
    con = db()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS users(
      id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
      password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'Administrator',
      created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS students(
      id INTEGER PRIMARY KEY AUTOINCREMENT, admission_no TEXT UNIQUE NOT NULL,
      first_name TEXT NOT NULL, last_name TEXT NOT NULL, gender TEXT, dob TEXT,
      class_name TEXT, guardian TEXT, phone TEXT, address TEXT,
      status TEXT DEFAULT 'Active', created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS teachers(
      id INTEGER PRIMARY KEY AUTOINCREMENT, staff_no TEXT UNIQUE NOT NULL,
      first_name TEXT NOT NULL, last_name TEXT NOT NULL, subject TEXT,
      phone TEXT, email TEXT, status TEXT DEFAULT 'Active'
    );
    CREATE TABLE IF NOT EXISTS attendance(
      id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER NOT NULL,
      attend_date TEXT NOT NULL, status TEXT NOT NULL, note TEXT,
      UNIQUE(student_id, attend_date),
      FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS fees(
      id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER NOT NULL,
      term TEXT NOT NULL, amount_due REAL NOT NULL DEFAULT 0,
      amount_paid REAL NOT NULL DEFAULT 0, payment_date TEXT, reference TEXT,
      FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS exams(
      id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER NOT NULL,
      subject TEXT NOT NULL, exam_name TEXT NOT NULL, score REAL NOT NULL,
      max_score REAL NOT NULL DEFAULT 100, term TEXT,
      FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE
    );
    """)
    if con.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        con.execute("INSERT INTO users(username,password_hash,role) VALUES(?,?,?)",
                    ("admin", generate_password_hash("admin123"), "Administrator"))
    con.commit()
    con.close()


# Initialize database when Gunicorn imports app.py.
init_db()
def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

@app.context_processor
def inject_globals():
    return {"today": date.today().isoformat(), "current_user": session.get("username"),
            "role": session.get("role")}

def num(v, default=0):
    try: return float(v)
    except (TypeError, ValueError): return default

@app.route("/")
def home():
    return redirect(url_for("dashboard") if "user_id" in session else url_for("login"))

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        username=request.form.get("username","").strip()
        password=request.form.get("password","")
        con=db()
        u=con.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        con.close()
        if u and check_password_hash(u["password_hash"], password):
            session.clear()
            session.update(user_id=u["id"], username=u["username"], role=u["role"])
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.", "danger")
    return render_template("login.html")

@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.get("/dashboard")
@login_required
def dashboard():
    con=db()
    counts={
      "students":con.execute("SELECT COUNT(*) FROM students WHERE status='Active'").fetchone()[0],
      "teachers":con.execute("SELECT COUNT(*) FROM teachers WHERE status='Active'").fetchone()[0],
      "fees_due":con.execute("SELECT COALESCE(SUM(amount_due),0) FROM fees").fetchone()[0],
      "fees_paid":con.execute("SELECT COALESCE(SUM(amount_paid),0) FROM fees").fetchone()[0],
    }
    att=con.execute("""SELECT
      COALESCE(SUM(status='Present'),0) p, COALESCE(SUM(status='Absent'),0) a,
      COALESCE(SUM(status='Late'),0) l, COALESCE(SUM(status='Excused'),0) e
      FROM attendance WHERE attend_date=?""",(date.today().isoformat(),)).fetchone()
    recent=con.execute("""SELECT s.admission_no,s.first_name||' '||s.last_name name,
      f.amount_paid,f.payment_date,f.reference FROM fees f JOIN students s ON s.id=f.student_id
      WHERE f.amount_paid>0 ORDER BY f.id DESC LIMIT 8""").fetchall()
    class_count=con.execute("SELECT COUNT(DISTINCT class_name) FROM students WHERE status='Active'").fetchone()[0]
    con.close()
    counts["classes"]=class_count
    return render_template("dashboard.html", counts=counts, att=att, recent=recent)

@app.route("/students", methods=["GET","POST"])
@login_required
def students():
    con=db()
    if request.method=="POST":
        data=[request.form.get(k,"").strip() for k in
              ["admission_no","first_name","last_name","gender","dob","class_name","guardian","phone","address","status"]]
        if not data[0] or not data[1] or not data[2]:
            flash("Admission number, first name and last name are required.","danger")
        else:
            try:
                con.execute("""INSERT INTO students(admission_no,first_name,last_name,gender,dob,class_name,guardian,phone,address,status)
                    VALUES(?,?,?,?,?,?,?,?,?,?)""",data)
                con.commit(); flash("Student added successfully.","success")
            except sqlite3.IntegrityError: flash("Admission number already exists.","danger")
    q=request.args.get("q","").strip()
    if q:
        rows=con.execute("""SELECT * FROM students WHERE admission_no LIKE ? OR first_name LIKE ?
          OR last_name LIKE ? OR class_name LIKE ? OR guardian LIKE ? ORDER BY id DESC""",
          tuple([f"%{q}%"]*5)).fetchall()
    else: rows=con.execute("SELECT * FROM students ORDER BY id DESC").fetchall()
    con.close()
    return render_template("students.html", students=rows, q=q)

@app.route("/students/edit/<int:id>", methods=["GET","POST"])
@login_required
def edit_student(id):
    con=db()
    if request.method=="POST":
        try:
            con.execute("""UPDATE students SET admission_no=?,first_name=?,last_name=?,gender=?,dob=?,
              class_name=?,guardian=?,phone=?,address=?,status=? WHERE id=?""",
              tuple(request.form.get(k,"").strip() for k in
              ["admission_no","first_name","last_name","gender","dob","class_name","guardian","phone","address","status"])+(id,))
            con.commit(); flash("Student updated successfully.","success"); con.close()
            return redirect(url_for("students"))
        except sqlite3.IntegrityError:
            flash("Admission number already exists.","danger")
    s=con.execute("SELECT * FROM students WHERE id=?", (id,)).fetchone()
    con.close()
    if not s: flash("Student not found.","danger"); return redirect(url_for("students"))
    return render_template("student_edit.html", student=s)

@app.post("/students/delete/<int:id>")
@login_required
def delete_student(id):
    con=db(); con.execute("DELETE FROM students WHERE id=?", (id,)); con.commit(); con.close()
    flash("Student deleted.","success"); return redirect(url_for("students"))

@app.route("/teachers", methods=["GET","POST"])
@login_required
def teachers():
    con=db()
    if request.method=="POST":
        data=[request.form.get(k,"").strip() for k in ["staff_no","first_name","last_name","subject","phone","email","status"]]
        try:
            con.execute("INSERT INTO teachers(staff_no,first_name,last_name,subject,phone,email,status) VALUES(?,?,?,?,?,?,?)",data)
            con.commit(); flash("Teacher added successfully.","success")
        except sqlite3.IntegrityError: flash("Staff number already exists.","danger")
    rows=con.execute("SELECT * FROM teachers ORDER BY id DESC").fetchall()
    con.close(); return render_template("teachers.html",teachers=rows)

@app.post("/teachers/delete/<int:id>")
@login_required
def delete_teacher(id):
    con=db(); con.execute("DELETE FROM teachers WHERE id=?", (id,)); con.commit(); con.close()
    flash("Teacher deleted.","success"); return redirect(url_for("teachers"))

@app.route("/attendance", methods=["GET","POST"])
@login_required
def attendance():
    con=db(); selected_date=request.values.get("attend_date",date.today().isoformat())
    if request.method=="POST":
        for s in con.execute("SELECT id FROM students WHERE status='Active'").fetchall():
            st=request.form.get(f"status_{s['id']}","Present")
            note=request.form.get(f"note_{s['id']}","").strip()
            if st not in ("Present","Absent","Late","Excused"): st="Present"
            con.execute("""INSERT INTO attendance(student_id,attend_date,status,note) VALUES(?,?,?,?)
              ON CONFLICT(student_id,attend_date) DO UPDATE SET status=excluded.status,note=excluded.note""",
              (s["id"],selected_date,st,note))
        con.commit(); flash("Attendance saved.","success")
    rows=con.execute("""SELECT s.*,COALESCE(a.status,'Present') att_status,COALESCE(a.note,'') note
      FROM students s LEFT JOIN attendance a ON a.student_id=s.id AND a.attend_date=?
      WHERE s.status='Active' ORDER BY s.class_name,s.last_name""",(selected_date,)).fetchall()
    con.close(); return render_template("attendance.html",students=rows,selected_date=selected_date)

@app.route("/fees", methods=["GET","POST"])
@login_required
def fees():
    con=db()
    if request.method=="POST":
        due=max(0,num(request.form.get("amount_due")))
        paid=max(0,num(request.form.get("amount_paid")))
        if paid>due and due>0: flash("Amount paid cannot exceed amount due for a transaction.","danger")
        else:
            con.execute("""INSERT INTO fees(student_id,term,amount_due,amount_paid,payment_date,reference)
              VALUES(?,?,?,?,?,?)""",(request.form["student_id"],request.form["term"].strip(),due,paid,
              request.form.get("payment_date") or date.today().isoformat(),request.form.get("reference","").strip()))
            con.commit(); flash("Fee transaction recorded.","success")
    rows=con.execute("""SELECT f.*,s.admission_no,s.first_name||' '||s.last_name name,
      (f.amount_due-f.amount_paid) balance FROM fees f JOIN students s ON s.id=f.student_id ORDER BY f.id DESC""").fetchall()
    students=con.execute("SELECT id,admission_no,first_name,last_name FROM students WHERE status='Active' ORDER BY last_name").fetchall()
    con.close(); return render_template("fees.html",fees=rows,students=students)

@app.post("/fees/delete/<int:id>")
@login_required
def delete_fee(id):
    con=db(); con.execute("DELETE FROM fees WHERE id=?", (id,)); con.commit(); con.close()
    flash("Fee transaction deleted.","success"); return redirect(url_for("fees"))

@app.route("/exams", methods=["GET","POST"])
@login_required
def exams():
    con=db()
    if request.method=="POST":
        score=num(request.form.get("score"),-1); maximum=num(request.form.get("max_score"),100)
        if score<0 or maximum<=0 or score>maximum: flash("Enter a valid score and maximum score.","danger")
        else:
            con.execute("""INSERT INTO exams(student_id,subject,exam_name,score,max_score,term)
              VALUES(?,?,?,?,?,?)""",(request.form["student_id"],request.form["subject"].strip(),
              request.form["exam_name"].strip(),score,maximum,request.form.get("term","").strip()))
            con.commit(); flash("Exam result saved.","success")
    rows=con.execute("""SELECT e.*,s.admission_no,s.first_name||' '||s.last_name name,
      ROUND((e.score/e.max_score)*100,1) percent FROM exams e JOIN students s ON s.id=e.student_id ORDER BY e.id DESC""").fetchall()
    students=con.execute("SELECT id,admission_no,first_name,last_name FROM students WHERE status='Active' ORDER BY last_name").fetchall()
    con.close(); return render_template("exams.html",exams=rows,students=students)

@app.post("/exams/delete/<int:id>")
@login_required
def delete_exam(id):
    con=db(); con.execute("DELETE FROM exams WHERE id=?", (id,)); con.commit(); con.close()
    flash("Result deleted.","success"); return redirect(url_for("exams"))

@app.get("/reports")
@login_required
def reports():
    con=db()
    classes=con.execute("""SELECT COALESCE(NULLIF(class_name,''),'Unassigned') class_name,COUNT(*) n
      FROM students WHERE status='Active' GROUP BY class_name ORDER BY class_name""").fetchall()
    balances=con.execute("""SELECT s.admission_no,s.first_name||' '||s.last_name name,
      COALESCE(SUM(f.amount_due),0) due,COALESCE(SUM(f.amount_paid),0) paid,
      COALESCE(SUM(f.amount_due-f.amount_paid),0) balance FROM students s LEFT JOIN fees f ON f.student_id=s.id
      GROUP BY s.id ORDER BY balance DESC""").fetchall()
    performance=con.execute("""SELECT COALESCE(NULLIF(s.class_name,''),'Unassigned') class_name,
      ROUND(AVG((e.score/e.max_score)*100),1) avg_score,COUNT(e.id) entries
      FROM exams e JOIN students s ON s.id=e.student_id GROUP BY s.class_name ORDER BY s.class_name""").fetchall()
    con.close(); return render_template("reports.html",classes=classes,balances=balances,performance=performance)

@app.get("/reports/export/students.csv")
@login_required
def export_students():
    con=db(); rows=con.execute("SELECT admission_no,first_name,last_name,gender,dob,class_name,guardian,phone,address,status FROM students ORDER BY admission_no").fetchall(); con.close()
    out=io.StringIO(); w=csv.writer(out); w.writerow(rows[0].keys() if rows else ["admission_no","first_name","last_name","gender","dob","class_name","guardian","phone","address","status"])
    for r in rows: w.writerow(list(r))
    return send_file(io.BytesIO(out.getvalue().encode()),mimetype="text/csv",as_attachment=True,download_name="students.csv")

@app.get("/reports/export/fees.csv")
@login_required
def export_fees():
    con=db(); rows=con.execute("""SELECT s.admission_no,s.first_name||' '||s.last_name student,f.term,
      f.amount_due,f.amount_paid,(f.amount_due-f.amount_paid) balance,f.payment_date,f.reference
      FROM fees f JOIN students s ON s.id=f.student_id ORDER BY f.id DESC""").fetchall(); con.close()
    out=io.StringIO(); w=csv.writer(out); w.writerow(["Admission","Student","Term","Amount Due","Amount Paid","Balance","Date","Reference"])
    for r in rows: w.writerow(list(r))
    return send_file(io.BytesIO(out.getvalue().encode()),mimetype="text/csv",as_attachment=True,download_name="fees.csv")

@app.get("/student/<int:id>/report")
@login_required
def student_report(id):
    con=db(); s=con.execute("SELECT * FROM students WHERE id=?",(id,)).fetchone()
    if not s: con.close(); flash("Student not found.","danger"); return redirect(url_for("students"))
    results=con.execute("""SELECT *,ROUND(score/max_score*100,1) percent FROM exams WHERE student_id=? ORDER BY term,subject,exam_name""",(id,)).fetchall()
    fees=con.execute("""SELECT *,amount_due-amount_paid balance FROM fees WHERE student_id=? ORDER BY id DESC""",(id,)).fetchall()
    att=con.execute("""SELECT status,COUNT(*) n FROM attendance WHERE student_id=? GROUP BY status""",(id,)).fetchall()
    con.close()
    return render_template("student_report.html",student=s,results=results,fees=fees,att=att)

@app.get("/api/summary")
@login_required
def api_summary():
    con=db()
    data=con.execute("SELECT COALESCE(NULLIF(class_name,''),'Unassigned') class_name,COUNT(*) count FROM students WHERE status='Active' GROUP BY class_name ORDER BY class_name").fetchall()
    con.close(); return jsonify([dict(x) for x in data])

@app.route("/settings",methods=["GET","POST"])
@login_required
def settings():
    if request.method=="POST":
        old=request.form.get("current_password",""); new=request.form.get("new_password","")
        if len(new)<6: flash("New password must be at least 6 characters.","danger")
        else:
            con=db(); u=con.execute("SELECT * FROM users WHERE id=?",(session["user_id"],)).fetchone()
            if not check_password_hash(u["password_hash"],old): flash("Current password is incorrect.","danger")
            else:
                con.execute("UPDATE users SET password_hash=? WHERE id=?",(generate_password_hash(new),session["user_id"]))
                con.commit(); flash("Password changed successfully.","success")
            con.close()
    return render_template("settings.html")

@app.get("/settings/backup")
@login_required
def backup():
    if os.path.exists(DB):
        return send_file(DB,as_attachment=True,download_name="macad_school_backup.sqlite")
    flash("Database does not exist yet.","danger"); return redirect(url_for("settings"))

@app.get("/health")
def health():
    return jsonify(status="ok", application="MAPEZA ACADEMY - MACAD")

if __name__=="__main__":
    init_db()
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)),debug=False)
