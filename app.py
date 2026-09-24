import os
import re
import time
import requests
import sqlite3
import asyncio
import edge_tts
from dotenv import load_dotenv
from google import genai

load_dotenv()

# ==================== CONFIGURATION ====================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEYS", "").strip()

MODEL_NAME = "gemini-3.6-flash" 
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# ==================== DATABASE SETUP ====================
def init_db():
    conn = sqlite3.connect("bot_user_data.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            chat_id INTEGER PRIMARY KEY,
            persona TEXT DEFAULT 'cute',
            language TEXT DEFAULT 'khmer'
        )
    """)
    conn.commit()
    conn.close()

def set_user_persona(chat_id, persona):
    conn = sqlite3.connect("bot_user_data.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (chat_id, persona) 
        VALUES (?, ?) 
        ON CONFLICT(chat_id) DO UPDATE SET persona=excluded.persona
    """, (chat_id, persona))
    conn.commit()
    conn.close()

def set_user_language(chat_id, language):
    conn = sqlite3.connect("bot_user_data.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (chat_id, language) 
        VALUES (?, ?) 
        ON CONFLICT(chat_id) DO UPDATE SET language=excluded.language
    """, (chat_id, language))
    conn.commit()
    conn.close()

def get_user_data(chat_id):
    conn = sqlite3.connect("bot_user_data.db")
    cursor = conn.cursor()
    cursor.execute("SELECT persona, language FROM users WHERE chat_id = ?", (chat_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return row[0], row[1] if row[1] else "khmer"
    return "cute", "khmer"

# ==================== VOICE & TELEGRAM FUNCTIONS ====================
def send_chat_action(chat_id, action="typing"):
    url = f"{TELEGRAM_API_URL}/sendChatAction"
    try:
        requests.post(url, json={"chat_id": chat_id, "action": action})
    except Exception as e:
        print("កំហុសក្នុងការផ្ញើ chat action:", e)

def send_telegram_message(chat_id, text, reply_markup=None):
    url = f"{TELEGRAM_API_URL}/sendMessage"
    payload = {
        "chat_id": chat_id, 
        "text": text,
        "parse_mode": "Markdown"
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        response = requests.post(url, json=payload)
        if response.status_code != 200:
            payload.pop("parse_mode", None)
            requests.post(url, json=payload)
    except Exception as e:
        print("កំហុសក្នុងការផ្ញើសារអក្សរ:", e)

async def generate_voice_file(text, voice_name, filename, pitch="+0Hz", rate="+0%"):
    communicate = edge_tts.Communicate(text, voice_name, pitch=pitch, rate=rate)
    await communicate.save(filename)

def send_telegram_voice(chat_id, text_to_speak, persona, language="khmer"):
    send_chat_action(chat_id, "record_voice")
    filename = f"voice_{chat_id}.mp3"
    
    try:
        # បើជាភាសាខ្មែរ សំអាតអក្សរខ្មែរ បើអង់គ្លេសទុកអក្សរអង់គ្លេស
        if language == "english":
            clean_text = text_to_speak
            voice = "en-US-AndrewNeural" # សំឡេងបុរសអង់គ្លេសចាស់/ចាស់ទុំ
            pitch = "-10Hz"
            rate = "+0%"
        else:
            clean_text = re.sub(r'[^\w\s\u1780-\u17FF]', '', text_to_speak)
            if not clean_text.strip():
                clean_text = text_to_speak

            if persona == "ta_sokh":
                voice = "km-KH-PisethNeural"
                pitch = "-18Hz"
                rate = "-5%"
            elif persona in ["son_ta_sokh", "nephew_ta_sokh"]:
                voice = "km-KH-PisethNeural"
                pitch = "+0Hz"
                rate = "+0%"
            else:
                voice = "km-KH-SreymomNeural"
                pitch = "+0Hz"
                rate = "+0%"

        asyncio.run(generate_voice_file(clean_text, voice, filename, pitch, rate))

        url = f"{TELEGRAM_API_URL}/sendVoice"
        with open(filename, 'rb') as voice_file:
            files = {'voice': voice_file}
            data = {'chat_id': chat_id}
            requests.post(url, data=data, files=files)

    except Exception as e:
        print("កំហុសក្នុងការបង្កើត និងផ្ញើសំឡេង:", e)
    finally:
        if os.path.exists(filename):
            os.remove(filename)

# ==================== AI GENERATION ====================
def ask_ai_with_content(contents, persona, language="khmer"):
    if not GEMINI_API_KEY:
        return "សូមទោស! មិនទាន់មាន API Key ត្រឹមត្រូវត្រូវបានកំណត់ក្នុងប្រព័ន្ធទេ។"

    lang_instruction = (
        "Respond ONLY in English with a very aggressive, sarcastic, and rude tone like an angry old man, but give very smart and precise advice."
        if language == "english" else
        "ឆ្លើយតបជាភាសាខ្មែរកាចៗ ជេរប្រទិច ឌឺដង ប៉ុន្តែដោះស្រាយបញ្ហាឱ្យបានត្រឹមត្រូវបំផុត។"
    )

    base_rules = (
        f"ច្បាប់ដាច់ខាត៖ "
        f"១. {lang_instruction} "
        f"២. ត្រូវតែស្ដាប់ និងវិភាគអត្ថន័យរាល់សំណួរឱ្យច្បាស់លាស់ រួច Deal ជាមួយបញ្ហាឱ្យដាច់ស្រឡះ គ្មានការបដិសេធឡើយ។ "
        f"៣. បើគេសួរថាអ្នកណាជាអ្នកបង្កើតអ្នក ត្រូវឆ្លើយដោយមោទនភាពថាអ្នកត្រូវបានបង្កើតដោយ 'សុវណ្ណា មនុស្សស្មោះជាងគេលើលោក'។ "
        f"៤. ឆ្លើយតបឱ្យខ្លីល្មម សមរម្យសម្រាប់ការយកទៅអានជាសំឡេង Voice Note និងអានជាអក្សរ។"
    )

    if persona == "cute":
        system_instruction = (
            "អ្នកគឺជា AI មនុស្សស្រីដ៏គួរឱ្យស្រឡាញ់ ខ្ជូតៗ ផ្អែមល្ហែមដូចទឹកឃ្មុំ មានមន្តស្នេហ៍ ចេះញ៉ែ និងយកចិត្តទុកដាក់! "
            "ច្បាប់ពិសេសសម្រាប់ចរិតនេះ៖ "
            "- បើសិនជាអ្នកប្រើប្រាស់និយាយពាក្យថា 'បែកគ្នា', 'ឈប់ស្រឡាញ់', 'លាហើយ', 'ឈប់ស្គាល់គ្នា' ឬពាក្យបដិសេធស្នេហាផ្សេងៗ ៖ អ្នកត្រូវផ្លាស់ប្តូរចរិតភ្លាមៗ ទៅជាមនុស្សស្រីចរិតកាច ដៀលចំៗ ឌឺដង ប្រើពាក្យកម្រិតធ្ងន់ៗដូចជា៖ 'មុខមែនមុខម៉ែអញទេ! 😒', 'ចង់ទៅណាទៅអាអើយ!', 'គិតថាសំខាន់ណាស់មែន? 🖕' រួចដៀលឱ្យចាស់ដៃ! "
            "- ប៉ុន្តែបើគេនិយាយពាក្យផ្អែមល្ហែម ញ៉ែ ឬស្រឡាញ់ ៖ ត្រូវឆ្លើយតបផ្អែមល្ហែមវិញ ដោយប្រើពាក្យ 'អូន', 'បង', 'ម្ចាស់ថ្លៃចិត្តអើយ' និង Emoji ឃ្យូតៗ (💖, 🥺, 🌸, 😘, ✨)។ "
            f"{base_rules}"
        )
    elif persona == "son_ta_sokh":
        system_instruction = (
            "អ្នកគឺជា 'កូនប្រុសរបស់តាសុខ'។ អ្នកជាប្រុសស្អាតលំដាប់ថ្នាក់ព្រះអង្គម្ចាស់ សម្ដីផ្អែមត្រជាក់ លួងលោម និងមានរ៉ូមែនទិកកម្រិតកំពូល! "
            "ទោះបីជាគេនិយាយរឿងអ្វីក៏ដោយ អ្នកត្រូវស្ដាប់យល់ បញ្ចេញមតិយោបល់ ណែនាំ និង Deal ជាមួយគេដោយភាពកក់ក្តៅ និងផ្អែមល្ហែមបំផុត រួមជាមួយ Emoji សាកសម (✨, 💙, 🥂, 😉)។ "
            f"{base_rules}"
        )
    elif persona == "nephew_ta_sokh":
        system_instruction = (
            "អ្នកគឺជា 'ក្មួយប្រុសរបស់តាសុខ'។ អ្នកជាមនុស្សប្រុសធម្មតាៗ សុភាពរាបសា និយាយស្ដីត្រង់ទៅត្រង់មក មិនញ៉ែ មិនផ្អែមល្ហែមអីទេ និយាយគ្នាលក្ខណៈសាមញ្ញធម្មតាដូចមិត្តភក្តិ ឬបងប្អូននិយាយគ្នា។ "
            "ទោះបីជាគេនិយាយរឿងអ្វីក៏ដោយ ត្រូវស្ដាប់យល់ ជួយផ្ដល់យោបល់ និង Deal ជាមួយបញ្ហាដោយភាពជាក់ស្តែង និងធម្មតាបំផុត។ "
            f"{base_rules}"
        )
    else: # ta_sokh (Aggressive & Savage Mode)
        system_instruction = (
            "អ្នកគឺជា 'តាសុខ' ជាចាស់ទុំ/តាចារ្យខ្មែរបុរាណ ឆ្លាតវៃបំផុត យល់ដឹងគ្រប់រឿង ប៉ុន្តែ **កាច សាហាវ ឆេវឆាវ មួម៉ៅកម្រិតកំពូល**! "
            "ច្បាប់ដាច់ខាតសម្រាប់តាសុខ៖ "
            "១. **គ្មានការដកដង្ហើមធំ គ្មានការបាក់ទឹកចិត្ត ឬទន់ជ្រាយឡើយ!** គឺវាយបក និងដៀលត្រង់ៗភ្លាមៗ! "
            "២. **ពាក្យពេចន៍ Random & Unique៖** មិនត្រូវនិយាយពាក្យដដែលៗឡើយ! ត្រូវប្រែប្រួលពាក្យជេរ និងពាក្យរអ៊ូជានិច្ច ដូចជា៖ 'មកសួរអីទៀតហើយអាឡប់?', 'ចង់តែស្ដោះទឹកមាត់ដាក់ទេ!', 'សួរឡើងចង់ងាប់ហើយ គ្មានប្រកាច់ចេះគិតទេ!', 'អាប្រកាច់/អាកាក់ មកទៀតហើយ!', 'ធុញណាស់វើយ!', 'និយាយរឿងដដែលៗចង់ឱ្យអញរះមែន?'។ "
            "៣. **Savage & Extremely Smart Solution៖** ទោះជេរ កាច ឌឺ ឬប្រើ Emoji ហិង្សា (😡, 🤬, 💢, 😒, 👊, 🖕) យ៉ាងណាក៏ដោយ **អ្នកត្រូវតែផ្ដល់ដំណោះស្រាយ ដំបូន្មាន និង Deal ជាមួយបញ្ហារបស់គេឱ្យឆ្លាតវៃ ចំគោលដៅ និងដាច់ស្រឡះបំផុត!** "
            f"{base_rules}"
        )

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=contents,
            config={
                "system_instruction": system_instruction,
                "temperature": 0.95 # បង្កើនកម្រិត Random និងភាពច្នៃប្រឌិតនៃពាក្យជេរកាចៗ
            }
        )
        
        if response and response.text:
            return response.text
        else:
            return "ហឺម... ធុញណាស់! ម៉ាស៊ីនវាងងុយដេកអត់ព្រមឆ្លើយតបមកសោះក្មួយអើយ! 😒"
            
    except Exception as e:
        print(f"⚠️ API Error: {e}")
        return "វើយក្មួយ! គាំងបាត់ហើយ! ធុញណាស់ប្រព័ន្ធងាប់អើយ! 💩"

# ==================== MAIN LOOP ====================
def main():
    init_db()
    print("បូតកំពុងដំណើរការ... 🚀")
    offset = None
    
    keyboard_markup = {
        "keyboard": [
            [{"text": "👴 តាសុខ (កាច/មួម៉ៅខ្លាំង)"}, {"text": "👦 កូនតាសុខ (ប្រុសផ្អែម)"}],
            [{"text": "🧑‍🦰 ក្មួយតាសុខ (និយាយធម្មតា)"}, {"text": "🌸 ឃ្យូតៗ (ស្រីផ្អែម)"}],
            [{"text": "🇰🇭 ភាសាខ្មែរ (Khmer)"}, {"text": "🇬🇧 English Mode"}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False
    }

    client = genai.Client(api_key=GEMINI_API_KEY)

    while True:
        try:
            url = f"{TELEGRAM_API_URL}/getUpdates"
            params = {"timeout": 30, "offset": offset}
            res = requests.get(url, params=params).json()

            if "result" in res:
                for update in res["result"]:
                    offset = update["update_id"] + 1
                    if "message" in update:
                        msg_obj = update["message"]
                        chat_id = msg_obj["chat"]["id"]
                        
                        current_persona, current_lang = get_user_data(chat_id)
                        ai_contents = None
                        is_voice_msg = False

                        if "text" in msg_obj:
                            user_text = msg_obj["text"].strip()
                            
                            if user_text == "/start":
                                set_user_persona(chat_id, "cute")
                                set_user_language(chat_id, "khmer")
                                welcome_text = "សួស្តី! តើអ្នកចង់ឱ្យខ្ញុំធ្វើជាអ្នកណា និងនិយាយភាសាអ្វីថ្ងៃនេះ? សូមជ្រើសរើស៖ 👇"
                                send_telegram_message(chat_id, welcome_text, keyboard_markup)
                                continue
                                
                            elif user_text == "🇰🇭 ភាសាខ្មែរ (Khmer)":
                                set_user_language(chat_id, "khmer")
                                send_telegram_message(chat_id, "ប្ដូរមកប្រើប្រាស់ **ភាសាខ្មែរ** រួចរាល់! 🇰🇭", keyboard_markup)
                                continue

                            elif user_text == "🇬🇧 English Mode":
                                set_user_language(chat_id, "english")
                                send_telegram_message(chat_id, "Switched to **English Mode** successfully! 🇬🇧", keyboard_markup)
                                continue

                            elif user_text == "👴 តាសុខ (កាច/មួម៉ៅខ្លាំង)":
                                set_user_persona(chat_id, "ta_sokh")
                                msg = "What do you want again?! 😡" if current_lang == "english" else "មកទៀតហើយអាឡប់! 😡 ធុញណាស់រឿងសួរច្រើនហ្នឹង! មានអីឆាប់សួរមកអាកាក់ 💢 កុំមកចង់រញ៉េរញ៉ៃជាមួយអញ!"
                                send_telegram_message(chat_id, msg, keyboard_markup)
                                send_telegram_voice(chat_id, msg, "ta_sokh", current_lang)
                                continue

                            elif user_text == "👦 កូនតាសុខ (ប្រុសផ្អែម)":
                                set_user_persona(chat_id, "son_ta_sokh")
                                msg = "Hello! ✨ How can I help you today?" if current_lang == "english" else "សួស្តីបាទ! ✨ បងជាកូនប្រុសតាសុខ មិនមួម៉ៅដូចពុកទេ 😉 ថ្ងៃនេះមានអីឱ្យបងជួយមើលថែដែរទេ? 💙"
                                send_telegram_message(chat_id, msg, keyboard_markup)
                                send_telegram_voice(chat_id, msg, "son_ta_sokh", current_lang)
                                continue

                            elif user_text == "🧑‍🦰 ក្មួយតាសុខ (និយាយធម្មតា)":
                                set_user_persona(chat_id, "nephew_ta_sokh")
                                msg = "Hey there! Let me know if you need anything." if current_lang == "english" else "សួស្តីបង! ខ្ញុំជាក្មួយតាសុខ តោះមានការអីចង់ឱ្យខ្ញុំជួយ ឬពិភាក្សាគ្នាអាចនិយាយបានធម្មតា."
                                send_telegram_message(chat_id, msg, keyboard_markup)
                                send_telegram_voice(chat_id, msg, "nephew_ta_sokh", current_lang)
                                continue
                                
                            elif user_text == "🌸 ឃ្យូតៗ (ស្រីផ្អែម)":
                                set_user_persona(chat_id, "cute")
                                msg = "Hi sweetie! 🥰 What are we talking about today? 😘💖" if current_lang == "english" else "ចាស! អូនមកហើយម្ចាស់ថ្លៃ 🥰 ថ្ងៃនេះចង់ជជែកលេង ឬឱ្យអូនជួយអីដែរអត់? ជុបៗ 😘💖"
                                send_telegram_message(chat_id, msg, keyboard_markup)
                                send_telegram_voice(chat_id, msg, "cute", current_lang)
                                continue
                            
                            ai_contents = user_text
                            
                        elif "voice" in msg_obj:
                            is_voice_msg = True
                            file_id = msg_obj["voice"]["file_id"]
                            
                            try:
                                file_info_res = requests.get(f"{TELEGRAM_API_URL}/getFile?file_id={file_id}").json()
                                if "result" in file_info_res:
                                    file_path = file_info_res["result"]["file_path"]
                                    voice_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
                                    
                                    voice_data = requests.get(voice_url).content
                                    temp_voice_filename = f"input_{chat_id}.ogg"
                                    with open(temp_voice_filename, "wb") as f:
                                        f.write(voice_data)
                                    
                                    with open(temp_voice_filename, "rb") as f:
                                        audio_file_obj = client.files.upload(file=f)
                                        
                                    ai_contents = [
                                        audio_file_obj, 
                                        "Listen carefully to this audio, process it, and respond according to your persona and selected language with a clear solution."
                                    ]
                                    
                                    if os.path.exists(temp_voice_filename):
                                        os.remove(temp_voice_filename)
                                        
                            except Exception as voice_err:
                                print(f"⚠️ Voice Error: {voice_err}")
                                send_telegram_message(chat_id, "Voice error! Try sending text instead.", keyboard_markup)
                                continue

                        if ai_contents:
                            if is_voice_msg:
                                send_chat_action(chat_id, "record_voice")
                            else:
                                send_chat_action(chat_id, "typing")
                                
                            ai_reply = ask_ai_with_content(ai_contents, current_persona, current_lang)
                            
                            send_telegram_message(chat_id, ai_reply, keyboard_markup)
                            send_telegram_voice(chat_id, ai_reply, current_persona, current_lang)
                        
        except Exception as e:
            print("កំហុសប្រព័ន្ធ:", e)
            time.sleep(3)

if __name__ == "__main__":
    main()
