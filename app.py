from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import datetime
from flask_mail import Mail, Message

app = Flask(__name__)

import os
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'default_secret_key')


# Email configuration
app.config['SEND_EMAILS'] = True
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER')

mail = Mail(app)

DATABASE = 'cloudreserve.db'

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def build_calendar(year, month, all_reservations):
    """Build a calendar grid for the given month/year.
    all_reservations must be a list of plain dicts (not sqlite3.Row objects).
    """
    first_day = datetime.date(year, month, 1)
    last_day = (first_day.replace(day=28) + datetime.timedelta(days=4)).replace(day=1) - datetime.timedelta(days=1)

    calendar = []
    week = []

    # Fill leading empty days (Sunday-start)
    for _ in range((first_day.weekday() + 1) % 7):
        week.append(None)

    for d in range(1, last_day.day + 1):
        date_obj = datetime.date(year, month, d)
        date_str = date_obj.strftime('%Y-%m-%d')
        bookings = [r for r in all_reservations if r['date'] == date_str]
        week.append({'day': d, 'date': date_str, 'bookings': bookings})
        if len(week) == 7:
            calendar.append(week)
            week = []

    if week:
        while len(week) < 7:
            week.append(None)
        calendar.append(week)

    return calendar


def get_calendar_nav(year, month):
    """Return prev/next month+year values and the full month name."""
    prev_month = month - 1 if month > 1 else 12
    prev_year  = year     if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year  = year     if month < 12 else year + 1
    month_name = datetime.date(year, month, 1).strftime('%B')
    return prev_month, prev_year, next_month, next_year, month_name


@app.route('/')
def index():
    return render_template('login.html')


@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']
    db = get_db()
    staff = db.execute(
        'SELECT * FROM staff WHERE username = ? AND password = ?',
        (username, password)
    ).fetchone()
    if staff:
        session['staff_id'] = staff['id']
        return redirect(url_for('dashboard'))
    else:
        flash('Invalid login!')
        return redirect(url_for('index'))


@app.route('/dashboard')
def dashboard():
    if 'staff_id' not in session:
        return redirect(url_for('index'))

    db = get_db()
    today_str = datetime.date.today().strftime('%Y-%m-%d')

    today_count = db.execute(
        "SELECT COUNT(*) FROM reservation WHERE date = ?", (today_str,)
    ).fetchone()[0]

    total_guests = db.execute(
        "SELECT COALESCE(SUM(group_size), 0) FROM reservation"
    ).fetchone()[0]

    pending_count = db.execute(
        "SELECT COUNT(*) FROM reservation WHERE status IN ('pending', 'queued')"
    ).fetchone()[0]

    upcoming_reservations = db.execute(
        "SELECT * FROM reservation WHERE date >= ? ORDER BY date, time LIMIT 5",
        (today_str,)
    ).fetchall()

    return render_template('dashboard.html',
        today_count=today_count,
        total_guests=total_guests,
        pending_count=pending_count,
        upcoming_reservations=upcoming_reservations
    )


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


@app.route('/reserve', methods=['GET', 'POST'])
def reserve():
    if 'staff_id' not in session:
        return redirect(url_for('index'))
    error = None
    alt_slots = None
    queue_count = 0
    date = request.form.get('date') if request.method == 'POST' else None
    time = request.form.get('time') if request.method == 'POST' else None
    db = get_db()
    if request.method == 'POST':
        guest_name = request.form['guest_name']
        email      = request.form['email']
        contact    = request.form['contact']
        date       = request.form['date']
        group_size = request.form['group_size']
        alt_time   = request.form.get('alt_time')
        join_queue = request.form.get('join_queue')
        if alt_time:
            time = alt_time
        exists = db.execute(
            'SELECT * FROM reservation WHERE date = ? AND time = ?',
            (date, time)
        ).fetchone()
        if exists and not join_queue:
            all_times = [f"{h:02d}:{m:02d}" for h in range(10, 22) for m in (0, 30)]
            booked_times = [r['time'] for r in db.execute(
                'SELECT time FROM reservation WHERE date = ?', (date,)
            ).fetchall()]
            alt_slots = [t for t in all_times if t not in booked_times]
            if time in alt_slots:
                alt_slots.remove(time)
            def time_diff(t):
                h, m = map(int, t.split(':'))
                req_h, req_m = map(int, time.split(':'))
                return abs((h * 60 + m) - (req_h * 60 + req_m))
            alt_slots = sorted(alt_slots, key=time_diff)[:5]
            queue_count = db.execute(
                'SELECT COUNT(*) FROM reservation WHERE date = ? AND time = ? AND status = ?',
                (date, time, 'queued')
            ).fetchone()[0]
            return render_template('reserve.html',
                error='Table not available. Please select another slot or join queue.',
                alt_slots=alt_slots, queue_count=queue_count, date=date, time=time)
        elif join_queue:
            db.execute(
                'INSERT INTO reservation (guest_name, email, contact, date, time, group_size, status, staff_id) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                (guest_name, email, contact, date, time, group_size, 'queued', session['staff_id'])
            )
            db.commit()
            db.execute(
                'INSERT INTO queue (reservation_id, status) VALUES (?, ?)',
                (db.execute('SELECT last_insert_rowid()').fetchone()[0], 'waiting')
            )
            db.commit()
            return render_template('confirmation.html', message='Added to queue and email sent!')
        else:
            db.execute(
                'INSERT INTO reservation (guest_name, email, contact, date, time, group_size, status, staff_id) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                (guest_name, email, contact, date, time, group_size, 'confirmed', session['staff_id'])
            )
            db.commit()
            if app.config['SEND_EMAILS']:
                try:
                    msg = Message(
                        subject='CloudReserve Reservation Confirmation',
                        recipients=[email],
                        body=(
                            f"Dear {guest_name},\n\n"
                            f"Your reservation for {date} at {time} for {group_size} people has been confirmed.\n\n"
                            f"Thank you for choosing CloudReserve!"
                        )
                    )
                    mail.send(msg)
                except Exception as e:
                    print('Email sending failed:', e)
            return render_template('confirmation.html', message='Reservation confirmed and email sent!')
    return render_template('reserve.html', error=error)


@app.route('/view_edit', methods=['GET', 'POST'])
def view_edit():
    if 'staff_id' not in session:
        return redirect(url_for('index'))

    reservation = None
    error       = None
    db          = get_db()

    # ── FIX: convert all Row objects to plain dicts ──
    # This is required so Jinja's tojson filter can serialize
    # the bookings list when rendering the calendar day onclick data.
    all_reservations = [dict(r) for r in db.execute(
        'SELECT * FROM reservation ORDER BY date, time'
    ).fetchall()]

    # Month navigation — read from query string, default to today
    today = datetime.date.today()
    try:
        month = int(request.args.get('month', today.month))
        year  = int(request.args.get('year',  today.year))
    except ValueError:
        month, year = today.month, today.year

    if month < 1:
        month, year = 12, year - 1
    elif month > 12:
        month, year = 1, year + 1

    prev_month, prev_year, next_month, next_year, month_name = get_calendar_nav(year, month)
    # all_reservations is already dicts — pass directly
    calendar = build_calendar(year, month, all_reservations)

    if request.method == 'POST':
        guest_name = request.form['guest_name']
        row = db.execute(
            'SELECT * FROM reservation WHERE guest_name = ?', (guest_name,)
        ).fetchone()
        # ── FIX: convert reservation Row to plain dict ──
        reservation = dict(row) if row else None
        if not reservation:
            error = 'Reservation not found.'

    return render_template('view_edit.html',
        reservation=reservation,
        error=error,
        all_reservations=all_reservations,
        calendar=calendar,
        month=month,
        year=year,
        month_name=month_name,
        prev_month=prev_month,
        prev_year=prev_year,
        next_month=next_month,
        next_year=next_year
    )


@app.route('/edit_reservation', methods=['POST'])
def edit_reservation():
    if 'staff_id' not in session:
        return redirect(url_for('index'))
    reservation_id = request.form['id']
    email      = request.form['email']
    contact    = request.form['contact']
    date       = request.form['date']
    time       = request.form['time']
    group_size = request.form['group_size']
    db = get_db()
    old_res = db.execute('SELECT * FROM reservation WHERE id = ?', (reservation_id,)).fetchone()
    db.execute(
        'UPDATE reservation SET email = ?, contact = ?, date = ?, time = ?, group_size = ? WHERE id = ?',
        (email, contact, date, time, group_size, reservation_id)
    )
    db.commit()
    if old_res and (old_res['date'] != date or old_res['time'] != time):
        queued = db.execute(
            'SELECT * FROM reservation WHERE date = ? AND time = ? AND status = ? ORDER BY id ASC LIMIT 1',
            (old_res['date'], old_res['time'], 'queued')
        ).fetchone()
        if queued:
            db.execute('UPDATE reservation SET status = ? WHERE id = ?', ('confirmed', queued['id']))
            db.execute('UPDATE queue SET status = ? WHERE reservation_id = ?', ('notified', queued['id']))
            db.commit()
            if app.config['SEND_EMAILS']:
                try:
                    msg = Message(
                        subject='CloudReserve Reservation Now Available',
                        recipients=[queued['email']],
                        body=(
                            f"Dear {queued['guest_name']},\n\n"
                            f"A slot for your reservation on {old_res['date']} at {old_res['time']} "
                            f"is now available and has been confirmed for you.\n\n"
                            f"Thank you for waiting in the queue!\n\nCloudReserve Team"
                        )
                    )
                    mail.send(msg)
                except Exception as e:
                    print('Email sending failed:', e)
    reservation = db.execute(
        'SELECT guest_name FROM reservation WHERE id = ?', (reservation_id,)
    ).fetchone()
    guest_name = reservation['guest_name'] if reservation else 'Guest'
    if app.config['SEND_EMAILS']:
        try:
            msg = Message(
                subject='CloudReserve Reservation Updated',
                recipients=[email],
                body=(
                    f"Dear {guest_name},\n\n"
                    f"Your reservation has been updated.\n\n"
                    f"New Schedule: {date} at {time} for {group_size} people.\n\n"
                    f"Thank you for choosing CloudReserve!"
                )
            )
            mail.send(msg)
        except Exception as e:
            print('Email sending failed:', e)
    return render_template(
        'confirmation.html',
        message=f'Reservation updated and email sent! New schedule: {date} at {time}.'
    )


@app.route('/delete_reservation', methods=['POST'])
def delete_reservation():
    if 'staff_id' not in session:
        return redirect(url_for('index'))
    reservation_id = request.form['id']
    db = get_db()
    reservation = db.execute(
        'SELECT * FROM reservation WHERE id = ?', (reservation_id,)
    ).fetchone()
    if reservation:
        date = reservation['date']
        time = reservation['time']
        if app.config['SEND_EMAILS']:
            try:
                msg = Message(
                    subject='CloudReserve Reservation Cancelled',
                    recipients=[reservation['email']],
                    body=(
                        f"Dear {reservation['guest_name']},\n\n"
                        f"Your reservation for {reservation['date']} at {reservation['time']} "
                        f"has been cancelled.\n\n"
                        f"If this was a mistake, please contact us.\n\n"
                        f"Thank you for choosing CloudReserve!"
                    )
                )
                mail.send(msg)
            except Exception as e:
                print('Email sending failed:', e)
        db.execute('DELETE FROM reservation WHERE id = ?', (reservation_id,))
        db.commit()
        queued = db.execute(
            'SELECT * FROM reservation WHERE date = ? AND time = ? AND status = ? ORDER BY id ASC LIMIT 1',
            (date, time, 'queued')
        ).fetchone()
        if queued:
            db.execute('UPDATE reservation SET status = ? WHERE id = ?', ('confirmed', queued['id']))
            db.execute('UPDATE queue SET status = ? WHERE reservation_id = ?', ('notified', queued['id']))
            db.commit()
            if app.config['SEND_EMAILS']:
                try:
                    msg = Message(
                        subject='CloudReserve Reservation Now Available',
                        recipients=[queued['email']],
                        body=(
                            f"Dear {queued['guest_name']},\n\n"
                            f"A slot for your reservation on {date} at {time} is now available "
                            f"and has been confirmed for you.\n\n"
                            f"Thank you for waiting in the queue!\n\nCloudReserve Team"
                        )
                    )
                    mail.send(msg)
                except Exception as e:
                    print('Email sending failed:', e)
    return render_template('confirmation.html', message='Reservation has been cancelled.')


@app.route('/queue', methods=['POST'])
def queue():
    if 'staff_id' not in session:
        return redirect(url_for('index'))
    guest_name = request.form['guest_name']
    email      = request.form['email']
    contact    = request.form['contact']
    date       = request.form['date']
    time       = request.form['time']
    group_size = request.form['group_size']
    db = get_db()
    db.execute(
        'INSERT INTO reservation (guest_name, email, contact, date, time, group_size, status, staff_id) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        (guest_name, email, contact, date, time, group_size, 'queued', session['staff_id'])
    )
    db.commit()
    db.execute(
        'INSERT INTO queue (reservation_id, status) VALUES (?, ?)',
        (db.execute('SELECT last_insert_rowid()').fetchone()[0], 'waiting')
    )
    db.commit()
    return render_template('confirmation.html', message='Added to queue and email sent!')


if __name__ == '__main__':
    app.run(debug=True)