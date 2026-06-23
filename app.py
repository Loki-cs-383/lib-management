from flask import Flask, render_template, request, redirect, url_for, flash
import os
import sqlite3
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Database configuration - uses SQLite in production (Render), MySQL locally
if os.environ.get('RENDER'):  # Render sets this environment variable
    # Production: Use SQLite file on persistent disk
    DB_PATH = os.path.join(os.getenv('RENDER_DISK_PATH', '/tmp'), 'library.db')
    def get_db_connection():
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row  # To mimic DictCursor behavior
        return conn
else:
    # Development: Use MySQL
    import pymysql
    db_config = {
        'host': 'localhost',
        'user': 'root',
        'password': '1234',  # Only used locally - change as needed
        'database': 'library',
        'cursorclass': pymysql.cursors.DictCursor
    }
    def get_db_connection():
        return pymysql.connect(**db_config)

def _execute(cursor, query, params):
    """Execute query with correct placeholder style for SQLite vs MySQL.
    Assumes query uses MySQL-style %s placeholders (as in the original schema).
    For SQLite, converts %s to ? before execution.
    """
    if isinstance(cursor.connection, sqlite3.Connection):
        # SQLite: replace %s with ?
        q = query.replace('%s', '?')
        return cursor.execute(q, params)
    else:
        # MySQL / pymysql: keep %s as-is
        return cursor.execute(query, params)

def init_db():
    """Initialize database with tables if they don't exist"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Create tables (same schema as your schema.sql)
    _execute(cursor, ('''
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(100) NOT NULL,
            email VARCHAR(100) UNIQUE NOT NULL,
            phone VARCHAR(20),
            join_date DATE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    '''), ())

    _execute(cursor, ('''
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title VARCHAR(200) NOT NULL,
            author VARCHAR(100) NOT NULL,
            isbn VARCHAR(20) UNIQUE NOT NULL,
            publication_year YEAR,
            available_copies INT NOT NULL DEFAULT 1,
            total_copies INT NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    '''), ())

    _execute(cursor, ('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INT NOT NULL,
            member_id INT NOT NULL,
            issue_date DATE NOT NULL,
            due_date DATE NOT NULL,
            return_date DATE,
            fine DECIMAL(5,2) DEFAULT 0.00,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (book_id) REFERENCES books(id),
            FOREIGN KEY (member_id) REFERENCES members(id)
        )
    '''), ())

    # Insert sample data only if tables are empty
    _execute(cursor, ('SELECT COUNT(*) FROM members'), ())
    if cursor.fetchone()[0] == 0:
        _execute(cursor, ('''
            INSERT INTO members (name, email, phone, join_date) VALUES
            (%s, %s, %s, %s),
            (%s, %s, %s, %s)
        '''), (
            'John Doe', 'john@example.com', '1234567890', '2023-01-15',
            'Jane Smith', 'jane@example.com', '0987654321', '2023-02-20'
        ))

    _execute(cursor, ('SELECT COUNT(*) FROM books'), ())
    if cursor.fetchone()[0] == 0:
        _execute(cursor, ('''
            INSERT INTO books (title, author, isbn, publication_year, total_copies, available_copies) VALUES
            (%s, %s, %s, %s, %s, %s),
            (%s, %s, %s, %s, %s, %s),
            (%s, %s, %s, %s, %s, %s)
        '''), (
            'The Great Gatsby', 'F. Scott Fitzgerald', '9780743273565', 1925, 3, 3,
            'To Kill a Mockingbird', 'Harper Lee', '9780061120084', 1960, 2, 2,
            '1984', 'George Orwell', '9780451524935', 1949, 4, 4
        ))

    conn.commit()
    conn.close()

# Initialize database when app starts
with app.app_context():
    init_db()

# Helper to convert None to empty string for display (optional)
def _nullsafe(val):
    return '' if val is None else val

# ------------------- Routes -------------------

@app.route('/')
def index():
    return render_template('index.html')

# Books routes
@app.route('/books')
def books():
    conn = get_db_connection()
    cursor = conn.cursor()
    _execute(cursor, ('SELECT * FROM books'), ())
    books = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('books.html', books=books)

@app.route('/books/add', methods=['GET', 'POST'])
def add_book():
    if request.method == 'POST':
        title = request.form['title']
        author = request.form['author']
        isbn = request.form['isbn']
        publication_year = request.form['publication_year']
        total_copies = request.form['total_copies']

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            _execute(cursor, (
                'INSERT INTO books (title, author, isbn, publication_year, total_copies, available_copies) '
                'VALUES (%s, %s, %s, %s, %s, %s)'
            ), (title, author, isbn, publication_year, total_copies, total_copies))
            conn.commit()
            flash('Book added successfully!', 'success')
        except Exception as e:
            conn.rollback()
            flash(f'Error adding book: {str(e)}', 'danger')
        finally:
            cursor.close()
            conn.close()
        return redirect(url_for('books'))

    return render_template('add_book.html')

@app.route('/books/edit/<int:id>', methods=['GET', 'POST'])
def edit_book(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    if request.method == 'POST':
        title = request.form['title']
        author = request.form['author']
        isbn = request.form['isbn']
        publication_year = request.form['publication_year']
        total_copies = request.form['total_copies']

        try:
            # Get current total copies to compute delta
            _execute(cursor, ('SELECT available_copies, total_copies FROM books WHERE id=%s'), (id,))
            book = cursor.fetchone()
            if book:
                diff = int(total_copies) - book['total_copies']
                new_available = book['available_copies'] + diff
                if new_available < 0:
                    new_available = 0

                _execute(cursor, (
                    'UPDATE books SET title=%s, author=%s, isbn=%s, publication_year=%s, total_copies=%s WHERE id=%s'
                ), (title, author, isbn, publication_year, total_copies, id))
                _execute(cursor, ('UPDATE books SET available_copies=%s WHERE id=%s'), (new_available, id))
                conn.commit()
                flash('Book updated successfully!', 'success')
            else:
                flash('Book not found!', 'danger')
        except Exception as e:
            conn.rollback()
            flash(f'Error updating book: {str(e)}', 'danger')
        finally:
            cursor.close()
            conn.close()
        return redirect(url_for('books'))

    # GET request
    _execute(callback, ('SELECT * FROM books WHERE id=%s'), (id,))
    book = cursor.fetchone()
    cursor.close()
    conn.close()
    return render_template('edit_book.html', book=book)

@app.route('/books/delete/<int:id>')
def delete_book(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Check if book is currently issued
        _execute(cursor, ('SELECT COUNT(*) as count FROM transactions WHERE book_id=%s AND return_date IS NULL'), (id,))
        result = cursor.fetchone()
        if result['count'] > 0:
            flash('Cannot delete book that is currently issued!', 'danger')
        else:
            _execute(cursor, ('DELETE FROM books WHERE id=%s'), (id,))
            conn.commit()
            flash('Book deleted successfully!', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'Error deleting book: {str(e)}', 'danger')
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('books'))

# Members routes
@app.route('/members')
def members():
    conn = get_db_connection()
    cursor = conn.cursor()
    _execute(cursor, ('SELECT * FROM members'), ())
    members = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('members.html', members=members)

@app.route('/members/add', methods=['GET', 'POST'])
def add_member():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        join_date = request.form['join_date']

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            _execute(cursor, (
                'INSERT INTO members (name, email, phone, join_date) VALUES (%s, %s, %s, %s)'
            ), (name, email, phone, join_date))
            conn.commit()
            flash('Member added successfully!', 'success')
        except Exception as e:
            conn.rollback()
            flash(f'Error adding member: {str(e)}', 'danger')
        finally:
            cursor.close()
            conn.close()
        return redirect(url_for('members'))

    return render_template('add_member.html')

@app.route('/members/edit/<int:id>', methods=['GET', 'POST'])
def edit_member(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        join_date = request.form['join_date']

        try:
            _execute(cursor, (
                'UPDATE members SET name=%s, email=%s, phone=%s, join_date=%s WHERE id=%s'
            ), (name, email, phone, join_date, id))
            conn.commit()
            flash('Member updated successfully!', 'success')
        except Exception as e:
            conn.rollback()
            flash(f'Error updating member: {str(e)}', 'danger')
        finally:
            cursor.close()
            conn.close()
        return redirect(url_for('members'))

    # GET request
    _execute(cursor, ('SELECT * FROM members WHERE id=%s'), (id,))
    member = cursor.fetchone()
    cursor.close()
    conn.close()
    return render_template('edit_member.html', member=member)

@app.route('/members/delete/<int:id>')
def delete_member(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Check if member has any issued books
        _execute(cursor, ('SELECT COUNT(*) as count FROM transactions WHERE member_id=%s AND return_date IS NULL'), (id,))
        result = cursor.fetchone()
        if result['count'] > 0:
            flash('Cannot delete member who has issued books!', 'danger')
        else:
            _execute(cursor, ('DELETE FROM members WHERE id=%s'), (id,))
            conn.commit()
            flash('Member deleted successfully!', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'Error deleting member: {str(e)}', 'danger')
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('members'))

# Transactions routes
@app.route('/transactions')
def transactions():
    conn = get_db_connection()
    cursor = conn.cursor()
    _execute(cursor, ('''
        SELECT t.id, b.title, m.name, t.issue_date, t.due_date, t.return_date, t.fine
        FROM transactions t
        JOIN books b ON t.book_id = b.id
        JOIN members m ON t.member_id = m.id
        ORDER BY t.issue_date DESC
    '''), ())
    transactions = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('transactions.html', transactions=transactions)

@app.route('/issue_book', methods=['GET', 'POST'])
def issue_book():
    if request.method == 'POST':
        book_id = request.form['book_id']
        member_id = request.form['member_id']
        issue_date = request.form['issue_date']
        # Calculate due date (14 days from issue date)
        issue_date_obj = datetime.strptime(issue_date, '%Y-%m-%d')
        due_date = issue_date_obj + timedelta(days=14)
        due_date_str = due_date.strftime('%Y-%m-%d')

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            # Check book availability
            _execute(cursor, ('SELECT available_copies FROM books WHERE id=%s'), (book_id,))
            book = cursor.fetchone()
            if not book or book['available_copies'] <= 0:
                flash('Book is not available for issue!', 'danger')
                return redirect(url_for('issue_book'))

            # Create transaction
            _execute(cursor, (
                'INSERT INTO transactions (book_id, member_id, issue_date, due_date) VALUES (%s, %s, %s, %s)'
            ), (book_id, member_id, issue_date, due_date_str))
            # Update book available copies
            _execute(cursor, ('UPDATE books SET available_copies = available_copies - 1 WHERE id=%s'), (book_id,))
            conn.commit()
            flash('Book issued successfully!', 'success')
        except Exception as e:
            conn.rollback()
            flash(f'Error issuing book: {str(e)}', 'danger')
        finally:
            cursor.close()
            conn.close()
        return redirect(url_for('transactions'))

    # GET request: show form with available books and members
    conn = get_db_connection()
    cursor = conn.cursor()
    _execute(cursor, ('SELECT id, title FROM books WHERE available_copies > 0'), ())
    books = cursor.fetchall()
    _execute(cursor, ('SELECT id, name FROM members'), ())
    members = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('issue_book.html', books=books, members=members)

@app.route('/return_book/<int:id>', methods=['GET', 'POST'])
def return_book(id):
    if request.method == 'POST':
        return_date = request.form['return_date']

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            # Get transaction details
            _execute(cursor, ('SELECT book_id, due_date FROM transactions WHERE id=%s'), (id,))
            transaction = cursor.fetchone()
            if not transaction:
                flash('Transaction not found!', 'danger')
                return redirect(url_for('transactions'))

            # Calculate fine if overdue
            due_date = datetime.strptime(transaction['due_date'], '%Y-%m-%d')
            return_date_obj = datetime.strptime(return_date, '%Y-%m-%d')
            fine = 0.0
            if return_date_obj > due_date:
                days_late = (return_date_obj - due_date).days
                fine = days_late * 0.50  # $0.50 per day late

            # Update transaction
            _execute(cursor, (
                'UPDATE transactions SET return_date=%s, fine=%s WHERE id=%s'
            ), (return_date, f"{fine:.2f}", id))
            # Increase book available copies
            _execute(cursor, ('UPDATE books SET available_copies = available_copies + 1 WHERE id=%s'), (transaction['book_id'],))
            conn.commit()
            flash(f'Book returned successfully! Fine: ${float(fine):.2f}', 'success')
        except Exception as e:
            conn.rollback()
            flash(f'Error returning book: {str(e)}', 'danger')
        finally:
            cursor.close()
            conn.close()
        return redirect(url_for('transactions'))

    # GET request: show return form
    conn = get_db_connection()
    cursor = conn.cursor()
    _execute(cursor, ('''
        SELECT t.id, b.title, m.name, t.issue_date, t.due_date
        FROM transactions t
        JOIN books b ON t.book_id = b.id
        JOIN members m ON t.member_id = m.id
        WHERE t.id=%s AND t.return_date IS NULL
    '''), (id,))
    transaction = cursor.fetchone()
    cursor.close()
    conn.close()
    if not transaction:
        flash('No active transaction found with that ID!', 'danger')
        return redirect(url_for('transactions'))
    return render_template('return_book.html', transaction=transaction)

# Optional: reset database (for testing only)
@app.route('/reset_db')
def reset_db():
    if not os.environ.get('RENDER'):  # Only allow locally
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('DROP TABLE IF EXISTS transactions')
        cursor.execute('DROP TABLE IF EXISTS books')
        cursor.execute('DROP TABLE IF EXISTS members')
        conn.commit()
        conn.close()
        init_db()
        flash('Database reset successfully!', 'success')
    else:
        flash('Operation not allowed in production.', 'warning')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)