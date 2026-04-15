# app.py
from flask import Flask, render_template, request, jsonify, send_file, url_for
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer
from datetime import datetime, timezone
from pymongo import MongoClient, DESCENDING
import hashlib
import random
import io
import os
import string
import secrets
from bson import ObjectId
import requests
from dictionary_service import dictionary_service

app = Flask(__name__)

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'fags62626sjjd@gmail.com'
app.config['MAIL_PASSWORD'] = os.getenv("MAIL_PASSWORD")
app.config['SECRET_KEY'] = 'your_secret_key_here'

mail = Mail(app)
s = URLSafeTimedSerializer(app.config['SECRET_KEY'])

PINYIN_RECORDS_COLLECTION = "pinyin_training_records"


DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")


print("檢查文件夾結構...")
print("當前目錄:", os.getcwd())
print("Templates 存在:", os.path.exists('templates'))
if os.path.exists('templates'):
    print("Templates 內容:", os.listdir('templates'))
else:
    print("警告: templates 文件夾不存在!")

try:
    # 3. 使用 MONGO_URI 連線 (這條路徑會自動適應本地或雲端)
    client = MongoClient(MONGO_URI)

    # 4. 指定 Database 名稱
    # 如果你在 Atlas 叫 mandarin_practice，這裡就維持不變
    db = client['mandarin_practice']

    users = db["users"]
    listening_records = db["listening_records"]
    speaking_records = db["speaking_records"]
    vocabulary = db["vocabulary"]
    pinyin_exercises = db["pinyin_exercises"]
    listening_exercises = db["listening_exercises"]
    custom_reading = db["custom_reading"]
    pinyin_training_records = db["pinyin_training_records"]
    user_login_stats = db["user_login_stats"]

    # 測試連線
    client.admin.command('ping')
    MONGO_ENABLED = True
    print("MongoDB 連接成功 (已連至:", "雲端 Atlas" if "mongodb+srv" in MONGO_URI else "本地 Localhost", ")")

    vocab_count = vocabulary.count_documents({})
    print(f"詞彙庫中的詞彙數量: {vocab_count}")

except Exception as e:
    print(f"MongoDB 連接失敗: {e}")
    MONGO_ENABLED = False


try:
    from ai_generator import cantonese_ai_generator

    AI_ENABLED = True
    print("AI 對話生成模塊加載成功")

    if DEEPSEEK_API_KEY and DEEPSEEK_API_KEY != "sk-0c0e59a5dab":
        cantonese_ai_generator.set_api_key(DEEPSEEK_API_KEY)
        print("DeepSeek API 密鑰已設置")
    else:
        print("請設置有效的 DeepSeek API 密鑰")

except ImportError as e:
    print(f"AI 對話生成模塊加載失敗: {e}")
    AI_ENABLED = False


try:
    from voice_service import voice_service

    VOICE_ENABLED = True
    print("語音服務模塊加載成功")
except ImportError as e:
    print(f"語音服務模塊加載失敗: {e}")
    VOICE_ENABLED = False



def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def create_user(username, password , email):
    if not MONGO_ENABLED:
        return {"success": False, "error": "數據庫未連接"}

    try:
        if users.find_one({"username": username}):
            return {"success": False, "error": "用戶名已存在"}

        if users.find_one({"email": email}):
            return {"success": False, "error": "郵箱已存在"}

        user_data = {
            "username": username,
            "password": hash_password(password),
            "email": email,
            "role": "user",
            "is_active": False,
            "is_locked": False,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now()
        }

        result = users.insert_one(user_data)
        return {"success": True, "user_id": str(result.inserted_id)}

    except Exception as e:
        print(f"創建用戶失敗: {e}")
        return {"success": False, "error": str(e)}


def verify_user(username, password):
    if not MONGO_ENABLED:
        return {"success": False, "error": "數據庫未連接"}

    try:
        hashed_password = hash_password(password)

        user = users.find_one({"username": username})
        if user:
            if user.get('is_locked', False):
                return {"success": False, "error": "帳號已被鎖定，請聯繫管理員"}

        user = users.find_one({
            "username": username,
            "password": hashed_password
        })

        if user:
            return {
                "success": True,
                "user_id": str(user["_id"]),
                "username": user["username"],
                "role": user.get("role", "user"),
                "is_locked": user.get("is_locked", False)
            }
        else:
            return {"success": False, "error": "用戶名或密碼錯誤"}

    except Exception as e:
        print(f"用戶驗證失敗: {e}")
        return {"success": False, "error": str(e)}


def update_login_stats(user_id):

    if not MONGO_ENABLED:
        return

    try:
        today = datetime.now().strftime('%Y-%m-%d')


        user_login_stats.update_one(
            {"user_id": user_id},
            {
                "$inc": {"total_logins": 1, f"daily_logins.{today}": 1},
                "$set": {"last_login": datetime.now()},
                "$setOnInsert": {"created_at": datetime.now()}
            },
            upsert=True
        )
    except Exception as e:
        print(f"更新登入統計失敗: {e}")


def mark_test_completed(user_id):

    if not MONGO_ENABLED:
        return

    try:
        user_login_stats.update_one(
            {"user_id": user_id},
            {"$set": {"test_completed": True, "test_completed_at": datetime.now()}},
            upsert=True
        )
    except Exception as e:
        print(f"標記測試完成失敗: {e}")


def has_completed_test(user_id):

    if not MONGO_ENABLED:
        return False

    try:
        stats = user_login_stats.find_one({"user_id": user_id})
        return stats.get("test_completed", False) if stats else False
    except Exception as e:
        print(f"檢查測試狀態失敗: {e}")
        return False

def get_random_vocabulary():

    if not MONGO_ENABLED:
        print("數據庫未連接，使用備用詞彙")
        return None

    try:
        pipeline = [{"$sample": {"size": 1}}]
        result = list(vocabulary.aggregate(pipeline))

        if result:
            print(f"從數據庫獲取詞彙: {result[0]['word']}")
            return result[0]
        else:
            print("數據庫中沒有詞彙")
            return None

    except Exception as e:
        print(f"獲取詞彙失敗: {e}")
        return None


def get_user_level(user_id):

    if not MONGO_ENABLED:
        return 1

    try:

        pinyin_records = list(pinyin_training_records.find({"user_id": user_id}))
        pinyin_total = len(pinyin_records)
        pinyin_correct = sum(1 for r in pinyin_records if r.get('is_correct', False))
        pinyin_accuracy = (pinyin_correct / pinyin_total * 100) if pinyin_total > 0 else 0

        if pinyin_accuracy < 70:
            return 1


        speaking_records_list = list(speaking_records.find({"user_id": user_id}))
        speaking_total = len(speaking_records_list)
        speaking_correct = sum(1 for r in speaking_records_list if r.get('accuracy', 0) >= 70)
        speaking_accuracy = (speaking_correct / speaking_total * 100) if speaking_total > 0 else 0

        if speaking_accuracy < 70:
            return 2


        listening_records_list = list(listening_records.find({"user_id": user_id}))
        listening_total = len(listening_records_list)
        listening_correct = sum(1 for r in listening_records_list if r.get('is_correct', False))
        listening_accuracy = (listening_correct / listening_total * 100) if listening_total > 0 else 0

        if listening_accuracy < 70:
            return 3


        return 4

    except Exception as e:
        print(f"獲取用戶等級失敗: {e}")
        return 1


def get_level_tasks(user_id):

    current_level = get_user_level(user_id)

    tasks = []


    if current_level == 1:
        tasks.append({
            "level": 1,
            "name": "拼音基礎訓練",
            "url": "/pinyinTraining",
            "description": "聲母、韻母單獨練習，打好發音基礎",
            "target": "準確率 ≥ 70%"
        })

    elif current_level == 2:
        tasks.append({
            "level": 2,
            "name": "說話發音練習",
            "url": "/speaking",
            "description": "大聲朗讀詞語，AI評估發音準確度",
            "target": "準確率 ≥ 70%"
        })

    elif current_level == 3:
        tasks.append({
            "level": 3,
            "name": "聆聽理解練習",
            "url": "/listening",
            "description": "聆聽AI對話，回答問題測試理解",
            "target": "準確率 ≥ 70%"
        })

    else:
        tasks.append({
            "level": 4,
            "name": "散文朗讀表達",
            "url": "/prose_reading",
            "description": "朗讀完整文章，提升綜合表達能力",
            "target": "完成進階練習"
        })

    return tasks, current_level


# 基本頁面路由
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/listening')
def listening():
    return render_template('listening.html')


@app.route('/speaking')
def speaking():
    return render_template('speaking.html')


@app.route('/tones')
def tones():
    return render_template('tones.html')


@app.route('/initialsTraining')
def initialsTraining():
    return render_template('initialsTraining.html')


@app.route('/tonesTraining')
def tonesTraining():
    return render_template('tonesTraining.html')


@app.route('/pinyinTraining')
def pinyinTraining():
    return render_template('pinyinTraining.html')


@app.route('/test')
def test_page():
    return render_template('test.html')

@app.route('/contactus')
def contactus():
    return render_template('contactus.html')

@app.route('/password')
def password():
    return render_template('password.html')

@app.route('/rank')
def rank_page():
    return render_template('rank.html')

@app.route('/staff_rank')
def staff_rank():
    return render_template('staffRank.html')

@app.route('/pinyin')
def pinyin():
    initials = ["b", "p", "m", "f", "d", "t", "n", "l", "g", "k", "h", "j", "q", "x", "zh", "ch", "sh", "r", "z", "c",
                "s", "y", "w"]
    finals = ["a", "o", "e", "i", "u", "ü", "ai", "ei", "ui", "ao", "ou", "iu", "ie", "üe", "er", "an", "en", "in",
              "un", "ün", "ang", "eng", "ing", "ong"]
    return render_template('pinyin.html', initials=initials, finals=finals)



@app.route('/register', methods=['POST'])
def register_user():
    try:
        data = request.get_json()
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')

        if not all([username, email, password]):
            return jsonify({'success': False, 'error': '請填寫所有欄位'})

        if users.find_one({"$or": [{"username": username}, {"email": email}]}):
            return jsonify({'success': False, 'error': '用戶名或 Email 已被註冊'})

        hashed_password = hashlib.sha256(password.encode()).hexdigest()

        new_user = {
            "username": username,
            "email": email,
            "password": hashed_password,
            "role": "user",
            "is_active": False,
            "is_locked": False,
            "created_at": datetime.now(timezone.utc)
        }
        users.insert_one(new_user)

        token = s.dumps(email, salt='email-confirm')
        confirm_url = url_for('confirm_email', token=token, _external=True)

        msg = Message('【普通話練習平台】帳號驗證信',
                      sender=app.config['MAIL_USERNAME'],
                      recipients=[email])
        msg.body = f'您好 {username}，請點擊以下連結以驗證您的帳號：\n\n{confirm_url}'

        mail.send(msg)
        return jsonify({"success": True, "message": "驗證郵件已發送，請檢查您的信箱！"})

    except Exception as e:
        print(f"註冊出錯: {e}")
        return jsonify({"success": False, "error": str(e)})


@app.route('/login', methods=['POST'])
def login_user():
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')

        if not all([username, password]):
            return jsonify({'success': False, 'error': '請填寫所有欄位'})

        user = users.find_one({"username": username})

        if not user:
            return jsonify({'success': False, 'error': '用戶名或密碼錯誤'})


        if not user.get('is_active', True):
            return jsonify({'success': False, 'error': '帳號尚未驗證，請先查看 Email'})


        if user.get('is_locked', False):
            return jsonify({'success': False, 'error': '帳號已被鎖定'})

        result = verify_user(username, password)

        if result['success']:

            update_login_stats(result['user_id'])


            test_completed = has_completed_test(result['user_id'])
            result['test_completed'] = test_completed

        return jsonify(result)

    except Exception as e:
        print(f"登入失敗錯誤: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/staff_login', methods=['POST'])
def staff_login_user():
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')

        result = verify_user(username, password)

        if result['success']:
            user = users.find_one({"username": username})
            if user:
                result['role'] = user.get('role', 'user')
                result['is_locked'] = user.get('is_locked', False)

                if result.get('role') != 'staff':
                    return jsonify({'success': False, 'error': '此帳號不是職員帳號'})

            print(f"職員 {username} 登入成功")

        return jsonify(result)

    except Exception as e:
        print(f"職員登入失敗: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/user_stats/<user_id>')
def get_user_stats(user_id):

    try:
        level = get_user_level(user_id)
        return jsonify({'level': level})
    except Exception as e:
        print(f"獲取用戶統計失敗: {e}")
        return jsonify({'level': 1})


@app.route('/user_info/<user_id>')
def get_user_info(user_id):

    try:
        if not MONGO_ENABLED:
            return jsonify({'success': False, 'error': '數據庫未連接'})

        user = users.find_one({"_id": ObjectId(user_id)})
        level = get_user_level(user_id)

        if user:
            return jsonify({
                'success': True,
                'user_id': str(user['_id']),
                'username': user['username'],
                'role': user.get('role', 'user'),
                'level': level,
                'is_locked': user.get('is_locked', False)
            })
        else:
            return jsonify({'success': False, 'error': '用戶不存在'})
    except Exception as e:
        print(f"獲取用戶資訊失敗: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/user_level/<user_id>')
def get_user_level_api(user_id):

    try:
        level = get_user_level(user_id)
        tasks, current_level = get_level_tasks(user_id)
        return jsonify({
            'success': True,
            'level': level,
            'tasks': tasks,
            'current_level': current_level
        })
    except Exception as e:
        print(f"獲取用戶等級失敗: {e}")
        return jsonify({'success': False, 'error': str(e), 'level': 1, 'tasks': [], 'current_level': 1})


@app.route('/user_records/<user_id>')
def get_user_records(user_id):

    try:
        listening_records_list = list(listening_records.find({"user_id": user_id}).sort("created_at", -1).limit(50))
        speaking_records_list = list(speaking_records.find({"user_id": user_id}).sort("created_at", -1).limit(50))
        pinyin_records_list = list(pinyin_training_records.find({"user_id": user_id}).sort("created_at", -1).limit(50))

        formatted_listening = []
        for record in listening_records_list:
            formatted_listening.append({
                'id': str(record['_id']),
                'topic': record.get('topic', '未知主題'),
                'is_correct': record.get('is_correct', False),
                'created_at': record['created_at'].strftime('%Y-%m-%d %H:%M:%S')
            })

        formatted_speaking = []
        for record in speaking_records_list:
            formatted_speaking.append({
                'id': str(record['_id']),
                'word': record.get('word', '未知詞語'),
                'accuracy': record.get('accuracy', 0),
                'created_at': record['created_at'].strftime('%Y-%m-%d %H:%M:%S')
            })

        formatted_pinyin = []
        for record in pinyin_records_list:
            formatted_pinyin.append({
                'id': str(record['_id']),
                'char': record.get('char', '未知'),
                'is_correct': record.get('is_correct', False),
                'created_at': record['created_at'].strftime('%Y-%m-%d %H:%M:%S')
            })

        return jsonify({
            'success': True,
            'listening_records': formatted_listening,
            'speaking_records': formatted_speaking,
            'pinyin_records': formatted_pinyin
        })
    except Exception as e:
        print(f"獲取用戶記錄失敗: {e}")
        return jsonify({'success': False, 'error': str(e)})


# 說話練習路由
@app.route('/get_vocabulary', methods=['GET'])
def get_vocabulary():

    try:
        vocab = get_random_vocabulary()
        if vocab:
            return jsonify({
                'word': vocab['word'],
                'pinyin': vocab.get('pinyin', ''),
                'category': vocab.get('category', '')
            })
        else:
            backup_words = ["你好", "謝謝", "再見", "老師", "學生", "中國", "北京", "上海", "廣東", "香港"]
            word = random.choice(backup_words)
            print(f"使用備用詞彙: {word}")
            return jsonify({'word': word})

    except Exception as e:
        print(f"獲取詞彙失敗: {e}")
        backup_words = ["你好", "謝謝", "再見", "老師", "學生"]
        word = random.choice(backup_words)
        return jsonify({'word': word})


@app.route('/start_recording', methods=['POST'])
def start_recording():
    try:
        data = request.get_json()
        duration = data.get('duration', 15)
        target_word = data.get('target_word', '')

        print(f"收到普通話錄音請求: 時長={duration}秒, 目標詞='{target_word}'")

        if VOICE_ENABLED:
            transcription, confidence = voice_service.transcribe_audio(
                duration=duration,
                target_word=target_word
            )
        else:
            transcription = target_word
            confidence = random.uniform(80, 95)

        print(f"普通話識別完成: '{transcription}' (置信度: {confidence:.1f}%)")

        return jsonify({
            'success': True,
            'transcription': transcription,
            'confidence': confidence
        })

    except Exception as e:
        print(f"錄音過程出錯: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        })


@app.route('/evaluate_pronunciation', methods=['POST'])
def evaluate_pronunciation():
    try:
        data = request.get_json()
        user_text = data.get('user_text', '')
        target_text = data.get('target_text', '')

        print(f"評估發音: 用戶說='{user_text}', 目標='{target_text}'")

        if VOICE_ENABLED:
            result = voice_service.evaluate_pronunciation(user_text, target_text)
        else:
            accuracy = random.uniform(70, 95)
            result = {
                'accuracy': round(accuracy, 1),
                'user_text': user_text,
                'target_text': target_text,
                'feedback': '發音不錯，繼續努力！' if accuracy > 80 else '發音需要改進，多練習幾次'
            }

        return jsonify({
            'success': True,
            'result': result
        })

    except Exception as e:
        print(f"評估發音失敗: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        })


def save_speaking_record(user_id, word, score, accuracy, exercise_data):

    if not MONGO_ENABLED:
        return False

    try:
        record = {
            "user_id": user_id,
            "word": word,
            "score": score,
            "accuracy": accuracy,
            "exercise_data": exercise_data,
            "created_at": datetime.now()
        }

        result = speaking_records.insert_one(record)
        return result.inserted_id is not None

    except Exception as e:
        print(f"保存說話記錄失敗: {e}")
        return False


@app.route('/save_speaking_record', methods=['POST'])
def save_speaking_record_route():
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        word = data.get('word')
        accuracy = data.get('accuracy', 0)
        user_pronunciation = data.get('user_pronunciation')
        target_pronunciation = data.get('target_pronunciation')
        feedback = data.get('feedback', '')

        if not all([user_id, word]):
            return jsonify({'success': False, 'error': '缺少必要參數'})

        exercise_data = {
            'user_pronunciation': user_pronunciation,
            'target_pronunciation': target_pronunciation,
            'feedback': feedback,
            'accuracy': accuracy
        }

        score = accuracy

        success = save_speaking_record(user_id, word, score, accuracy, exercise_data)
        return jsonify({'success': success})

    except Exception as e:
        print(f"保存說話記錄失敗: {e}")
        return jsonify({'success': False, 'error': str(e)})


# 重置密碼路由
@app.route('/reset_password', methods=['POST'])
def reset_password():

    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        old_password = data.get('old_password', '')
        new_password = data.get('new_password', '')

        if not MONGO_ENABLED:
            return jsonify({'success': False, 'error': '數據庫未連接'})

        if not username or not old_password or not new_password:
            return jsonify({'success': False, 'error': '請填寫所有欄位'})

        if len(new_password) < 6:
            return jsonify({'success': False, 'error': '新密碼至少需要 6 個字符'})

        user = users.find_one({"username": username})
        if not user:
            return jsonify({'success': False, 'error': '用戶不存在'})

        old_hashed = hash_password(old_password)
        if user.get("password") != old_hashed:
            return jsonify({'success': False, 'error': '舊密碼不正確'})

        new_hashed = hash_password(new_password)

        if old_hashed == new_hashed:
            return jsonify({'success': False, 'error': '新密碼不能與舊密碼相同'})

        result = users.update_one(
            {"username": username},
            {
                "$set": {
                    "password": new_hashed,
                    "updated_at": datetime.now()
                }
            }
        )

        if result.modified_count > 0:
            return jsonify({'success': True, 'message': '密碼修改成功'})
        else:
            return jsonify({'success': False, 'error': '密碼未修改，請稍後再試'})

    except Exception as e:
        print(f"重置密碼失敗: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/dictionary')
def dictionary():
    return render_template('dictionary.html')


# 字典服務
try:
    from dictionary_service import dictionary_service

    DICTIONARY_ENABLED = True
    print("字典服務模塊加載成功")
except ImportError as e:
    print(f"字典服務模塊加載失敗: {e}")
    DICTIONARY_ENABLED = False


@app.route('/search_dictionary', methods=['POST'])
def search_dictionary():
    try:
        data = request.get_json()
        word = data.get('word', '').strip()

        if not word:
            return jsonify({'success': False, 'error': '請輸入要查詢的詞語'})

        print(f"字典查詢: {word}")

        if not DICTIONARY_ENABLED:
            return jsonify({
                'success': False,
                'error': '字典服務暫時不可用'
            })

        result = dictionary_service.search_word(word)
        return jsonify(result)

    except Exception as e:
        print(f"字典查詢失敗: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/generate_listening', methods=['POST'])
def generate_listening():
    try:
        data = request.json
        topic = data.get('topic', '學習')
        api_key = os.getenv("DEEPSEEK_API_KEY")  # 確保 Render 有填呢個

        if not api_key:
            return jsonify({"success": False, "error": "API Key 未設定"}), 500

        # 直接用 requests 呼叫，唔使裝複雜嘅 SDK，最啱 Render 免費版/Starter 版
        response = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": "你是一個普通話老師。請根據主題生成一段A和B的對話，並出一個選擇題。"},
                    {"role": "user", "content": f"主題：{topic}"}
                ],
                "response_format": {"type": "json_object"}  # 如果你想要 JSON 回傳
            },
            timeout=30
        )

        result = response.json()
        # 這裡根據你前端需要的格式來 return 內容
        # ... (解析 result 並 return)
        return jsonify(
            {"success": True, "dialogue": "...", "question": "...", "options": [...], "correct_answer": "..."})

    except Exception as e:
        print(f"Error: {str(e)}")  # 呢句會顯示喺 Render Logs
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/save_listening_record', methods=['POST'])
def save_listening_record():

    try:
        data = request.get_json()
        user_id = data.get('user_id')
        topic = data.get('topic')
        exercise_id = data.get('exercise_id')
        user_answer = data.get('user_answer')
        correct_answer = data.get('correct_answer')
        question = data.get('question')
        is_correct = data.get('is_correct', False)
        options = data.get('options', [])
        dialogue = data.get('dialogue', '')

        if not all([user_id, topic]):
            return jsonify({'success': False, 'error': '缺少必要參數'})

        record = {
            "user_id": user_id,
            "topic": topic,
            "exercise_id": exercise_id,
            "question": question,
            "user_answer": user_answer,
            "correct_answer": correct_answer,
            "options": options,
            "dialogue": dialogue,
            "is_correct": is_correct,
            "score": 100 if is_correct else 0,
            "created_at": datetime.now()
        }

        result = listening_records.insert_one(record)

        print(f"聆聽記錄已保存: {result.inserted_id}, 是否正確: {is_correct}")

        return jsonify({'success': True, 'record_id': str(result.inserted_id)})

    except Exception as e:
        print(f"保存聆聽記錄失敗: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/retry_listening', methods=['POST'])
def retry_listening():

    try:
        data = request.get_json()
        exercise_id = data.get('exercise_id')

        if not exercise_id:
            return jsonify({'success': False, 'error': '缺少練習ID'})

        from bson import ObjectId
        exercise = listening_exercises.find_one({'_id': ObjectId(exercise_id)})

        if not exercise:
            return jsonify({'success': False, 'error': '題目不存在'})

        print(f"重做聆聽練習: {exercise_id}")

        return jsonify({
            'success': True,
            'exercise_id': str(exercise['_id']),
            'dialogue': exercise['dialogue'],
            'question': exercise['question'],
            'options': exercise['options'],
            'correct_answer': exercise['correct_answer']
        })

    except Exception as e:
        print(f"重做失敗: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/pinyin_practice')
def pinyin_practice():
    return render_template('pinyin_practice.html')


def serialize_mongo_document(doc):

    if not doc:
        return doc

    if isinstance(doc, dict):
        result = {}
        for key, value in doc.items():
            if key == '_id':
                result[key] = str(value)
            elif isinstance(value, ObjectId):
                result[key] = str(value)
            elif isinstance(value, dict):
                result[key] = serialize_mongo_document(value)
            elif isinstance(value, list):
                result[key] = [serialize_mongo_document(item) if isinstance(item, dict) else item for item in value]
            elif isinstance(value, datetime):
                result[key] = value.isoformat()
            else:
                result[key] = value
        return result
    elif isinstance(doc, list):
        return [serialize_mongo_document(item) if isinstance(item, dict) else item for item in doc]
    return doc


@app.route('/get_pinyin_exercise', methods=['POST'])
def get_pinyin_exercise():
    try:
        data = request.get_json()
        difficulty = data.get('difficulty', 'easy')
        exercise_type = data.get('type', None)

        print(f"收到拼音練習要求: {difficulty}, type: {exercise_type}")

        if not MONGO_ENABLED:
            print("MongoDB 未connect")
            return jsonify({'success': False, 'error': '數據庫未連接'})

        query = {"difficulty": difficulty}

        if difficulty == "easy" and exercise_type:
            if exercise_type == "initial":
                query["type"] = "initials"
            elif exercise_type == "final":
                query["type"] = "finals"

        print(f"查询条件: {query}")

        pipeline = [
            {"$match": query},
            {"$sample": {"size": 1}}
        ]

        result = list(pinyin_exercises.aggregate(pipeline))
        print(f"數量: {len(result)}")

        if result:
            exercise = result[0]
            print(f"練習為: {exercise.get('char', exercise.get('sentence', '未知'))}")

            exercise = serialize_mongo_document(exercise)

            response_data = {
                "success": True,
                "difficulty": difficulty,
                "exercise": exercise
            }

            if difficulty == "easy":
                if exercise_type == "initial":
                    response_data["char"] = exercise["char"]
                    response_data["hint"] = get_tone_mark(exercise["final"], exercise.get("tone", 1))
                    response_data["correct_answer"] = exercise["initial"]
                    response_data["exercise_type"] = "initial"
                elif exercise_type == "final":
                    response_data["char"] = exercise["char"]
                    response_data["hint"] = exercise["initial"] or "(無聲母)"
                    response_data["correct_answer"] = exercise["final"]
                    response_data["exercise_type"] = "final"

            elif difficulty == "medium":
                response_data["char"] = exercise["char"]
                response_data["correct_answer"] = exercise["noTonePinyin"]

            elif difficulty == "hard":
                response_data["sentence"] = exercise["sentence"]
                response_data["words"] = exercise["words"]

            return jsonify(response_data)
        else:
            print(f"未找到對應題目 : {difficulty}, type: {exercise_type}")

            if difficulty == "easy":
                default_exercise = {
                    "char": "爸",
                    "initial": "b",
                    "final": "a",
                    "tone": 4,
                    "pinyin": "ba4"
                }
                response_data = {
                    "success": True,
                    "difficulty": difficulty,
                    "exercise": default_exercise
                }
                if exercise_type == "initial":
                    response_data["char"] = default_exercise["char"]
                    response_data["hint"] = get_tone_mark(default_exercise["final"], default_exercise.get("tone", 1))
                    response_data["correct_answer"] = default_exercise["initial"]
                    response_data["exercise_type"] = "initial"
                elif exercise_type == "final":
                    response_data["char"] = default_exercise["char"]
                    response_data["hint"] = default_exercise["initial"] or "(無聲母)"
                    response_data["correct_answer"] = default_exercise["final"]
                    response_data["exercise_type"] = "final"
                return jsonify(response_data)
            else:
                return jsonify({'success': False, 'error': '未找到相應難度的練習題'})

    except Exception as e:
        print(f"獲取拼音練習題失敗: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/check_pinyin_data', methods=['GET'])
def check_pinyin_data():

    try:
        if not MONGO_ENABLED:
            return jsonify({'success': False, 'error': 'MongoDB 未連接'})

        total = pinyin_exercises.count_documents({})
        easy_initials = pinyin_exercises.count_documents({"difficulty": "easy", "type": "initials"})
        easy_finals = pinyin_exercises.count_documents({"difficulty": "easy", "type": "finals"})
        medium = pinyin_exercises.count_documents({"difficulty": "medium"})
        hard = pinyin_exercises.count_documents({"difficulty": "hard"})

        sample_easy_initials = list(pinyin_exercises.find({"difficulty": "easy", "type": "initials"}).limit(3))
        sample_easy_finals = list(pinyin_exercises.find({"difficulty": "easy", "type": "finals"}).limit(3))

        sample_easy_initials = serialize_mongo_document(sample_easy_initials)
        sample_easy_finals = serialize_mongo_document(sample_easy_finals)

        return jsonify({
            'success': True,
            'total_count': total,
            'easy_initials_count': easy_initials,
            'easy_finals_count': easy_finals,
            'medium_count': medium,
            'hard_count': hard,
            'sample_easy_initials': sample_easy_initials,
            'sample_easy_finals': sample_easy_finals
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


def get_tone_mark(final, tone):
    if not final or tone < 1 or tone > 4:
        return final

    tone_marks = {
        1: {'a': 'ā', 'e': 'ē', 'i': 'ī', 'o': 'ō', 'u': 'ū', 'ü': 'ǖ'},
        2: {'a': 'á', 'e': 'é', 'i': 'í', 'o': 'ó', 'u': 'ú', 'ü': 'ǘ'},
        3: {'a': 'ǎ', 'e': 'ě', 'i': 'ǐ', 'o': 'ǒ', 'u': 'ǔ', 'ü': 'ǚ'},
        4: {'a': 'à', 'e': 'è', 'i': 'ì', 'o': 'ò', 'u': 'ù', 'ü': 'ǜ'}
    }

    main_vowels = ['a', 'e', 'i', 'o', 'u', 'ü']
    for vowel in main_vowels:
        if vowel in final:
            if tone in tone_marks and vowel in tone_marks[tone]:
                marked_vowel = tone_marks[tone][vowel]
                return final.replace(vowel, marked_vowel)

    return final


@app.route('/admin/dashboard')
def admin_dashboard():
    return render_template('adminDashboard.html')


@app.route('/admin/get_all_users', methods=['GET'])
def get_all_users():
    try:
        if not MONGO_ENABLED:
            return jsonify({'success': False, 'error': '數據庫未連接'})

        all_users = list(users.find({}, {
            '_id': 1,
            'username': 1,
            'role': 1,
            'is_locked': 1,
            'created_at': 1
        }).sort('created_at', DESCENDING))

        formatted_users = []
        for user in all_users:
            formatted_users.append({
                'id': str(user['_id']),
                'username': user['username'],
                'role': user.get('role', 'user'),
                'is_locked': user.get('is_locked', False),
                'created_at': user['created_at'].strftime('%Y-%m-%d %H:%M:%S')
            })

        return jsonify({'success': True, 'users': formatted_users})

    except Exception as e:
        print(f"獲取用戶列表失敗: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/admin/update_user', methods=['POST'])
def update_user():
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        action = data.get('action')
        new_password = data.get('new_password', None)

        if not all([user_id, action]):
            return jsonify({'success': False, 'error': ''})

        update_data = {}

        if action == 'lock':
            update_data['is_locked'] = True
        elif action == 'unlock':
            update_data['is_locked'] = False
        elif action == 'reset_password':
            if not new_password:
                return jsonify({'success': False, 'error': 'please input new password'})
            update_data['password'] = hash_password(new_password)

        update_data['updated_at'] = datetime.now()

        result = users.update_one(
            {'_id': ObjectId(user_id)},
            {'$set': update_data}
        )

        if result.modified_count > 0:
            return jsonify({'success': True, 'message': 'update successful'})
        else:
            return jsonify({'success': False, 'error': 'User does not exist or information has not been changed.'})

    except Exception as e:
        print(f"update user fail: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/wrong_questions')
def wrong_questions_page():

    return render_template('wrong_questions.html')


@app.route('/api/wrong_questions/<user_id>', methods=['GET'])
def api_get_wrong_questions(user_id):

    try:
        wrong_questions = []

        if MONGO_ENABLED:
            listening_wrong = list(listening_records.find({
                "user_id": user_id,
                "is_correct": False
            }).sort("created_at", -1).limit(50))

            for record in listening_wrong:
                wrong_questions.append({
                    'id': str(record['_id']),
                    'exercise_id': record.get('exercise_id', ''),
                    'question_type': 'listening',
                    'question': record.get('question', '未知題目'),
                    'user_answer': record.get('user_answer', '(未填寫)'),
                    'correct_answer': record.get('correct_answer', ''),
                    'score': record.get('score', 0),
                    'topic': record.get('topic', '未知主題'),
                    'created_at': record['created_at'].strftime('%Y-%m-%d %H:%M:%S')
                })

            speaking_wrong = list(speaking_records.find({
                "user_id": user_id,
                "accuracy": {"$lt": 70}
            }).sort("created_at", -1).limit(50))

            for record in speaking_wrong:
                wrong_questions.append({
                    'id': str(record['_id']),
                    'question_type': 'speaking',
                    'question': f"發音練習：{record.get('word', '未知詞語')}",
                    'user_answer': record.get('exercise_data', {}).get('user_pronunciation', ''),
                    'correct_answer': record.get('word', ''),
                    'score': record.get('score', 0),
                    'accuracy': record.get('accuracy', 0),
                    'created_at': record['created_at'].strftime('%Y-%m-%d %H:%M:%S')
                })

            pinyin_wrong = list(pinyin_training_records.find({
                "user_id": user_id,
                "is_correct": False
            }).sort("created_at", -1).limit(50))

            for record in pinyin_wrong:
                wrong_questions.append({
                    'id': str(record['_id']),
                    'question_type': 'pinyin',
                    'difficulty': record.get('difficulty'),
                    'question': record.get('char', '拼音練習'),
                    'user_answer': record.get('user_answer', ''),
                    'correct_answer': record.get('correct_answer', ''),
                    'score': record.get('score', 0),
                    'created_at': record['created_at'].strftime('%Y-%m-%d %H:%M:%S')
                })

            wrong_questions.sort(key=lambda x: x['created_at'], reverse=True)

        # 計算統計資料
        stats = {
            'total': len(wrong_questions),
            'listening': len([q for q in wrong_questions if q.get('question_type') == 'listening']),
            'speaking': len([q for q in wrong_questions if q.get('question_type') == 'speaking']),
            'pinyin': len([q for q in wrong_questions if q.get('question_type') == 'pinyin'])
        }

        return jsonify({
            'success': True,
            'records': wrong_questions,
            'stats': stats
        })

    except Exception as e:
        print(f"獲取錯題失敗: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'records': [],
            'stats': {'total': 0, 'listening': 0, 'speaking': 0, 'pinyin': 0}
        })


@app.route('/save_pinyin_training_record', methods=['POST'])
def save_pinyin_training_record():

    try:
        data = request.get_json()
        user_id = data.get('user_id')
        difficulty = data.get('difficulty')
        practice_type = data.get('practice_type')
        char = data.get('char')
        sentence = data.get('sentence')
        user_answer = data.get('user_answer')
        correct_answer = data.get('correct_answer')
        is_correct = data.get('is_correct', False)
        attempts = data.get('attempts', 1)
        word_list = data.get('word_list')

        if not all([user_id, difficulty]):
            return jsonify({'success': False, 'error': '缺少必要參數'})

        record = {
            "user_id": user_id,
            "difficulty": difficulty,
            "practice_type": practice_type,
            "char": char,
            "sentence": sentence,
            "user_answer": user_answer,
            "correct_answer": correct_answer,
            "is_correct": is_correct,
            "score": 100 if is_correct else 0,
            "attempts": attempts,
            "word_list": word_list,
            "created_at": datetime.now()
        }

        result = pinyin_training_records.insert_one(record)

        print(f"拼音練習記錄已保存: {result.inserted_id}, 是否正確: {is_correct}")

        return jsonify({'success': True, 'record_id': str(result.inserted_id)})

    except Exception as e:
        print(f"保存拼音記錄失敗: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/get_pinyin_training_stats/<user_id>', methods=['GET'])
def get_pinyin_training_stats(user_id):

    if not MONGO_ENABLED:
        return jsonify({
            'total_practices': 0,
            'correct_answers': 0,
            'accuracy_rate': 0,
            'today_completed': 0
        })

    try:
        total_practices = pinyin_training_records.count_documents({"user_id": user_id})
        correct_answers = pinyin_training_records.count_documents({
            "user_id": user_id,
            "is_correct": True
        })

        accuracy_rate = round((correct_answers / total_practices * 100), 1) if total_practices > 0 else 0

        today = datetime.now().date()
        today_start = datetime.combine(today, datetime.min.time())
        today_completed = pinyin_training_records.count_documents({
            "user_id": user_id,
            "created_at": {"$gte": today_start}
        })

        return jsonify({
            'total_practices': total_practices,
            'correct_answers': correct_answers,
            'accuracy_rate': accuracy_rate,
            'today_completed': today_completed,
            'daily_goal': 20
        })

    except Exception as e:
        print(f"獲取拼音統計失敗: {e}")
        return jsonify({
            'total_practices': 0,
            'correct_answers': 0,
            'accuracy_rate': 0,
            'today_completed': 0,
            'daily_goal': 20
        })


@app.route('/get_pinyin_exercise_by_char', methods=['POST'])
def get_pinyin_exercise_by_char():

    try:
        data = request.get_json()
        difficulty = data.get('difficulty')
        char = data.get('char')

        if not MONGO_ENABLED:
            return jsonify({'success': False, 'error': '數據庫未連接'})

        query = {"difficulty": difficulty}

        if difficulty == "easy":
            query["char"] = char
            query["type"] = "initials" if data.get('type') == 'initial' else "finals"
        elif difficulty == "medium":
            query["char"] = char
        elif difficulty == "hard":
            query["sentence"] = char

        print(f"查詢拼音題目: {query}")

        exercise = pinyin_exercises.find_one(query)

        if exercise:
            exercise = serialize_mongo_document(exercise)

            response_data = {
                "success": True,
                "difficulty": difficulty,
                "exercise": exercise
            }

            if difficulty == "easy":
                final_with_tone = exercise.get('final', '')
                tone = exercise.get('tone', 1)
                if final_with_tone and tone:
                    final_with_tone = get_tone_mark(final_with_tone, tone)

                response_data["char"] = exercise["char"]
                response_data["hint"] = final_with_tone
                response_data["correct_answer"] = exercise["initial"] if data.get('type') == 'initial' else exercise[
                    "final"]
            elif difficulty == "medium":
                response_data["char"] = exercise["char"]
                response_data["correct_answer"] = exercise.get("noTonePinyin", exercise.get("pinyin", ""))

            return jsonify(response_data)
        else:
            print(f"找不到題目: {query}")
            return jsonify({'success': False, 'error': '找不到指定的題目'})

    except Exception as e:
        print(f"獲取指定拼音練習題失敗: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/get_vocabulary_by_initial', methods=['GET'])
def get_vocabulary_by_initial():

    try:
        initial = request.args.get('initial', '')

        if not MONGO_ENABLED:
            return jsonify({'error': '數據庫未連接'})

        pipeline = [
            {"$match": {"pinyin": {"$regex": f"^{initial}", "$options": "i"}}},
            {"$sample": {"size": 1}}
        ]

        result = list(vocabulary.aggregate(pipeline))

        if result:
            selected = result[0]
            selected = serialize_mongo_document(selected)
            return jsonify({
                'word': selected.get('word', ''),
                'pinyin': selected.get('pinyin', ''),
                'category': selected.get('category', '')
            })
        else:
            result = list(vocabulary.aggregate([{"$sample": {"size": 1}}]))
            if result:
                selected = serialize_mongo_document(result[0])
                return jsonify({
                    'word': selected.get('word', ''),
                    'pinyin': selected.get('pinyin', ''),
                    'category': selected.get('category', '')
                })
            else:
                return jsonify({'error': '詞彙庫為空'})

    except Exception as e:
        print(f"獲取聲母詞彙失敗: {e}")
        return jsonify({'error': str(e)})


@app.route('/get_vocabulary_by_final', methods=['GET'])
def get_vocabulary_by_final():

    try:
        final = request.args.get('final', '')

        if not MONGO_ENABLED:
            return jsonify({'error': '數據庫未連接'})

        pipeline = [
            {"$match": {"pinyin": {"$regex": final, "$options": "i"}}},
            {"$sample": {"size": 1}}
        ]

        result = list(vocabulary.aggregate(pipeline))

        if result:
            selected = result[0]
            selected = serialize_mongo_document(selected)
            return jsonify({
                'word': selected.get('word', ''),
                'pinyin': selected.get('pinyin', ''),
                'category': selected.get('category', '')
            })
        else:
            result = list(vocabulary.aggregate([{"$sample": {"size": 1}}]))
            if result:
                selected = serialize_mongo_document(result[0])
                return jsonify({
                    'word': selected.get('word', ''),
                    'pinyin': selected.get('pinyin', ''),
                    'category': selected.get('category', '')
                })
            else:
                return jsonify({'error': '詞彙庫為空'})

    except Exception as e:
        print(f"獲取韻母詞彙失敗: {e}")
        return jsonify({'error': str(e)})


@app.route('/get_vocabulary_by_word', methods=['GET'])
def get_vocabulary_by_word():

    try:
        word = request.args.get('word', '')

        if not MONGO_ENABLED:
            return jsonify({'error': '數據庫未連接'})

        result = vocabulary.find_one({"word": word})

        if result:
            return jsonify({
                'word': result.get('word', ''),
                'pinyin': result.get('pinyin', ''),
                'category': result.get('category', '')
            })
        else:
            return jsonify({'error': '找不到該詞語'})

    except Exception as e:
        print(f"獲取詞語拼音失敗: {e}")
        return jsonify({'error': str(e)})



@app.route('/prose_reading')
def prose_reading():

    return render_template('prose_reading.html')


@app.route('/api/get_all_prose')
def api_get_all_prose():

    try:
        if not MONGO_ENABLED:
            return jsonify({'success': False, 'error': '數據庫未連接'})

        prose_list = list(db["reading_materials"].find().sort("created_at", -1))
        prose_list = serialize_mongo_document(prose_list)

        print(f"找到 {len(prose_list)} 篇散文")

        return jsonify({'success': True, 'prose_list': prose_list})

    except Exception as e:
        print(f"取得散文列表失敗: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/get_prose/<prose_id>')
def api_get_prose(prose_id):

    try:
        if not MONGO_ENABLED:
            return jsonify({'success': False, 'error': '數據庫未連接'})

        from bson import ObjectId
        prose = db["reading_materials"].find_one({"_id": ObjectId(prose_id)})

        if prose:
            prose = serialize_mongo_document(prose)
            return jsonify({'success': True, 'prose': prose})
        else:
            return jsonify({'success': False, 'error': '散文不存在'})

    except Exception as e:
        print(f"取得散文失敗: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/save_prose_record', methods=['POST'])
def api_save_prose_record():

    try:
        data = request.get_json()
        user_id = data.get('user_id')
        prose_id = data.get('prose_id')
        sentence = data.get('sentence')
        user_text = data.get('user_text')
        target_text = data.get('target_text')
        accuracy = data.get('accuracy', 0)
        feedback = data.get('feedback', '')

        if not all([user_id, prose_id, sentence, target_text]):
            return jsonify({'success': False, 'error': '缺少必要參數'})

        if "prose_reading_records" not in db.list_collection_names():
            db.create_collection("prose_reading_records")

        record = {
            "user_id": user_id,
            "prose_id": prose_id,
            "sentence": sentence,
            "user_text": user_text,
            "target_text": target_text,
            "accuracy": accuracy,
            "feedback": feedback,
            "created_at": datetime.now()
        }

        result = db["prose_reading_records"].insert_one(record)

        print(f"散文朗讀記錄已儲存: {result.inserted_id}")
        return jsonify({'success': True, 'record_id': str(result.inserted_id)})

    except Exception as e:
        print(f"儲存朗讀記錄失敗: {e}")
        return jsonify({'success': False, 'error': str(e)})



@app.route('/custom_reading')
def custom_reading():
    return render_template('custom_reading.html')


@app.route('/api/generate_article', methods=['POST'])
def generate_article():
    try:
        data = request.get_json()
        topic = data.get('topic', '').strip()

        if not topic:
            return jsonify({'success': False, 'error': '請輸入主題'})

        if not AI_ENABLED:
            return jsonify({'success': False, 'error': 'AI 模塊未加載'})

        print(f"AI 生成文章，主題: {topic}")

        import requests

        prompt = f"""請用中文寫一篇約200字的短文，主題是「{topic}」。文章要適合普通話朗讀練習，內容通順、用詞適中。只輸出文章內容，不要有任何解釋或額外說明。"""

        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 500
        }

        response = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )

        if response.status_code == 200:
            result = response.json()
            article = result["choices"][0]["message"]["content"].strip()
            print(f"文章生成成功，長度: {len(article)}字")
            return jsonify({
                'success': True,
                'article': article,
                'topic': topic,
                'word_count': len(article)
            })
        else:
            print(f"API 錯誤: {response.status_code}")
            return jsonify({'success': False, 'error': f'AI 生成失敗: {response.status_code}'})

    except Exception as e:
        print(f"生成文章失敗: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/save_custom_article', methods=['POST'])
def save_custom_article():
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        username = data.get('username')
        title = data.get('title', '自訂文章')
        topic = data.get('topic', '')
        content = data.get('content', '')
        source_type = data.get('source_type', 'manual')

        if not content:
            return jsonify({'success': False, 'error': '文章內容不能為空'})

        if not user_id:
            return jsonify({'success': False, 'error': '請先登入'})

        if not MONGO_ENABLED:
            return jsonify({'success': False, 'error': '數據庫未連接'})

        if "custom_reading" not in db.list_collection_names():
            db.create_collection("custom_reading")

        import re
        sentences = re.split(r'[。！？；]', content)
        sentences = [s.strip() + '。' for s in sentences if s.strip() and len(s.strip()) > 0]

        if not sentences:
            sentences = [content]

        article_data = {
            "user_id": user_id,
            "username": username,
            "title": title,
            "topic": topic,
            "content": content,
            "sentences": sentences,
            "source_type": source_type,
            "word_count": len(content),
            "created_at": datetime.now(),
            "last_practiced_at": None,
            "practice_count": 0
        }

        result = db["custom_reading"].insert_one(article_data)
        article_id = str(result.inserted_id)

        print(f"自訂文章已保存: {article_id}, 標題: {title}")

        return jsonify({
            'success': True,
            'article_id': article_id,
            'title': title,
            'sentences': sentences,
            'word_count': len(content)
        })

    except Exception as e:
        print(f"保存文章失敗: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/get_user_custom_articles/<user_id>')
def get_user_custom_articles(user_id):

    try:
        if not MONGO_ENABLED:
            return jsonify({'success': False, 'error': '數據庫未連接'})

        articles = list(db["custom_reading"].find(
            {"user_id": user_id}
        ).sort("created_at", -1))

        articles = serialize_mongo_document(articles)

        return jsonify({
            'success': True,
            'articles': articles
        })

    except Exception as e:
        print(f"獲取文章列表失敗: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/get_custom_article/<article_id>')
def get_custom_article(article_id):

    try:
        if not MONGO_ENABLED:
            return jsonify({'success': False, 'error': '數據庫未連接'})

        from bson import ObjectId
        article = db["custom_reading"].find_one({"_id": ObjectId(article_id)})

        if article:
            article = serialize_mongo_document(article)
            return jsonify({
                'success': True,
                'article': {
                    '_id': article['_id'],
                    'title': article.get('title', '自訂文章'),
                    'content': article.get('content', ''),
                    'sentences': article.get('sentences', []),
                    'topic': article.get('topic', ''),
                    'word_count': article.get('word_count', 0),
                    'source_type': article.get('source_type', 'manual')
                }
            })
        else:
            return jsonify({'success': False, 'error': '文章不存在'})

    except Exception as e:
        print(f"獲取文章失敗: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/update_article_practice/<article_id>', methods=['POST'])
def update_article_practice(article_id):

    try:
        if not MONGO_ENABLED:
            return jsonify({'success': False, 'error': '數據庫未連接'})

        from bson import ObjectId

        result = db["custom_reading"].update_one(
            {"_id": ObjectId(article_id)},
            {
                "$set": {"last_practiced_at": datetime.now()},
                "$inc": {"practice_count": 1}
            }
        )

        return jsonify({'success': True})

    except Exception as e:
        print(f"更新練習記錄失敗: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/save_test_result', methods=['POST'])
def save_test_result():
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        test_data = data.get('test_data', {})

        if not user_id:
            return jsonify({'success': False, 'error': '未登入'})

        for wrong in test_data.get('pinyin', {}).get('wrong_list', []):
            pinyin_training_records.insert_one({
                "user_id": user_id,
                "difficulty": wrong.get('difficulty', 'easy'),
                "char": wrong.get('char', ''),
                "user_answer": wrong.get('user', ''),
                "correct_answer": wrong.get('correct', ''),
                "is_correct": False,
                "score": 0,
                "created_at": datetime.now()
            })

        mark_test_completed(user_id)

        return jsonify({'success': True, 'message': '測試結果已保存'})

    except Exception as e:
        print(f"保存測試結果失敗: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/confirm_email/<token>')
def confirm_email(token):
    try:
        email = s.loads(token, salt='email-confirm', max_age=3600)
    except Exception as e:
        print(f"Token 解密失敗: {e}")
        return '<h1>驗證連結已過期或無效</h1><a href="/">回到首頁</a>'

    result = users.update_one(
        {"email": email},
        {"$set": {"is_active": True}}
    )

    if result.modified_count > 0:
        return '<h1>驗證成功！</h1><p>您的帳號已激活，現在可以登入了。</p><a href="/">回到首頁</a>'

    user = users.find_one({"email": email})
    if user and user.get('is_active'):
        return '<h1>帳號先前已完成驗證</h1><p>請直接登入即可。</p><a href="/">回到首頁</a>'

    return '<h1>驗證失敗</h1><p>找不到對應的用戶資料，請聯繫管理員。</p><a href="/">回到首頁</a>'


@app.route('/api/forgot_password', methods=['POST'])
def forgot_password():
    data = request.json
    email = data.get('email')

    user = users.find_one({"email": email})
    if not user:
        return jsonify({'success': False, 'error': '找不到此 Email 關聯的用戶'})

    alphabet = string.ascii_letters + string.digits
    new_password = ''.join(secrets.choice(alphabet) for i in range(8))

    hashed_password = hashlib.sha256(new_password.encode()).hexdigest()

    try:
        users.update_one({"email": email}, {"$set": {"password": hashed_password}})

        msg = Message("您的新密碼 - 普通話練習平台",
                      sender=app.config['MAIL_USERNAME'],
                      recipients=[email])
        msg.body = f"""
        您好，{user['username']}：

        您在普通話練習平台申請了密碼重置。
        您的新密碼為：{new_password}

        請登入後儘快修改您的密碼。
        """
        mail.send(msg)

        return jsonify({'success': True})
    except Exception as e:
        print(f"發送密碼失敗: {e}")
        return jsonify({'success': False, 'error': '發送郵件失敗，請聯絡管理員'})

@app.route('/api/rankings', methods=['GET'])
def get_rankings():

    try:
        target_user_id = request.args.get('user_id')
        if not target_user_id:
            return jsonify({'success': False, 'error': '未提供使用者 ID'})

        if not MONGO_ENABLED:
            return jsonify({'success': False, 'error': '數據庫未連接'})

        from bson import ObjectId

        # 1. 拼音統計
        pinyin_pipeline = [
            {"$group": {
                "_id": "$user_id",
                "total": {"$sum": 1},
                "correct": {"$sum": {"$cond": ["$is_correct", 1, 0]}}
            }},
            {"$project": {
                "user_id": "$_id",
                "total": 1,
                "correct": 1,
                "accuracy": {
                    "$round": [
                        {"$multiply": [{"$divide": ["$correct", {"$max": ["$total", 1]}]}, 100]},
                        1
                    ]
                }
            }}
        ]
        pinyin_stats = list(pinyin_training_records.aggregate(pinyin_pipeline))
        pinyin_map = {s['user_id']: s for s in pinyin_stats}


        speaking_pipeline = [
            {"$group": {
                "_id": "$user_id",
                "total": {"$sum": 1},
                "avg_accuracy": {"$avg": "$accuracy"}
            }},
            {"$project": {
                "user_id": "$_id",
                "total": 1,
                "accuracy": {"$round": ["$avg_accuracy", 1]}
            }}
        ]
        speaking_stats = list(speaking_records.aggregate(speaking_pipeline))
        speaking_map = {s['user_id']: s for s in speaking_stats}


        listening_pipeline = [
            {"$group": {
                "_id": "$user_id",
                "total": {"$sum": 1},
                "correct": {"$sum": {"$cond": ["$is_correct", 1, 0]}}
            }},
            {"$project": {
                "user_id": "$_id",
                "total": 1,
                "correct": 1,
                "accuracy": {
                    "$round": [
                        {"$multiply": [{"$divide": ["$correct", {"$max": ["$total", 1]}]}, 100]},
                        1
                    ]
                }
            }}
        ]
        listening_stats = list(listening_records.aggregate(listening_pipeline))
        listening_map = {s['user_id']: s for s in listening_stats}


        all_users = list(users.find({}, {"_id": 1, "username": 1}))
        user_name_map = {str(u['_id']): u['username'] for u in all_users}


        pinyin_ranking = []
        for user_id, stat in pinyin_map.items():
            pinyin_ranking.append({
                "user_id": user_id,
                "username": user_name_map.get(user_id, "未知"),
                "accuracy": stat['accuracy'],
                "total": stat['total']
            })
        pinyin_ranking.sort(key=lambda x: (-x['accuracy'], -x['total']))

        speaking_ranking = []
        for user_id, stat in speaking_map.items():
            speaking_ranking.append({
                "user_id": user_id,
                "username": user_name_map.get(user_id, "未知"),
                "accuracy": stat['accuracy'],
                "total": stat['total']
            })
        speaking_ranking.sort(key=lambda x: (-x['accuracy'], -x['total']))

        listening_ranking = []
        for user_id, stat in listening_map.items():
            listening_ranking.append({
                "user_id": user_id,
                "username": user_name_map.get(user_id, "未知"),
                "accuracy": stat['accuracy'],
                "total": stat['total']
            })
        listening_ranking.sort(key=lambda x: (-x['accuracy'], -x['total']))


        if not users.find_one({"_id": ObjectId(target_user_id)}):
            return jsonify({'success': False, 'error': '使用者不存在'})

        target_user = users.find_one({"_id": ObjectId(target_user_id)})
        target_username = target_user['username']

        pinyin_target = pinyin_map.get(target_user_id, {"accuracy": 0, "total": 0, "correct": 0})
        speaking_target = speaking_map.get(target_user_id, {"accuracy": 0, "total": 0})
        listening_target = listening_map.get(target_user_id, {"accuracy": 0, "total": 0, "correct": 0})


        pinyin_rank = next((i+1 for i, u in enumerate(pinyin_ranking) if u['user_id'] == target_user_id), 1)
        speaking_rank = next((i+1 for i, u in enumerate(speaking_ranking) if u['user_id'] == target_user_id), 1)
        listening_rank = next((i+1 for i, u in enumerate(listening_ranking) if u['user_id'] == target_user_id), 1)

        return jsonify({
            'success': True,
            'view_user': {
                'user_id': target_user_id,
                'username': target_username,
                'pinyin': {
                    'accuracy': pinyin_target['accuracy'],
                    'total': pinyin_target['total'],
                    'correct': pinyin_target['correct']
                },
                'pinyin_rank': pinyin_rank,
                'speaking': {
                    'accuracy': speaking_target['accuracy'],
                    'total': speaking_target['total']
                },
                'speaking_rank': speaking_rank,
                'listening': {
                    'accuracy': listening_target['accuracy'],
                    'total': listening_target['total'],
                    'correct': listening_target['correct']
                },
                'listening_rank': listening_rank
            },
            'pinyin_ranking': pinyin_ranking,
            'speaking_ranking': speaking_ranking,
            'listening_ranking': listening_ranking
        })

    except Exception as e:
        print(f"排名API錯誤: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/all_pinyin_stats', methods=['GET'])
def get_all_pinyin_stats():
    try:
        if not MONGO_ENABLED:
            return jsonify({'success': False, 'error': '數據庫未連接', 'stats': []})

        pipeline = [
            {
                "$group": {
                    "_id": "$user_id",
                    "total": {"$sum": 1},
                    "total_score": {"$sum": "$score"}
                }
            },
            {
                "$project": {
                    "user_id": "$_id",
                    "total": 1,
                    "accuracy": {
                        "$round": [
                            {"$divide": ["$total_score", {"$max": ["$total", 1]}]},
                            1
                        ]
                    }
                }
            }
        ]

        results = list(pinyin_training_records.aggregate(pipeline))

        all_users = list(users.find({}, {'_id': 1, 'username': 1}))
        user_name_map = {str(u['_id']): u['username'] for u in all_users}

        formatted = []
        for r in results:
            user_id = r['user_id']
            formatted.append({
                'user_id': user_id,
                'username': user_name_map.get(user_id, '未知用戶'),
                'accuracy': r.get('accuracy', 0),
                'total': r.get('total', 0)
            })

        return jsonify({'success': True, 'stats': formatted})

    except Exception as e:
        print(f"獲取拼音統計失敗: {e}")
        return jsonify({'success': False, 'error': str(e), 'stats': []})


@app.route('/api/all_speaking_stats', methods=['GET'])
def get_all_speaking_stats():
    try:
        if not MONGO_ENABLED:
            return jsonify({'success': False, 'error': '數據庫未連接', 'stats': []})

        pipeline = [
            {
                "$group": {
                    "_id": "$user_id",
                    "total": {"$sum": 1},
                    "total_score": {"$sum": "$score"}
                }
            },
            {
                "$project": {
                    "user_id": "$_id",
                    "total": 1,
                    "accuracy": {
                        "$round": [
                            {"$divide": ["$total_score", {"$max": ["$total", 1]}]},
                            1
                        ]
                    }
                }
            }
        ]

        results = list(speaking_records.aggregate(pipeline))

        all_users = list(users.find({}, {'_id': 1, 'username': 1}))
        user_name_map = {str(u['_id']): u['username'] for u in all_users}

        formatted = []
        for r in results:
            user_id = r['user_id']
            formatted.append({
                'user_id': user_id,
                'username': user_name_map.get(user_id, '未知用戶'),
                'accuracy': r.get('accuracy', 0),
                'total': r.get('total', 0)
            })

        return jsonify({'success': True, 'stats': formatted})

    except Exception as e:
        print(f"獲取說話統計失敗: {e}")
        return jsonify({'success': False, 'error': str(e), 'stats': []})


@app.route('/api/all_listening_stats', methods=['GET'])
def get_all_listening_stats():

    try:
        if not MONGO_ENABLED:
            return jsonify({'success': False, 'error': '數據庫未連接', 'stats': []})

        pipeline = [
            {
                "$group": {
                    "_id": "$user_id",
                    "total": {"$sum": 1},
                    "total_score": {"$sum": "$score"}
                }
            },
            {
                "$project": {
                    "user_id": "$_id",
                    "total": 1,
                    "accuracy": {
                        "$round": [
                            {"$divide": ["$total_score", {"$max": ["$total", 1]}]},
                            1
                        ]
                    }
                }
            }
        ]

        results = list(listening_records.aggregate(pipeline))

        all_users = list(users.find({}, {'_id': 1, 'username': 1}))
        user_name_map = {str(u['_id']): u['username'] for u in all_users}

        formatted = []
        for r in results:
            user_id = r['user_id']
            formatted.append({
                'user_id': user_id,
                'username': user_name_map.get(user_id, '未知用戶'),
                'accuracy': r.get('accuracy', 0),
                'total': r.get('total', 0)
            })

        return jsonify({'success': True, 'stats': formatted})

    except Exception as e:
        print(f"獲取聆聽統計失敗: {e}")
        return jsonify({'success': False, 'error': str(e), 'stats': []})


if __name__ == '__main__':
    print("啟動普通話練習平台")
    print(f"AI 系統狀態: {'已啟用' if AI_ENABLED else '未加載'}")
    print(f"語音識別狀態: {'已啟用' if VOICE_ENABLED else '使用模擬'}")
    print(f"數據庫狀態: {'已啟用' if MONGO_ENABLED else '未加載'}")

    app.run(debug=True, host='127.0.0.1', port=5000, use_reloader=False)