import requests
import random
import re
import json


class CantoneseAIGenerator:
    def __init__(self, api_key=None, base_url="https://api.deepseek.com/v1"):
        self.api_key = api_key
        self.base_url = base_url
        self.model_loaded = bool(api_key)

    def set_api_key(self, api_key):

        self.api_key = api_key
        self.model_loaded = bool(api_key)
        if self.model_loaded:
            print("DeepSeek API 密鑰設置成功")
        else:
            print("DeepSeek API 密鑰無效")

    def call_deepseek_api(self, prompt, max_tokens=500):

        if not self.model_loaded:
            return None

        try:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }

            data = {
                "model": "deepseek-chat",
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "max_tokens": max_tokens,
                "temperature": 0.8,
                "stream": False
            }

            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=data,
                timeout=60
            )

            if response.status_code == 200:
                result = response.json()
                return result["choices"][0]["message"]["content"]
            else:
                print(f"API 請求失敗: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            print(f"調用 DeepSeek API 失敗: {e}")
            return None

    def generate_complete_exercise(self, topic):

        print(f"為主題 '{topic}' 生成 AI 練習...")

        if not self.model_loaded:
            return self._fallback_exercise(topic)

        try:
            # 單次 API 調用生成所有內容
            prompt = f"""請根據「{topic}」這個主題，完成以下任務：

1. 寫一個大約100-150字的對話故事，包含兩個人（A和B）的對話
2. 基於對話內容生成一條選擇題
3. 提供A、B、C、D四個選項
4. 明確指出正確答案

請按照以下JSON格式輸出，不要添加其他內容：

{{
  "dialogue": "A: [對話內容]\\nB: [對話內容]\\nA: [對話內容]\\nB: [對話內容]",
  "question": "選擇題問題",
  "options": [
    "A. 選項A內容",
    "B. 選項B內容", 
    "C. 選項C內容",
    "D. 選項D內容"
  ],
  "correct_answer": "A. 選項A內容"
}}

請確保：
- 對話自然流暢，圍繞主題「{topic}」
- 問題要基於對話內容
- 正確答案必須是options中的一個
- 直接輸出JSON，不要有其他文字"""

            result = self.call_deepseek_api(prompt, max_tokens=800)

            if result:
                return self._parse_json_result(result, topic)
            else:
                return self._fallback_exercise(topic)

        except Exception as e:
            print(f"AI 練習生成失敗: {e}")
            return self._fallback_exercise(topic)

    def _parse_json_result(self, result, topic):

        try:

            json_match = re.search(r'\{.*\}', result, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                data = json.loads(json_str)


                required_fields = ['dialogue', 'question', 'options', 'correct_answer']
                if all(field in data for field in required_fields):


                    if data['correct_answer'] not in data['options']:
                        print("正確答案不在選項中，使用第一個選項")
                        data['correct_answer'] = data['options'][0]

                    return {
                        "dialogue": data["dialogue"],
                        "question": data["question"],
                        "options": data["options"],
                        "correct_answer": data["correct_answer"],
                        "source": "deepseek_api"
                    }


            print("JSON 解析失敗，使用備用方案")
            return self._fallback_exercise(topic)

        except json.JSONDecodeError as e:
            print(f"JSON 解析錯誤: {e}")
            return self._fallback_exercise(topic)
        except Exception as e:
            print(f"解析結果失敗: {e}")
            return self._fallback_exercise(topic)

    def _fallback_exercise(self, topic):

        print(f"使用備用練習生成 for {topic}")


        dialogues = {
            "學習": "A: 你最近在學什麼？\nB: 我在學普通話，覺得發音有點難。\nA: 多練習就會進步，我可以幫你。\nB: 太好了，我們一起練習吧！",
            "旅遊": "A: 假期打算去哪裡玩？\nB: 我想去北京看看長城和故宮。\nA: 北京很漂亮，食物也很好吃。\nB: 是啊，我已經開始做旅行計劃了。",
            "工作": "A: 新工作怎麼樣？\nB: 很不錯，同事都很友善。\nA: 工作內容有趣嗎？\nB: 很有挑戰性，但能學到很多。",
            "飲食": "A: 今晚想吃什麼？\nB: 我想吃火鍋，天氣有點冷。\nA: 好主意，我知道一家不錯的火鍋店。\nB: 那我們下班後一起去吧！"
        }


        exercises = {
            "學習": {
                "question": "兩個人在討論什麼？",
                "options": ["A. 學習普通話", "B. 旅行計劃", "C. 工作情況", "D. 晚餐選擇"],
                "correct_answer": "A. 學習普通話"
            },
            "旅遊": {
                "question": "B計劃去哪裡旅行？",
                "options": ["A. 上海", "B. 北京", "C. 廣州", "D. 香港"],
                "correct_answer": "B. 北京"
            },
            "工作": {
                "question": "B對新工作感覺如何？",
                "options": ["A. 很無聊", "B. 很有挑戰性", "C. 很輕鬆", "D. 很困難"],
                "correct_answer": "B. 很有挑戰性"
            },
            "飲食": {
                "question": "他們決定吃什麼？",
                "options": ["A. 壽司", "B. 火鍋", "C. 披薩", "D. 漢堡"],
                "correct_answer": "B. 火鍋"
            }
        }


        if topic in dialogues and topic in exercises:
            dialogue = dialogues[topic]
            exercise_data = exercises[topic]
        else:
            dialogue = dialogues["學習"]
            exercise_data = exercises["學習"]

        return {
            "dialogue": dialogue,
            "question": exercise_data["question"],
            "options": exercise_data["options"],
            "correct_answer": exercise_data["correct_answer"],
            "source": "fallback"
        }



cantonese_ai_generator = CantoneseAIGenerator()