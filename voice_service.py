
import sounddevice as sd
import numpy as np
import time
from typing import Tuple
import re

try:
    import whisper

    WHISPER_AVAILABLE = True
    print("OpenAI Whisper 可用")
except ImportError as e:
    WHISPER_AVAILABLE = False
    print(f"OpenAI Whisper 不可用: {e}")


class VoiceService:
    def __init__(self, model_size: str = "base"):
        self.model_size = model_size
        self.model = None
        self.sample_rate = 16000
        self.load_model()

    def load_model(self):
        if not WHISPER_AVAILABLE:
            print("Whisper 不可用，使用模擬模式")
            return

        print(f"加載 Whisper {self.model_size} 模型...")
        try:
            self.model = whisper.load_model(self.model_size)
            print(f"Whisper {self.model_size} 模型加載成功")
        except Exception as e:
            print(f"模型加載失敗: {e}")
            print("使用模擬語音識別模式")

    def transcribe_audio(self, duration: int = 10, target_word: str = "") -> Tuple[str, float]:

        if not self.model or not WHISPER_AVAILABLE:
            return self._simulate_transcription(target_word)

        try:
            audio_data = self.record_audio(duration)
            if audio_data is None:
                return "錄音失敗", 0.0

            result = self.model.transcribe(
                audio_data,
                language='zh',
                task='transcribe',
                fp16=False
            )

            transcription = result["text"].strip()


            confidence = result.get("segments", [{}])[0].get("confidence", 0.5) * 100

            return transcription, confidence

        except Exception as e:
            print(f"語音識別失敗: {e}")
            return self._simulate_transcription(target_word)

    def _simulate_transcription(self, target_word: str) -> Tuple[str, float]:
        print("使用模擬語音識別模式")
        time.sleep(2)

        if not target_word:
            return "請說出目標詞語", 0.0


        word_hash = hash(target_word) % 10

        if word_hash < 8:
            transcription = target_word
            confidence = 100.0
        else:

            common_errors = {
                "你好": "你號", "謝謝": "些些", "再見": "在見",
                "老師": "老司", "學生": "學森", "朋友": "盆友",
                "工作": "工坐", "天氣": "天汽", "食物": "實物",
                "學習": "學系", "學校": "學笑", "家庭": "家亭"
            }
            transcription = common_errors.get(target_word, target_word + "嗎")


            target_clean = self._clean_text(target_word)
            trans_clean = self._clean_text(transcription)

            correct_chars = 0
            min_len = min(len(trans_clean), len(target_clean))
            for i in range(min_len):
                if trans_clean[i] == target_clean[i]:
                    correct_chars += 1

            if len(target_clean) > 0:
                confidence = (correct_chars / len(target_clean)) * 100
            else:
                confidence = 0.0

        print(f"模擬識別結果: {transcription} (置信度: {confidence:.1f}%)")
        return transcription, confidence

    def record_audio(self, duration: int = 15) -> np.ndarray:
        try:
            print(f"開始錄音 {duration} 秒...")
            recording = sd.rec(
                int(duration * self.sample_rate),
                samplerate=self.sample_rate,
                channels=1,
                dtype='float32'
            )
            sd.wait()
            print("錄音完成")
            return recording.flatten()
        except Exception as e:
            print(f"錄音失敗: {e}")
            return None

    def _calculate_mandarin_confidence(self, transcription: str, target_word: str) -> float:
        if not transcription:
            return 0.0

        transcription_clean = self._clean_text(transcription)
        target_clean = self._clean_text(target_word) if target_word else ""


        has_chinese = any('\u4e00' <= char <= '\u9fff' for char in transcription_clean)
        if not has_chinese:
            return 0.0


        if not target_clean:
            return 20.0


        if not transcription_clean:
            return 0.0


        correct_chars = 0
        min_len = min(len(transcription_clean), len(target_clean))

        for i in range(min_len):
            if transcription_clean[i] == target_clean[i]:
                correct_chars += 1


        if len(target_clean) > 0:
            match_percentage = (correct_chars / len(target_clean)) * 100
        else:
            match_percentage = 0.0


        if transcription_clean == target_clean:
            return 100.0

        return round(match_percentage, 1)

    def _clean_text(self, text):
        if not text:
            return ""

        import re

        cleaned = re.sub(r'[^\u4e00-\u9fff]', '', text)
        return cleaned

    def evaluate_pronunciation(self, user_text: str, target_text: str) -> dict:

        user_clean = self._clean_text(user_text)
        target_clean = self._clean_text(target_text)


        if not target_clean:
            return {
                "accuracy": 0.0,
                "user_text": user_text,
                "target_text": target_text,
                "feedback": "目標文本為空",
                "matched_chars": 0,
                "total_chars": 0
            }


        matched_chars = 0
        total_chars = len(target_clean)
        min_len = min(len(user_clean), len(target_clean))

        for i in range(min_len):
            if user_clean[i] == target_clean[i]:
                matched_chars += 1


        accuracy = (matched_chars / total_chars) * 100 if total_chars > 0 else 0


        if user_clean == target_clean:
            feedback = "完美！發音完全正確！"
            accuracy = 100.0
        elif accuracy >= 80:
            feedback = f"很好！準確率 {accuracy:.1f}%"
        elif accuracy >= 60:
            feedback = f"不錯！準確率 {accuracy:.1f}%"
        elif accuracy >= 40:
            feedback = f"加油！準確率 {accuracy:.1f}%"
        else:
            feedback = f"需要加強！準確率 {accuracy:.1f}%"

        print(f"發音評估: 目標='{target_clean}', 用戶='{user_clean}'")
        print(f"匹配字符: {matched_chars}/{total_chars} = {accuracy:.1f}%")

        return {
            "accuracy": round(accuracy, 1),
            "user_text": user_text,
            "target_text": target_text,
            "feedback": feedback,
            "matched_chars": matched_chars,
            "total_chars": total_chars
        }



voice_service = VoiceService("base")