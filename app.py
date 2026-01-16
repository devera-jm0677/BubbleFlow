from flask import Flask, render_template, request, redirect, url_for, session, flash
import pymysql
import pymysql.cursors
from datetime import datetime
import math
import csv
from io import StringIO
from flask import Response


app = Flask(__name__)
app.secret_key = 'bubbleflow_secret_key'

# --- Database Configuration ---
def get_db_connection():
    return pymysql.connect(
        host='localhost',
        user='root',      # Default XAMPP/WAMP user
        password='',      # Default password is empty
        database='laundrysys_db',
        cursorclass=pymysql.cursors.DictCursor
    )

@app.route('/')
def landing():
    return render_template('landing.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email').lower()
        password = request.form.get('password')

        connection = get_db_connection()
        try:
            with connection.cursor() as cursor:
                # Query to find user
                sql = "SELECT * FROM users WHERE email=%s AND password=%s"
                cursor.execute(sql, (email, password))
                user = cursor.fetchone()

                if user:
                    # Store user info in session
                    session['user'] = {
                        'user_id': user['user_id'],
                        'name': user['name'],
                        'email': user['email'],
                        'role': user['role']
                    }
                    flash(f"Welcome back, {user['name']}!", "success")
                    return redirect(url_for('admin_dashboard' if user['role'] == 'admin' else 'user_dashboard'))
                else:
                    flash("Invalid email or password.", "error")
        finally:
            connection.close()

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email').lower()
        password = request.form.get('password')
        role = request.form.get('role')

        connection = get_db_connection()
        try:
            with connection.cursor() as cursor:
                # Check if email exists
                cursor.execute("SELECT user_id FROM users WHERE email=%s", (email,))
                if cursor.fetchone():
                    flash("Email already exists!", "error")
                    return redirect(url_for('register'))

                # Insert new user
                sql = "INSERT INTO users (name, email, password, role) VALUES (%s, %s, %s, %s)"
                cursor.execute(sql, (name, email, password, role))
                connection.commit()
                
                flash("Registration successful! Please login.", "success")
                return redirect(url_for('login'))
        except Exception as e:
            flash(f"An error occurred: {str(e)}", "error")
        finally:
            connection.close()

    return render_template('register.html')

@app.route('/user_dashboard')
def user_dashboard():
    if 'user' not in session or session['user']['role'] != 'user':
        return redirect(url_for('login'))
    
    user_id = session['user']['user_id']
    
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # Get active services
            cursor.execute("SELECT * FROM services WHERE status='active'")
            services = cursor.fetchall()
            
            # Add descriptions
            for service in services:
                if service['service_name'] == 'Wash':
                    service['description'] = 'Standard washing with detergent'
                elif service['service_name'] == 'Dry':
                    service['description'] = 'Machine drying'
                elif service['service_name'] == 'Fold':
                    service['description'] = 'Professional folding'
                elif service['service_name'] == 'Iron':
                    service['description'] = 'Ironing and steaming'
                else:
                    service['description'] = 'Premium service'
            
            # Get order stats
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_orders,
                    SUM(CASE WHEN status = 'Completed' THEN 1 ELSE 0 END) as completed_orders
                FROM orders 
                WHERE user_id=%s
            """, (user_id,))
            stats = cursor.fetchone()
            
            # Get recent orders (last 3)
            cursor.execute("""
                SELECT o.*, 
                       GROUP_CONCAT(s.service_name) as service_names
                FROM orders o
                LEFT JOIN order_services os ON o.order_id = os.order_id
                LEFT JOIN services s ON os.service_id = s.service_id
                WHERE o.user_id=%s
                GROUP BY o.order_id
                ORDER BY o.created_at DESC
                LIMIT 3
            """, (user_id,))
            recent_orders = cursor.fetchall()
            
    finally:
        connection.close()
    
    return render_template('user_dashboard.html',
                         services=services,
                         total_orders=stats['total_orders'] if stats else 0,
                         completed_orders=stats['completed_orders'] if stats else 0,
                         recent_orders=recent_orders)

@app.route('/edit_profile', methods=['GET', 'POST'])
def edit_profile():
    if 'user' not in session or session['user']['role'] != 'user':
        return redirect(url_for('login'))
    
    user_id = session['user']['user_id']
    
    if request.method == 'POST':
        # Handle form submission
        new_name = request.form.get('name')
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        connection = get_db_connection()
        try:
            with connection.cursor() as cursor:
                # Get current user data
                cursor.execute("SELECT * FROM users WHERE user_id=%s", (user_id,))
                user = cursor.fetchone()
                
                # Verify current password if trying to change password
                if current_password or new_password:
                    if user['password'] != current_password:
                        flash("Current password is incorrect.", "error")
                        return redirect(url_for('edit_profile'))
                    
                    if new_password != confirm_password:
                        flash("New passwords do not match.", "error")
                        return redirect(url_for('edit_profile'))
                    
                    if len(new_password) < 6:
                        flash("Password must be at least 6 characters.", "error")
                        return redirect(url_for('edit_profile'))
                
                # Update user information
                update_fields = []
                update_values = []
                
                if new_name and new_name != user['name']:
                    update_fields.append("name = %s")
                    update_values.append(new_name)
                
                if new_password and new_password != user['password']:
                    update_fields.append("password = %s")
                    update_values.append(new_password)
                
                if update_fields:
                    update_values.append(user_id)
                    sql = f"UPDATE users SET {', '.join(update_fields)} WHERE user_id = %s"
                    cursor.execute(sql, update_values)
                    connection.commit()
                    
                    # Update session
                    session['user']['name'] = new_name if new_name else session['user']['name']
                    
                    flash("Profile updated successfully!", "success")
                else:
                    flash("No changes were made.", "info")
                    
        except Exception as e:
            flash(f"An error occurred: {str(e)}", "error")
        finally:
            connection.close()
        
        return redirect(url_for('edit_profile'))
    
    # GET request - display form
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # Get user stats
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_orders,
                    SUM(CASE WHEN status = 'Pending' THEN 1 ELSE 0 END) as pending_orders,
                    SUM(CASE WHEN status = 'Ready' THEN 1 ELSE 0 END) as ready_orders,
                    SUM(CASE WHEN status = 'Completed' THEN 1 ELSE 0 END) as completed_orders
                FROM orders 
                WHERE user_id=%s
            """, (user_id,))
            user_stats = cursor.fetchone()
            
            # Get the user's first order date to approximate member since
            cursor.execute("""
                SELECT MIN(created_at) as first_order_date 
                FROM orders 
                WHERE user_id=%s
            """, (user_id,))
            first_order = cursor.fetchone()
            
            # Get user details
            cursor.execute("SELECT * FROM users WHERE user_id=%s", (user_id,))
            user_data = cursor.fetchone()
            
    finally:
        connection.close()
    
    # Create a user dictionary with additional data for the template
    user_info = {
        'name': user_data['name'],
        'email': user_data['email'],
        'role': user_data['role'],
        'created_at': first_order['first_order_date'] if first_order and first_order['first_order_date'] else datetime.now()
    }
    
    return render_template('edit_profile.html', 
                         user_stats=user_stats,
                         user=user_info)

@app.route('/submit_order', methods=['POST'])
def submit_order():
    if 'user' not in session or session['user']['role'] != 'user':
        return redirect(url_for('login'))
    
    weight = float(request.form.get('weight'))
    service_ids = request.form.getlist('services')
    
    if not service_ids:
        flash("Please select at least one service.", "error")
        return redirect(url_for('user_dashboard'))
    
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # Calculate total cost
            total = 0
            cursor.execute("SELECT * FROM services WHERE service_id IN (%s)" % 
                         ','.join(['%s']*len(service_ids)), service_ids)
            services = cursor.fetchall()
            
            for service in services:
                total += weight * float(service['price_per_kg'])
            
            # Create order
            sql = """
                INSERT INTO orders (user_id, weight, total_estimate, status) 
                VALUES (%s, %s, %s, %s)
            """
            cursor.execute(sql, (session['user']['user_id'], weight, total, 'Pending'))
            order_id = cursor.lastrowid
            
            # Add order services
            for service_id in service_ids:
                cursor.execute("""
                    INSERT INTO order_services (order_id, service_id) 
                    VALUES (%s, %s)
                """, (order_id, service_id))
            
            connection.commit()
            
            flash(f"Order submitted successfully! Estimated cost: ₱{total:.2f}", "success")
            
    except Exception as e:
        flash(f"An error occurred: {str(e)}", "error")
    finally:
        connection.close()
    
    return redirect(url_for('user_dashboard'))

@app.route('/user_orders')
def my_orders():
    if 'user' not in session or session['user']['role'] != 'user':
        return redirect(url_for('login'))
    
    user_id = session['user']['user_id']
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # Get order stats
            cursor.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'Pending' THEN 1 ELSE 0 END) as pending,
                    SUM(CASE WHEN status = 'In Progress' THEN 1 ELSE 0 END) as in_progress,
                    SUM(CASE WHEN status = 'Ready' THEN 1 ELSE 0 END) as ready,
                    SUM(CASE WHEN status = 'Completed' THEN 1 ELSE 0 END) as completed
                FROM orders 
                WHERE user_id=%s
            """, (user_id,))
            stats = cursor.fetchone()
            
            # Calculate pagination
            total_orders = stats['total'] if stats else 0
            total_pages = math.ceil(total_orders / per_page)
            offset = (page - 1) * per_page
            
            # Get orders with pagination
            cursor.execute("""
                SELECT o.*, 
                       GROUP_CONCAT(s.service_name) as services_list
                FROM orders o
                LEFT JOIN order_services os ON o.order_id = os.order_id
                LEFT JOIN services s ON os.service_id = s.service_id
                WHERE o.user_id=%s
                GROUP BY o.order_id
                ORDER BY o.created_at DESC
                LIMIT %s OFFSET %s
            """, (user_id, per_page, offset))
            orders = cursor.fetchall()
            
            # Format data for display
            for order in orders:
                order['order_code'] = f"ORD-{order['order_id']:04d}"
                if order['services_list']:
                    order['services_list'] = order['services_list'].split(',')
                else:
                    order['services_list'] = []
                
    finally:
        connection.close()
    
    return render_template('user_orders.html',
                         orders=orders,
                         total_orders=stats['total'] if stats else 0,
                         pending_orders=stats['pending'] if stats else 0,
                         in_progress_orders=stats['in_progress'] if stats else 0,
                         ready_orders=stats['ready'] if stats else 0,
                         completed_orders=stats['completed'] if stats else 0,
                         page=page,
                         total_pages=total_pages)

# =========================
# ADMIN DASHBOARD
# =========================
@app.route('/admin_dashboard')
def admin_dashboard():
    if 'user' not in session or session['user']['role'] != 'admin':
        return redirect(url_for('login'))

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:

            # ======================
            # ORDER COUNTS
            # ======================
            cur.execute("SELECT COUNT(*) AS total FROM orders")
            total_orders = cur.fetchone()['total']

            cur.execute("SELECT COUNT(*) AS pending FROM orders WHERE status='Pending'")
            pending_orders = cur.fetchone()['pending']

            cur.execute("SELECT COUNT(*) AS in_progress FROM orders WHERE status='In Progress'")
            in_progress_orders = cur.fetchone()['in_progress']

            cur.execute("SELECT COUNT(*) AS ready FROM orders WHERE status='Ready'")
            ready_orders = cur.fetchone()['ready']

            cur.execute("SELECT COUNT(*) AS completed FROM orders WHERE status='Completed'")
            completed_orders = cur.fetchone()['completed']

            # ======================
            # 💰 REVENUE ANALYTICS
            # ======================
            cur.execute("""
                SELECT IFNULL(SUM(total_estimate),0) AS revenue_today
                FROM orders
                WHERE status='Completed'
                AND DATE(created_at) = CURDATE()
            """)
            revenue_today = cur.fetchone()['revenue_today']

            cur.execute("""
                SELECT IFNULL(SUM(total_estimate),0) AS revenue_month
                FROM orders
                WHERE status='Completed'
                AND MONTH(created_at) = MONTH(CURDATE())
                AND YEAR(created_at) = YEAR(CURDATE())
            """)
            revenue_month = cur.fetchone()['revenue_month']

            # ======================
            # ⏱ AVG PROCESSING TIME
            # ======================
            cur.execute("""
                SELECT AVG(TIMESTAMPDIFF(MINUTE, created_at, updated_at)) AS avg_minutes
                FROM orders
                WHERE status='Completed'
            """)
            avg_minutes = cur.fetchone()['avg_minutes'] or 0
            avg_minutes = int(avg_minutes)

            avg_hours = avg_minutes // 60
            avg_mins = avg_minutes % 60

            # ======================
            # 📈 ORDERS PER DAY (CHART)
            # ======================
            cur.execute("""
                SELECT DATE(created_at) AS day, COUNT(*) AS total
                FROM orders
                GROUP BY day
                ORDER BY day
            """)
            daily = cur.fetchall()

            # ======================
            # 🧺 SERVICE USAGE (CHART)
            # ======================
            cur.execute("""
                SELECT s.service_name, COUNT(*) AS total
                FROM order_services os
                JOIN services s ON os.service_id = s.service_id
                GROUP BY s.service_name
            """)
            services = cur.fetchall()

            

    finally:
        conn.close()

    return render_template(
        'admin/dashboard.html',

        # counts
        total_orders=total_orders,
        pending_orders=pending_orders,
        in_progress_orders=in_progress_orders,
        ready_orders=ready_orders,
        completed_orders=completed_orders,

        # revenue
        revenue_today=revenue_today,
        revenue_month=revenue_month,

        # processing time
        avg_minutes=avg_minutes,
        avg_hours=avg_hours,
        avg_mins=avg_mins,

        # charts
        chart_days=[d['day'].strftime('%b %d') for d in daily],
        chart_orders=[d['total'] for d in daily],
        chart_services=[s['service_name'] for s in services],
        chart_counts=[s['total'] for s in services]
    )



# =========================
# SERVICES (FULL CRUD)
# =========================
@app.route('/admin/services', methods=['GET', 'POST'])
def manage_services():
    if 'user' not in session or session['user']['role'] != 'admin':
        return redirect(url_for('login'))

    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:

            # CREATE or UPDATE
            if request.method == 'POST':
                service_id = request.form.get('service_id')
                name = request.form['service_name']
                price = request.form['price_per_kg']
                status = request.form['status']

                if service_id:  # UPDATE
                    cursor.execute("""
                        UPDATE services
                        SET service_name=%s, price_per_kg=%s, status=%s
                        WHERE service_id=%s
                    """, (name, price, status, service_id))
                else:  # CREATE
                    cursor.execute("""
                        INSERT INTO services (service_name, price_per_kg, status)
                        VALUES (%s,%s,%s)
                    """, (name, price, status))

                connection.commit()

            # READ
            cursor.execute("""
                SELECT s.*,
                (SELECT COUNT(*) FROM order_services os WHERE os.service_id = s.service_id) AS used_count
                FROM services s
            """)
            services = cursor.fetchall()


    finally:
        connection.close()

    return render_template('admin/services.html', services=services)

@app.route('/admin/services/reactivate/<int:service_id>')
def reactivate_service(service_id):
    if 'user' not in session or session['user']['role'] != 'admin':
        return redirect(url_for('login'))

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                UPDATE services
                SET status='active'
                WHERE service_id=%s
            """, (service_id,))
            connection.commit()
            flash("Service reactivated successfully.", "success")
    finally:
        connection.close()

    return redirect(url_for('manage_services'))

# =========================
# DELETE SERVICE  ✅ (THIS WAS MISSING)
# =========================
@app.route('/admin/services/delete/<int:service_id>')
def delete_service(service_id):
    if 'user' not in session or session['user']['role'] != 'admin':
        return redirect(url_for('login'))

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            # CHECK kung ginagamit sa orders
            cursor.execute("""
                SELECT COUNT(*) AS total
                FROM order_services
                WHERE service_id=%s
            """, (service_id,))
            used = cursor.fetchone()['total']

            if used > 0:
                flash("Cannot delete service. It is already used in orders.", "error")
                return redirect(url_for('manage_services'))

            # SOFT DELETE (inactive)
            cursor.execute("""
                UPDATE services
                SET status='inactive'
                WHERE service_id=%s
            """, (service_id,))
            connection.commit()

            flash("Service deactivated successfully.", "success")

    finally:
        connection.close()

    return redirect(url_for('manage_services'))


# =========================
# MANAGE ORDERS
# =========================
@app.route('/admin/orders', methods=['GET', 'POST'])
def manage_orders():
    if 'user' not in session or session['user']['role'] != 'admin':
        return redirect(url_for('login'))

    connection = get_db_connection()

    try:
        with connection.cursor() as cursor:
            if request.method == 'POST':
                order_id = request.form['order_id']
                status = request.form['status']

                cursor.execute(
                    "UPDATE orders SET status=%s WHERE order_id=%s",
                    (status, order_id)
                )
                connection.commit()

            # ===== DAILY STATS (TODAY ONLY) =====
            cursor.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN status='Pending' THEN 1 ELSE 0 END) as pending,
                    SUM(CASE WHEN status='In Progress' THEN 1 ELSE 0 END) as in_progress,
                    SUM(CASE WHEN status='Ready' THEN 1 ELSE 0 END) as ready,
                    SUM(CASE WHEN status='Completed' THEN 1 ELSE 0 END) as completed
                FROM orders
                WHERE DATE(created_at) = CURDATE()
            """)
            daily_stats = cursor.fetchone()

            # ===== ORDERS WITH SERVICES =====
            cursor.execute("""
                SELECT 
    o.order_id,
    o.user_id,
    u.name AS customer_name,
    o.weight,
    o.total_estimate,
    o.status,
    o.created_at,
    GROUP_CONCAT(s.service_name SEPARATOR ', ') AS services
FROM orders o
JOIN users u ON o.user_id = u.user_id
LEFT JOIN order_services os ON o.order_id = os.order_id
LEFT JOIN services s ON os.service_id = s.service_id
GROUP BY 
    o.order_id,
    o.user_id,
    u.name,
    o.weight,
    o.total_estimate,
    o.status,
    o.created_at
ORDER BY o.created_at DESC;

            """)
            orders = cursor.fetchall()

            # format services list
            for o in orders:
                o['services'] = o['services'].split(',') if o['services'] else []

    finally:
        connection.close()

    return render_template(
        'admin/orders.html',
        orders=orders,
        stats=daily_stats
    )


@app.route('/admin/analytics')
def admin_analytics():
    if 'user' not in session or session['user']['role'] != 'admin':
        return redirect(url_for('login'))

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DATE(created_at) as day, COUNT(*) as total
                FROM orders
                GROUP BY day
                ORDER BY day DESC
                LIMIT 7
            """)
            daily_orders = cur.fetchall()

            cur.execute("""
                SELECT s.service_name, COUNT(*) as total
                FROM order_services os
                JOIN services s ON os.service_id = s.service_id
                GROUP BY s.service_name
                ORDER BY total DESC
            """)
            top_services = cur.fetchall()

            cur.execute("""
                SELECT SUM(total_estimate) as revenue
                FROM orders
                WHERE status='Completed'
            """)
            revenue = cur.fetchone()['revenue'] or 0
    finally:
        conn.close()

    return render_template(
        'admin/analytics.html',
        daily_orders=daily_orders,
        top_services=top_services,
        revenue=revenue
    )

@app.route('/order/<int:order_id>/receipt')
def print_receipt(order_id):
    if 'user' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:

            # ORDER INFO
            cur.execute("""
                SELECT o.*, u.name
                FROM orders o
                JOIN users u ON o.user_id = u.user_id
                WHERE o.order_id = %s
            """, (order_id,))
            order = cur.fetchone()

            if not order:
                flash("Order not found.", "error")
                return redirect(url_for('my_orders'))

            # SERVICES WITH PRICE
            cur.execute("""
                SELECT s.service_name, s.price_per_kg
                FROM order_services os
                JOIN services s ON os.service_id = s.service_id
                WHERE os.order_id = %s
            """, (order_id,))
            services = cur.fetchall()

    finally:
        conn.close()

    return render_template(
        "receipt.html",
        order=order,
        services=services
    )



@app.route('/admin/reports/sales')
def sales_report():
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT order_id, total_estimate, created_at
                FROM orders
                WHERE status='Completed'
            """)
            rows = cur.fetchall()
    finally:
        conn.close()

    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(['Order ID', 'Total', 'Date'])

    for r in rows:
        writer.writerow([r['order_id'], r['total_estimate'], r['created_at']])

    return Response(
        si.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment;filename=sales_report.csv'}
    )


@app.route('/admin/reports/services')
def service_usage_report():
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT s.service_name, COUNT(*) AS usage_count
                FROM order_services os
                JOIN services s ON os.service_id=s.service_id
                GROUP BY s.service_name
            """)
            rows = cur.fetchall()
    finally:
        conn.close()

    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(['Service', 'Times Used'])

    for r in rows:
        writer.writerow([r['service_name'], r['usage_count']])

    return Response(
        si.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment;filename=service_usage.csv'}
    )


@app.route('/admin/reports/receipts')
def bulk_receipts():
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT o.order_id, u.name, o.total_estimate, o.created_at
                FROM orders o
                JOIN users u ON o.user_id=u.user_id
                WHERE o.status='Completed'
            """)
            rows = cur.fetchall()
    finally:
        conn.close()

    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(['Order ID', 'Customer', 'Total', 'Date'])

    for r in rows:
        writer.writerow([r['order_id'], r['name'], r['total_estimate'], r['created_at']])

    return Response(
        si.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment;filename=receipts.csv'}
    )

@app.route('/admin/services/hard-delete/<int:service_id>')
def hard_delete_service(service_id):
    if 'user' not in session or session['user']['role'] != 'admin':
        return redirect(url_for('login'))

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM services WHERE service_id = %s",
                (service_id,)
            )
        conn.commit()
        flash('Service deleted successfully.', 'success')
    except Exception as e:
        conn.rollback()
        flash('Error deleting service.', 'danger')
        print(e)
    finally:
        conn.close()

    return redirect(url_for('manage_services'))

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out successfully.", "success")
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)