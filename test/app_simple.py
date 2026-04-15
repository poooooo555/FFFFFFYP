# app_simple.py - 最簡單測試版本
from flask import Flask

app = Flask(__name__)

@app.route('/')
def hello():
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>測試頁面</title>
        <style>
            body { font-family: Arial; margin: 40px; }
            a { margin: 10px; padding: 10px; background: #007bff; color: white; text-decoration: none; }
        </style>
    </head>
    <body>
        <h1>🎯 普通話練習平台</h1>
        <p>如果見到呢個頁面，表示 Flask 工作正常！</p>
        <div>
            <a href="/">首頁</a>
            <a href="/listening">聆聽練習</a>
            <a href="/speaking">說話練習</a>
            <a href="/test">測試 API</a>
        </div>
    </body>
    </html>
    '''

@app.route('/listening')
def listening():
    return '<h1>🎧 聆聽練習</h1><p>聆聽練習頁面</p><a href="/">返回首頁</a>'

@app.route('/speaking')
def speaking():
    return '<h1>🎤 說話練習</h1><p>說話練習頁面</p><a href="/">返回首頁</a>'

@app.route('/test')
def test():
    return {'status': 'success', 'message': 'API 工作正常！'}

if __name__ == '__main__':
    print("🚀 啟動最簡單測試版本...")
    app.run(debug=True, host='127.0.0.1', port=5000, use_reloader=False)