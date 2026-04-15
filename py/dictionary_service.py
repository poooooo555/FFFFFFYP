
import os


class DictionaryService:
    def __init__(self):
        self.pinyin_dict = self._load_pinyin_data()

    def _load_pinyin_data(self):
        pinyin_map = {}

        file_path = os.path.join(os.path.dirname(__file__), 'dictionary', 'pinyin.txt')

        if not os.path.exists(file_path):
            print(f"錯誤: 找不到 {file_path}")
            return {}

        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith('#') or ':' not in line:
                    continue
                try:

                    parts = line.split('#')
                    char = parts[1].strip() if len(parts) > 1 else ""
                    pinyins = parts[0].split(':')[1].strip()
                    first_pinyin = pinyins.split(',')[0]

                    if char:
                        pinyin_map[char] = first_pinyin
                except:
                    continue
        return pinyin_map

    def search_word(self, word):

        pinyin_list = [self.pinyin_dict.get(c, c) for c in word]
        pinyin_str = " ".join(pinyin_list)

        return {
            'success': True,
            'word': word,
            'pinyin': pinyin_str,
            'source': '本地 pinyin.txt 數據庫'
        }



dictionary_service = DictionaryService()