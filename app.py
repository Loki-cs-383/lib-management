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

def init_db():
    """Initialize database with tables if they don't exist"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Create tables (same schema as your schema.sql)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(100) NOT NULL,
            email VARCHAR(100) UNIQUE NOT NULL,
            phone VARCHAR(20),
            join_date DATE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
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
    ''')

    cursor.execute('''
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
    ''')

    # Insert sample data only if tables are empty
    cursor.execute('SELECT COUNT(*) FROM members')
    if cursor.fetchone()[0] == 0:
        cursor.execute('''
            INSERT INTO members (name, email, phone, join_date) VALUES
            ('John Doe', 'john@example.com', '1234567890', '2023-01-15'),
            ('Jane Smith', 'jane@example.com', '0987654321', '2023-02-20')
        ''')

        cursor.execute('''
            INSERT INTO books (title, author, isbn, publication_year, available_copies, total_copies) VALUES
            ('The Great Gatsby', 'F. Scott Fitzgerald', '9780743273565', 1925, 3, 3),
            ('To Kill a Mockingbird', 'Harper Lee', '9780061120084', 1960, 2, 2),
            ('1984', 'George Orwell', '9780451524935', 1949, 4, 4)
        ''')

    conn.commit()
    conn.close()

# Initialize database when app starts
with app.app_context():
    init_db()

# Home page
@app.route('/')
def index():
    return render_template('index.html')

# Books routes
@app.route('/books')
def books():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM books')
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
            cursor.execute(
                'INSERT INTO books (title, author, isbn, publication_year, total_copies, available_copies) VALUES (%s, %s, %s, %s, %s, %s)',
                (title, author, isbn, publication_year, total_copies, total_copies)
            )
            conn.commit()
            flash('Book added successfully!', 'success')
        except Exception as e:
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

        cursor.execute(
            'UPDATE books SET title=%s, author=%s, isbn=%s, publication_year=%s, total_copies=%s WHERE id=%s',
            (title, author, isbn, publication_year, total_copies, id)
        )
        # Update available copies based on difference in total copies
        cursor.execute('SELECT available_copies, total_copies FROM books WHERE id=%s', (id,))
        book = cursor.fetchone()
        if book:
            diff = int(total_copies) - book['total_copies']
            new_available = book['available_copies'] + diff
            if new_available < 0:
                new_available = 0
            cursor.execute('UPDATE books SET available_copies=%s WHERE id=%s', (new_available, id))
        conn.commit()
        flash('Book updated successfully!', 'success')
        return redirect(url_for('books'))

    # GET request
    cursor.execute('SELECT * FROM books WHERE id=%s', (id,))
    book = cursor.fetchone()
    cursor.close()
    conn.close()
    return render_template('edit_book.html', book=book)

@app.route('/books/delete/<int:id>')
def delete_book(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Check if book is issued
        cursor.execute('SELECT COUNT(*) as count FROM transactions WHERE book_id=%s AND return_date IS NULL', (id,))
        result = cursor.fetchone()
        if result['count'] > 0:
            flash('Cannot delete book that is currently issued!', 'danger')
        else:
            cursor.execute('DELETE FROM books WHERE id=%s', (id,))
            conn.commit()
            flash('Book deleted successfully!', 'success')
    except Exception as e:
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
    cursor.execute('SELECT * FROM members')
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
            cursor.execute(
                'INSERT INTO members (name, email, phone, join_date) VALUES (%s, %s, %s, %s)',
                (name, email, phone, join_date)
            )
            conn.commit()
            flash('Member added successfully!', 'success')
        except Exception as e:
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

        cursor.execute(
            'UPDATE members SET name=%s, email=%s, phone=%s, join_date=%s WHERE id=%s',
            (name, email, phone, join_date, id)
        )
        conn.commit()
        flash('Member updated successfully!', 'success')
        return redirect(url_for('members'))

    # GET request
    cursor.execute('SELECT * FROM members WHERE id=%s', (id,))
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
        cursor.execute('SELECT COUNT(*) as count FROM transactions WHERE member_id=%s AND return_date IS NULL', (id,))
        result = cursor.fetchone()
        if result['count'] > 0:
            flash('Cannot delete member who has issued books!', 'danger')
        else:
            cursor.execute('DELETE FROM members WHERE id=%s', (id,))
            conn.commit()
            flash('Member deleted successfully!', 'success')
    except Exception as e:
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
    cursor.execute('''
        SELECT t.*, b.title, m.name
        FROM transactions t
        JOIN books b ON t.book_id = b.id
        JOIN members m ON t.member_id = m.id
        ORDER BY t.issue_date DESC
    ''')
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
            cursor.execute('SELECT available_copies FROM books WHERE id=%s', (book_id,))
            book = cursor.fetchone()
            if not book or book['available_copies'] <= 0:
                flash('Book is not available for issue!', 'danger')
                return redirect(url_for('issue_book'))

            # Create transaction
            cursor.execute(
                'INSERT INTO transactions (book_id, member_id, issue_date, due_date) VALUES (%s, %s, %s, %s)',
                (book_id, member_id, issue_date, due_date_str)
            )
            # Update book available copies
            cursor.execute(
                'UPDATE books SET available_copies = available_copies - 1 WHERE id=%s',
                (book_id,)
            )
            conn.commit()
            flash('Book issued successfully!', 'success')
        except Exception as e:
            flash(f'Error issuing book: {str(e)}', 'danger')
        finally:
            cursor.close()
            conn.close()
        return redirect(url_for('transactions'))

    # GET request: show form with available books and members
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, title FROM books WHERE available_copies > 0')
    books = cursor.fetchall()
    cursor.execute('SELECT id, name FROM members')
    members = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('issue_book.html', books=books, members=members)

@app.route('/return_book/<int:id>', methods=['GET', 'POST'])
def return_book(id):
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        return_date = request.form['return_date']

        # Calculate fine if any (e.g., $0.50 per day overdue)
        cursor.execute('''
            SELECT t.*, b.title, m.name
            FROM transactions t
            JOIN books b ON t.book_id = b.id
            JOIN members m ON t.member_id = m.id
            WHERE t.id=%s
        ''', (id,))
        transaction = cursor.fetchone()

        if transaction:
            # Handle due_date which might be a string or date object
            due_date = transaction['due_date']
            if isinstance(due_date, str):
                due_date = datetime.strptime(due_date, '%Y-%m-%d').date()
            elif hasattr(due_date, 'date'):
                due_date = due_date.date()

            # Handle return_date from form (always a string)
            return_date_obj = datetime.strptime(return_date, '%Y-%m-%d').date()
            days_overdue = (return_date_obj - due_date).days
            fine = max(0, days_overdue * 0.50)  # $0.50 per day

            # Update transaction
            cursor.execute(
                'UPDATE transactions SET return_date=%s, fine=%s WHERE id=%s',
                (return_date, fine, id)
            )
            # Update book available copies
            cursor.execute(
                'UPDATE books SET available_copies = available_copies + 1 WHERE id=%s',
                (transaction['book_id'],)
            )
            conn.commit()
            flash(f'Book returned successfully! Fine: ${fine:.2f}', 'success')
        else:
            flash('Transaction not found!', 'danger')

        cursor.close()
        conn.close()
        return redirect(url_for('transactions'))

    # GET request: show return form
    cursor.execute('''
        SELECT t.*, b.title, m.name
        FROM transactions t
        JOIN books b ON t.book_id = b.id
        JOIN members m ON t.member_id = m.id
        WHERE t.id=%s AND t.return_date IS NULL
    ''', (id,))
    transaction = cursor.fetchone()
    cursor.close()
    conn.close()
    if not transaction:
        flash('No such active transaction!', 'danger')
        return redirect(url_for('transactions'))
    return render_template('return_book.html', transaction=transaction)

if __name__ == '__main__':
    app.run(debug=True)