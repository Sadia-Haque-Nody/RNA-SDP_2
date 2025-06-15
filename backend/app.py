from flask import Flask, jsonify, request
from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector
from flask_cors import CORS
from functools import wraps
import jwt
import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'NO_D_ASH_A_ROOF_E'

CORS(app)

# Database connection
def get_db_connection():
    return mysql.connector.connect(
        host='localhost',
        user='root',
        password='',
        database='mymealplanner'
    )

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None

        if 'Authorization' in request.headers:
            parts = request.headers['Authorization'].split()
            if len(parts) == 2 and parts[0] == 'Bearer':
                token = parts[1]

        if not token:
            return jsonify({'error': 'Token is missing!'}), 401

        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user_id = data['user_id']
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired'}), 401
        except jwt.InvalidTokenError as e:
            print(f"Invalid token error: {str(e)}")  # Log the exact error
            return jsonify({'error': 'Invalid token'}), 401

        return f(current_user_id, *args, **kwargs)
    return decorated
@app.route('/api/test_db')
def test_db():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        if result and result[0] == 1:
            return jsonify({'message': 'Database connection is working!'})
        else:
            return jsonify({'message': 'Unexpected result from database.'}), 500
    except Exception as e:
        return jsonify({'error': f'Database connection failed: {str(e)}'}), 500

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
        cursor = conn.cursor(buffered=True)
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
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        cursor.execute("SELECT user_id, password FROM Users WHERE username = %s", (username,))
        user = cursor.fetchone()

        if user and check_password_hash(user['password'], password):
            token = jwt.encode({
                'user_id': user['user_id'],
                'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
            }, app.config['SECRET_KEY'], algorithm="HS256")
            
            # Ensure token is a string, decode bytes if necessary (PyJWT v2+ returns string usually)
            if isinstance(token, bytes):
                token = token.decode('utf-8')

            return jsonify({'message': 'Login successful', 'token': token}), 200
        else:
            return jsonify({'error': 'Invalid username or password'}), 401
    except Exception as e:
        print("Login error:", e)
        return jsonify({'error': 'Server error'}), 500
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

@app.route('/api/by_ingredient', methods=['POST'])
def api_by_ingredient():
    try:
        ingredients = request.json.get('ingredients', [])
        meals = []
        if ingredients:
            placeholders = ', '.join(['%s'] * len(ingredients))
            query = f'''
                SELECT m.*
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
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

@app.route('/api/by_preference', methods=['POST'])
def api_by_preference():
    try:
        preference = request.json.get('preference', '').strip().lower()
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = "SELECT m.* FROM Meals m WHERE LOWER(CONCAT(',', m.tags, ',')) LIKE %s"
        cursor.execute(query, ("%,{}%,".format(preference),))
        meals = cursor.fetchall()
        return jsonify(meals)
    except Exception as e:
        print("Error in by_preference:", e)
        return jsonify({'error': 'Something went wrong'}), 500
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

@app.route('/api/all_meals', methods=['GET'])
def api_all_meals():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM Meals")
        meals = cursor.fetchall()
        return jsonify(meals), 200
    except Exception as e:
        print("Error fetching all meals:", e)
        return jsonify({'error': 'Something went wrong'}), 500
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

@app.route('/api/meal/<int:meal_id>', methods=['GET'])
def api_meal_detail(meal_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM Meals WHERE meal_id = %s", (meal_id,))
        meal = cursor.fetchone()
        if not meal:
            return jsonify({"error": "Meal not found"}), 404

        cursor.execute('''
            SELECT i.ingredient_name, mi.quantity, i.unit
            FROM Meal_Ingredients mi
            JOIN Ingredients i ON mi.ingredient_id = i.ingredient_id
            WHERE mi.meal_id = %s
        ''', (meal_id,))
        ingredients = cursor.fetchall()

        response = {
            "meal_id": meal['meal_id'],
            "name": meal['meal_name'],
            "description": meal.get('description', ''),
            "calories": meal['calories'],
            "protein": meal['protein_g'],
            "carbs": meal['carbs_g'],
            "fat": meal['fat_g'],
            "image_url": meal.get('image_url', ''),
            "ingredients": [
                {
                    "name": ingr['ingredient_name'],
                    "quantity": ingr['quantity'],
                    "unit": ingr['unit']
                } for ingr in ingredients
            ],
            "tags": meal['tags']
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
@token_required
def api_add_to_plan(user_id, meal_id):
    try:
        data = request.json
        selected_day = data.get('day')
        meal_type = data.get('meal_type')

        if not selected_day or not meal_type:
            return jsonify({'error': 'Day and meal_type required'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if there is already a plan for this user, day, and meal_type
        cursor.execute('''
            SELECT meal_plan_id FROM Meal_Plan
            WHERE user_id = %s AND day = %s AND meal_type = %s
        ''', (user_id, selected_day, meal_type))
        existing_plan = cursor.fetchone()

        if existing_plan:
            # Update existing plan
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
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()


@app.route('/api/meal_plan_with_totals', methods=['GET'])
@token_required
def get_meal_plan_with_totals(user_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
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
                result[day] = {'meals': {}, 'totals': {'calories': 0, 'carbs_g': 0, 'fat_g': 0, 'protein_g': 0}}
            result[day]['meals'][meal_type] = {
                'meal_id': row['meal_id'],
                'meal_name': row['meal_name'],
                'calories': row['calories'],
                'carbs_g': row['carbs_g'],
                'fat_g': row['fat_g'],
                'protein_g': row['protein_g']
            }
            # Sum totals
            result[day]['totals']['calories'] += row['calories']
            result[day]['totals']['carbs_g'] += row['carbs_g']
            result[day]['totals']['fat_g'] += row['fat_g']
            result[day]['totals']['protein_g'] += row['protein_g']

        return jsonify(result)
    except Exception as e:
        print("Error in meal_plan_with_totals:", e)
        return jsonify({'error': 'Something went wrong'}), 500
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

@app.route('/api/remove_from_plan', methods=['POST'])
@token_required
def api_remove_meal_from_plan(user_id):
    try:
        data = request.json
        day = data.get('day')
        meal_type = data.get('meal_type')

        if not day or not meal_type:
            return jsonify({'error': 'Day and meal_type required'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            DELETE FROM Meal_Plan
            WHERE user_id = %s AND day = %s AND meal_type = %s
        ''', (user_id, day, meal_type))
        conn.commit()
        return jsonify({'message': 'Meal removed from plan'})
    except Exception as e:
        print("Error removing meal:", e)
        return jsonify({'error': 'Something went wrong'}), 500
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

@app.route('/api/clear_meal_plan', methods=['POST'])
@token_required
def api_clear_meal_plan(user_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM Meal_Plan WHERE user_id = %s', (user_id,))
        conn.commit()
        return jsonify({'message': 'Meal plan cleared'})
    except Exception as e:
        print("Error clearing meal plan:", e)
        return jsonify({'error': 'Something went wrong'}), 500
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

@app.route('/api/my_account', methods=['GET'])
@token_required
def api_my_account(user_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT username FROM Users WHERE user_id = %s', (user_id,))
        user = cursor.fetchone()

        if not user:
            return jsonify({'error': 'User not found'}), 404

        cursor.execute('''
            SELECT mp.meal_id, m.meal_name, mp.day, mp.meal_type
            FROM Meal_Plan mp
            JOIN Meals m ON mp.meal_id = m.meal_id
            WHERE mp.user_id = %s
        ''', (user_id,))
        meals = cursor.fetchall()

        return jsonify({
            'username': user['username'],
            'meals': meals
        })
    except Exception as e:
        print("Error in my_account:", e)
        return jsonify({'error': 'Something went wrong'}), 500
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

if __name__ == '__main__':
    app.run(debug=True)
