from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date
import pymysql

app = Flask(__name__)
app.secret_key = 'bristol_events_secret_key'

def get_db_connection():
    connection = pymysql.connect(
        host='localhost',
        user='root',
        password='Haseeba@7861',
        database='bristol_events'
    )
    return connection

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/events')
def events():
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    category = request.args.get('category', '')
    if category:
        cursor.execute('''SELECT events.*, venues.venue_name 
            FROM events JOIN venues ON events.venue_id = venues.venue_id
            WHERE events.category = %s''', (category,))
    else:
        cursor.execute('''SELECT events.*, venues.venue_name 
            FROM events JOIN venues ON events.venue_id = venues.venue_id''')
    events = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('events.html', events=events, selected_category=category)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        email = request.form['email']
        password = request.form['password']
        is_student = 1 if 'is_student' in request.form else 0
        hashed_password = generate_password_hash(password)
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('INSERT INTO users (first_name, last_name, email, password, is_student) VALUES (%s, %s, %s, %s, %s)',
                         (first_name, last_name, email, hashed_password, is_student))
            conn.commit()
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        except pymysql.err.IntegrityError:
            flash('Email already exists. Please use a different email.', 'error')
        finally:
            cursor.close()
            conn.close()
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        cursor.execute('SELECT * FROM users WHERE email = %s', (email,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['user_id']
            session['user_name'] = user['first_name']
            session['is_admin'] = user['is_admin']
            flash('Welcome back ' + user['first_name'] + '!', 'success')
            return redirect(url_for('home'))
        else:
            flash('Invalid email or password.', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('home'))

@app.route('/book/<int:event_id>', methods=['GET', 'POST'])
def book(event_id):
    if 'user_id' not in session:
        flash('Please login to book an event.', 'error')
        return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    cursor.execute('SELECT events.*, venues.venue_name FROM events JOIN venues ON events.venue_id = venues.venue_id WHERE event_id = %s', (event_id,))
    event = cursor.fetchone()
    if request.method == 'POST':
        num_tickets = int(request.form['num_tickets'])
        total_price = event['ticket_price'] * num_tickets
        today = date.today()
        days_until_event = (event['event_date'] - today).days
        discount = 0
        if days_until_event >= 50:
            discount = 20
        elif days_until_event >= 35:
            discount = 15
        elif days_until_event >= 25:
            discount = 10
        elif days_until_event >= 15:
            discount = 5
        if discount > 0:
            total_price = total_price - (total_price * discount / 100)
        cursor2 = conn.cursor(pymysql.cursors.DictCursor)
        cursor2.execute('SELECT is_student FROM users WHERE user_id = %s', (session['user_id'],))
        user = cursor2.fetchone()
        if user['is_student']:
            total_price = total_price - (total_price * 10 / 100)
        if num_tickets > event['tickets_remaining']:
            flash('Not enough tickets available.', 'error')
        else:
            insert_cursor = conn.cursor()
            insert_cursor.execute('INSERT INTO bookings (user_id, event_id, num_tickets, total_price) VALUES (%s, %s, %s, %s)',
                         (session['user_id'], event_id, num_tickets, total_price))
            cursor.execute('UPDATE events SET tickets_remaining = tickets_remaining - %s WHERE event_id = %s',
                         (num_tickets, event_id))
            conn.commit()
            new_booking_id = insert_cursor.lastrowid
            insert_cursor.close()
            cursor.close()
            conn.close()
            flash('Booking confirmed!', 'success')
            return redirect(url_for('booking_receipt', booking_id=new_booking_id))
    cursor.close()
    conn.close()
    return render_template('book.html', event=event)

@app.route('/booking-receipt/<int:booking_id>')
def booking_receipt(booking_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    print('Looking for booking_id:', booking_id)
    cursor.execute('''SELECT bookings.*, events.event_name, events.event_date,
        events.ticket_price, venues.venue_name,
        users.first_name, users.last_name, users.email
        FROM bookings
        JOIN events ON bookings.event_id = events.event_id
        JOIN venues ON events.venue_id = venues.venue_id
        JOIN users ON bookings.user_id = users.user_id
        WHERE bookings.booking_id = %s''', (booking_id,))
    booking = cursor.fetchone()
    print('Booking found:', booking)
    cursor.close()
    conn.close()
    return render_template('receipt.html', booking=booking)
@app.route('/my-bookings')
def my_bookings():
    if 'user_id' not in session:
        flash('Please login to view your bookings.', 'error')
        return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    cursor.execute('''SELECT bookings.*, events.event_name, events.event_date,
        venues.venue_name
        FROM bookings
        JOIN events ON bookings.event_id = events.event_id
        JOIN venues ON events.venue_id = venues.venue_id
        WHERE bookings.user_id = %s
        ORDER BY bookings.booking_date DESC''', (session['user_id'],))
    bookings = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('my_bookings.html', bookings=bookings)
@app.route('/cancel-booking/<int:booking_id>')
def cancel_booking(booking_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    cursor.execute('SELECT * FROM bookings WHERE booking_id = %s AND user_id = %s',
                   (booking_id, session['user_id']))
    booking = cursor.fetchone()
    if booking and booking['status'] == 'confirmed':
        cursor.execute('UPDATE bookings SET status = %s WHERE booking_id = %s',
                       ('cancelled', booking_id))
        cursor.execute('UPDATE events SET tickets_remaining = tickets_remaining + %s WHERE event_id = %s',
                       (booking['num_tickets'], booking['event_id']))
        conn.commit()
        flash('Booking cancelled successfully.', 'success')
    else:
        flash('Booking not found or already cancelled.', 'error')
    cursor.close()
    conn.close()
    return redirect(url_for('my_bookings'))
@app.route('/admin')
def admin():
    if 'user_id' not in session or not session.get('is_admin'):
        flash('Access denied.', 'error')
        return redirect(url_for('home'))
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    cursor.execute('SELECT * FROM events JOIN venues ON events.venue_id = venues.venue_id')
    events = cursor.fetchall()
    cursor.execute('SELECT * FROM users')
    users = cursor.fetchall()
    cursor.execute('SELECT COUNT(*) as total_bookings FROM bookings WHERE status = %s', ('confirmed',))
    total_bookings = cursor.fetchone()
    cursor.execute('SELECT SUM(total_price) as total_revenue FROM bookings WHERE status = %s', ('confirmed',))
    total_revenue = cursor.fetchone()
    cursor.close()
    conn.close()
    return render_template('admin.html', events=events, users=users, total_bookings=total_bookings, total_revenue=total_revenue)
@app.route('/admin/add-event', methods=['GET', 'POST'])
def add_event():
    if 'user_id' not in session or not session.get('is_admin'):
        return redirect(url_for('home'))
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    cursor.execute('SELECT * FROM venues')
    venues = cursor.fetchall()
    if request.method == 'POST':
        event_name = request.form['event_name']
        description = request.form['description']
        category = request.form['category']
        event_date = request.form['event_date']
        start_time = request.form['start_time']
        ticket_price = request.form['ticket_price']
        total_tickets = request.form['total_tickets']
        last_booking_date = request.form['last_booking_date']
        venue_id = request.form['venue_id']
        cursor.execute('''INSERT INTO events (event_name, description, category, event_date, 
            start_time, ticket_price, total_tickets, tickets_remaining, last_booking_date, venue_id) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''',
            (event_name, description, category, event_date, start_time, 
             ticket_price, total_tickets, total_tickets, last_booking_date, venue_id))
        conn.commit()
        cursor.close()
        conn.close()
        flash('Event added successfully!', 'success')
        return redirect(url_for('admin'))
    cursor.close()
    conn.close()
    return render_template('add_event.html', venues=venues)
@app.route('/admin/delete-event/<int:event_id>')
def delete_event(event_id):
    if 'user_id' not in session or not session.get('is_admin'):
        return redirect(url_for('home'))
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM events WHERE event_id = %s', (event_id,))
    conn.commit()
    cursor.close()
    conn.close()
    flash('Event deleted successfully!', 'success')
    return redirect(url_for('admin'))

@app.route('/admin/edit-event/<int:event_id>', methods=['GET', 'POST'])
def edit_event(event_id):
    if 'user_id' not in session or not session.get('is_admin'):
        return redirect(url_for('home'))
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    cursor.execute('SELECT * FROM venues')
    venues = cursor.fetchall()
    cursor.execute('SELECT * FROM events WHERE event_id = %s', (event_id,))
    event = cursor.fetchone()
    if request.method == 'POST':
        event_name = request.form['event_name']
        description = request.form['description']
        category = request.form['category']
        event_date = request.form['event_date']
        start_time = request.form['start_time']
        ticket_price = request.form['ticket_price']
        total_tickets = request.form['total_tickets']
        last_booking_date = request.form['last_booking_date']
        venue_id = request.form['venue_id']
        cursor.execute('''UPDATE events SET event_name=%s, description=%s, category=%s,
            event_date=%s, start_time=%s, ticket_price=%s, total_tickets=%s,
            last_booking_date=%s, venue_id=%s WHERE event_id=%s''',
            (event_name, description, category, event_date, start_time,
             ticket_price, total_tickets, last_booking_date, venue_id, event_id))
        conn.commit()
        cursor.close()
        conn.close()
        flash('Event updated successfully!', 'success')
        return redirect(url_for('admin'))
    cursor.close()
    conn.close()
    return render_template('edit_event.html', event=event, venues=venues)
@app.route('/update-password', methods=['GET', 'POST'])
def update_password():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        cursor.execute('SELECT * FROM users WHERE user_id = %s', (session['user_id'],))
        user = cursor.fetchone()
        if not check_password_hash(user['password'], current_password):
            flash('Current password is incorrect.', 'error')
        elif new_password != confirm_password:
            flash('New passwords do not match.', 'error')
        else:
            hashed_password = generate_password_hash(new_password)
            cursor.execute('UPDATE users SET password = %s WHERE user_id = %s',
                         (hashed_password, session['user_id']))
            conn.commit()
            flash('Password updated successfully!', 'success')
        cursor.close()
        conn.close()
    return render_template('update_password.html')
@app.route('/admin/reports')
def admin_reports():
    if 'user_id' not in session or not session.get('is_admin'):
        return redirect(url_for('home'))
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    
    # Revenue and bookings per event
    cursor.execute('''SELECT events.event_name, events.event_date,
        venues.venue_name,
        COUNT(bookings.booking_id) as total_bookings,
        SUM(bookings.total_price) as total_revenue,
        events.total_tickets,
        events.tickets_remaining
        FROM events
        LEFT JOIN bookings ON events.event_id = bookings.event_id 
        AND bookings.status = "confirmed"
        LEFT JOIN venues ON events.venue_id = venues.venue_id
        GROUP BY events.event_id
        ORDER BY total_revenue DESC''')
    event_reports = cursor.fetchall()
    
    cursor.close()
    conn.close()
    return render_template('admin_reports.html', event_reports=event_reports)
@app.route('/waiting-list/<int:event_id>')
def join_waiting_list(event_id):
    if 'user_id' not in session:
        flash('Please login to join the waiting list.', 'error')
        return redirect(url_for('login'))
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    cursor.execute('SELECT * FROM waiting_list WHERE user_id = %s AND event_id = %s',
                   (session['user_id'], event_id))
    existing = cursor.fetchone()
    if existing:
        flash('You are already on the waiting list for this event.', 'error')
    else:
        cursor.execute('INSERT INTO waiting_list (user_id, event_id) VALUES (%s, %s)',
                       (session['user_id'], event_id))
        conn.commit()
        flash('You have been added to the waiting list!', 'success')
    cursor.close()
    conn.close()
    return redirect(url_for('events'))

if __name__ == '__main__':
    app.run(debug=True)