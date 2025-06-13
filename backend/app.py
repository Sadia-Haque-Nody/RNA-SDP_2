from flask import Flask, jsonify, request, session
from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector
from flask_cors import CORS

app = Flask(__name__)
app.secret_key = 'NO_D_ASH_A_ROOF_E'

CORS(app)

# Database connection
def get_db_connection():
    return mysql.connector.connect(
        host='localhost',
        user='root',
        password='123',
        database='mymealplanner'
    )

@app.route('/api/test_db')
def test_db():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")  # Simple test query
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        if result and result[0] == 1:
            return jsonify({'message': 'Database connection is working!'})
        else:
            return jsonify({'message': 'Unexpected result from database.'}), 500
    except Exception as e:
        return jsonify({'error': f'Database connection failed: {str(e)}'}), 500


# ===== Authentication APIs =====

@app.route('/api/check_session', methods=['GET'])
def check_session():
    user_id = session.get('user_id')
    if user_id:
        return jsonify({'logged_in': True, 'user_id': user_id}), 200
    else:
        return jsonify({'logged_in': False}), 200

@app.route('/api/signup', methods=['POST'])
def api_signup():
    data = request.json
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')
    confirm_password = data.get('confirm_password', '')

    if not username or not email or not password:
        return jsonify({'error': 'All fields are required'}), 400

    if len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400

    if password != confirm_password:
        return jsonify({'error': 'Passwords do not match'}), 400

    hashed_password = generate_password_hash(password)

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO Users (username, email, password) VALUES (%s, %s, %s)",
            (username, email, hashed_password)
        )
        conn.commit()
        return jsonify({'message': 'Account created successfully'}), 200

    except mysql.connector.IntegrityError:
        return jsonify({'error': 'Username or email already exists'}), 409

    except Exception as e:
        print("Signup error:", e)
        return jsonify({'error': 'Server error'}), 500

    finally:
        if 'cursor' in locals(): cursor.close()
        if 'conn' in locals(): conn.close()

@app.route('/api/login', methods=['POST'])
def api_login():
    if session.get('user_id'):
        # User already logged in
        return jsonify({'message': 'Already logged in'}), 200

    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT user_id, password FROM Users WHERE username = %s", (username,))
        user = cursor.fetchone()

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['user_id']
            return jsonify({'message': 'Login successful'}), 200
        else:
            return jsonify({'error': 'Invalid username or password'}), 401

    except Exception as e:
        print("Login error:", e)
        return jsonify({'error': 'Server error'}), 500

    finally:
        if 'cursor' in locals(): cursor.close()
        if 'conn' in locals(): conn.close()

@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'message': 'Logged out successfully'}), 200

# ===== Meal APIs =====

@app.route('/api/by_ingredient', methods=['POST'])
def api_by_ingredient():
    try:
        ingredients = request.json.get('ingredients', [])
        meals = []

        if ingredients:
            placeholders = ', '.join(['%s'] * len(ingredients))
            query = f'''
                SELECT  m.meal_name, m.tags
                FROM Meals m
                JOIN Meal_Ingredients mi ON m.meal_id = mi.meal_id
                JOIN Ingredients i ON mi.ingredient_id = i.ingredient_id
                WHERE i.ingredient_name IN ({placeholders})
                GROUP BY m.meal_id
                HAVING COUNT(DISTINCT i.ingredient_name) = %s;
            '''

            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(query, ingredients + [len(ingredients)])
            meals = cursor.fetchall()
        return jsonify(meals)

    except Exception as e:
        print("Error in by_ingredient:", e)
        return jsonify({'error': 'Something went wrong'}), 500
    finally:
        if 'cursor' in locals(): cursor.close()
        if 'conn' in locals(): conn.close()


@app.route('/api/by_preference', methods=['POST'])
def api_by_preference():
    try:
        preference = request.json.get('preference', '').strip().lower()
        print("Searching tags for preference:", preference)
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        query = "SELECT m.meal_name, m.tags FROM Meals m WHERE LOWER(CONCAT(',', m.tags, ',')) LIKE %s"
        cursor.execute(query, ("%,{}%,".format(preference),))
        meals = cursor.fetchall()
        return jsonify(meals)

    except Exception as e:
        print("Error in by_preference:", e)
        return jsonify({'error': 'Something went wrong'}), 500
    finally:
        if 'cursor' in locals(): cursor.close()
        if 'conn' in locals(): conn.close()


@app.route('/api/meal/<int:meal_id>', methods=['GET'])
def api_meal_detail(meal_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Get meal details
        cursor.execute("SELECT * FROM Meals WHERE meal_id = %s", (meal_id,))
        meal = cursor.fetchone()

        if not meal:
            return jsonify({"error": "Meal not found"}), 404

        # Get ingredients
        cursor.execute('''
            SELECT i.ingredient_name, mi.quantity, i.unit
            FROM Meal_Ingredients mi
            JOIN Ingredients i ON mi.ingredient_id = i.ingredient_id
            WHERE mi.meal_id = %s
        ''', (meal_id,))
        ingredients = cursor.fetchall()

        # Build JSON response
        response = {
            "meal_id": meal['meal_id'],
            "name": meal['meal_name'],
            "description": meal.get('description', ''),  # Using get() in case description is optional
            "calories": meal['calories'],
            "protein": meal['protein_g'],
            "carbs": meal['carbs_g'],
            "fat": meal['fat_g'],
            "image_url": meal.get('image_url', ''),  # Assuming you might have an image URL
            "ingredients": [
                {
                    "name": ingr['ingredient_name'],
                    "quantity": ingr['quantity'],
                    "unit": ingr['unit']
                } for ingr in ingredients
            ]
        }

        return jsonify(response), 200

    except Exception as e:
        print("Error in meal_detail:", e)
        return jsonify({"error": "Something went wrong"}), 500
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()


@app.route('/api/add_to_plan/<int:meal_id>', methods=['POST'])
def api_add_to_plan(meal_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Not authenticated'}), 401

    try:
        data = request.json
        selected_day = data.get('day')
        meal_type = data.get('meal_type')

        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if this user already has a meal for this day & type
        cursor.execute('''
            SELECT plan_id FROM Meal_Plan
            WHERE user_id = %s AND day = %s AND meal_type = %s
        ''', (user_id, selected_day, meal_type))
        existing_plan = cursor.fetchone()

        if existing_plan:
            # Update the existing meal plan with the new meal
            cursor.execute('''
                UPDATE Meal_Plan
                SET meal_id = %s
                WHERE user_id = %s AND day = %s AND meal_type = %s
            ''', (meal_id, user_id, selected_day, meal_type))
        else:
            # Insert new plan
            cursor.execute('''
                INSERT INTO Meal_Plan (user_id, meal_id, meal_type, day)
                VALUES (%s, %s, %s, %s)
            ''', (user_id, meal_id, meal_type, selected_day))

        conn.commit()
        return jsonify({'message': 'Meal added or updated in your plan'})

    except Exception as e:
        print("Error in add_to_plan:", e)
        return jsonify({'error': 'Something went wrong'}), 500

    finally:
        if 'cursor' in locals(): cursor.close()
        if 'conn' in locals(): conn.close()

@app.route('/api/meal_plan_with_totals', methods=['GET'])
def get_meal_plan_with_totals():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Not authenticated'}), 401

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Get meals in the plan for the user
        cursor.execute('''
            SELECT mp.day, mp.meal_type, m.meal_id, m.meal_name, m.calories, m.carbs_g, m.fat_g, m.protein_g
            FROM Meal_Plan mp
            JOIN Meals m ON mp.meal_id = m.meal_id
            WHERE mp.user_id = %s
        ''', (user_id,))
        plans = cursor.fetchall()

        result = {}

        for row in plans:
            day = row['day']
            meal_type = row['meal_type']

            if day not in result:
                result[day] = {
                    'meals': {},
                    'totals': {
                        'calories': 0,
                        'carbs_g': 0,
                        'fat_g': 0,
                        'protein_g': 0
                    }
                }

            result[day]['meals'][meal_type] = {
                'meal_id': row['meal_id'],
                'meal_name': row['meal_name']
            }

            result[day]['totals']['calories'] += int(row['calories']) if row['calories'] else 0
            result[day]['totals']['carbs_g'] += float(row['carbs_g']) if row['carbs_g'] else 0
            result[day]['totals']['fat_g'] += float(row['fat_g']) if row['fat_g'] else 0
            result[day]['totals']['protein_g'] += float(row['protein_g']) if row['protein_g'] else 0

        return jsonify(result)

    except Exception as e:
        print("Error in meal_plan_with_totals:", e)
        return jsonify({'error': 'Something went wrong'}), 500

    finally:
        if 'cursor' in locals(): cursor.close()
        if 'conn' in locals(): conn.close()

@app.route('/api/remove_from_plan', methods=['POST'])
def api_remove_from_plan():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Not authenticated'}), 401

    data = request.json
    day = data.get('day')
    meal_type = data.get('meal_type')

    if not day or not meal_type:
        return jsonify({'error': 'Day and meal_type are required'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Delete the meal plan entry for that user, day, and meal_type
        cursor.execute('''
            DELETE FROM Meal_Plan
            WHERE user_id = %s AND day = %s AND meal_type = %s
        ''', (user_id, day, meal_type))

        conn.commit()

        return jsonify({'message': 'Meal removed from your plan'})

    except Exception as e:
        print("Error in remove_from_plan:", e)
        return jsonify({'error': 'Something went wrong'}), 500

    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()
@app.route('/api/meal_plan_clear_all', methods=['DELETE'])
def api_clear_all_meal_plan():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Not authenticated'}), 401

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Delete all meal plan entries for this user
        cursor.execute('DELETE FROM Meal_Plan WHERE user_id = %s', (user_id,))
        conn.commit()

        return jsonify({'message': 'All meal plans cleared successfully'}), 200

    except Exception as e:
        print("Error clearing meal plan:", e)
        return jsonify({'error': 'Something went wrong'}), 500

    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

@app.route('/api/get_username', methods=['GET'])
def get_username():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Not authenticated'}), 401

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT name FROM Users WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()

        if user:
            return jsonify({'name': user['name']})
        else:
            return jsonify({'error': 'User not found'}), 404

    except Exception as e:
        print("Error in get_username:", e)
        return jsonify({'error': 'Something went wrong'}), 500

    finally:
        if 'cursor' in locals(): cursor.close()
        if 'conn' in locals(): conn.close()


if __name__ == '__main__':
    app.run(debug=True)