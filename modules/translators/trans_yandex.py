from .base import *

@register_translator('Yandex')
class YandexTranslator(BaseTranslator):

    concate_text = False
    params: Dict = {
        'api_key': '',
        'delay': 0.0,
    }

    def _setup_translator(self):
        self.lang_map['简体中文'] = 'zh'
        self.lang_map['日本語'] = 'ja'
        self.lang_map['English'] = 'en'
        self.lang_map['한국어'] = 'ko'
        self.lang_map['Tiếng Việt'] = 'vi'
        self.lang_map['čeština'] = 'cs'
        self.lang_map['Nederlands'] = 'nl'
        self.lang_map['Français'] = 'fr'
        self.lang_map['Deutsch'] = 'de'
        self.lang_map['magyar nyelv'] = 'hu'
        self.lang_map['Italiano'] = 'it'
        self.lang_map['Polski'] = 'pl'
        self.lang_map['Português'] = 'pt'
        self.lang_map['limba română'] = 'ro'
        self.lang_map['русский язык'] = 'ru'
        self.lang_map['Español'] = 'es'
        self.lang_map['Türk dili'] = 'tr'

        self.api_url = 'https://translate.api.cloud.yandex.net/translate/v2/translate'

    def _translate(self, src_list: List[str]) -> List[str]:

        body = {
            "targetLanguageCode": self.lang_map[self.lang_target],
            "texts": src_list,
            "folderId": '',
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": "Api-Key {0}".format(self.params['api_key'])
        }

        translations = requests.post(self.api_url, json=body, headers=headers).json()['translations']

        tr_list = []
        for tr in translations:
            if 'text' in tr:
                tr_list.append(tr['text'])
            else:
                tr_list.append('')
        return tr_list