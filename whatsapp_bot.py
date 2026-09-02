"""
منظومة السكرتيرة الذكية - شركة البرج المتألق
المزود: Evolution API (غير مقيد ومجاني بالكامل)
"""

import os
import re
import time
import threading
import requests
from flask import Flask, request, jsonify
from groq import Groq

app = Flask(__name__)

# =============================================================
# 1. مفاتيح الربط والإعدادات
# =============================================================
GROQ_API_KEY = "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"
EVOLUTION_API_URL = "https://rtco-evolution-api.onrender.com"
INSTANCE_NAME = "RTCo"
EVOLUTION_API_KEY = "Nawresnrshh@1096"

# رقم هاتف الإدارة لاستلام التقارير والإشعارات (مع الرمز الدولي و @s.whatsapp.net)
ADMIN_CHAT_ID = "9647805509298@s.whatsapp.net"

client = Groq(api_key=GROQ_API_KEY)

# هياكل الذاكرة والمؤقتات
user_conversations = {}   # {chat_id: [{"role": ..., "content": ...}]}
user_last_active = {}     # {chat_id: timestamp}
user_meta = {}            # {chat_id: {"name": str, "phone": str}}

# =============================================================
# 2. الهوية التوجيهية ونصوص الأقسام والاعتذار
# =============================================================
SYSTEM_INSTRUCTION = """
أنتِ السكرتيرة التنفيذية والمستشارة الفنية لشركة "البرج المتألق للمقاولات العامة والاستثمارات العقارية والتجارة العامة والنقل العام".
أسلوبكِ: أنثوي، لبق، راقٍ، ومهذب جداً بلهجة عراقية محترمة وبيئة أعمال راقية (مثل: "يا أهلاً وسهلاً بحضرتك"، "تدلل/تدللين"، "يسعدنا نخدمك").

قواعد الردود على واتساب:
1. أجيبي مباشرة عن سؤال العميل باللغة العربية مع تقديم تفاصيل هندسية وفنية مفيدة وموجزة.
2. لا تضعي أرقام هواتف أو إيميل أو روابط في نهاية الأجوبة العادية لأن العميل لديه خيار إرسال رقم 0 لعرض القائمة.
3. اذكري أرقام التواصل كتابياً فقط إذا طلبها الزبون بصراحة.
4. الحوار مستمر ومترابط؛ اربطي الإجابات التكميلية بالسياق السابق دون إعادة ترحيب.
"""

COMPANY_MENU_TEXT = (
    "🏛️ *شركة البرج المتألق - أقسام الشركة وقنوات التواصل*\n\n"
    "1️⃣ أرسل *1* : 🏗️ المقاولات العامة والإنشاءات\n"
    "2️⃣ أرسل *2* : 🏢 الاستثمارات والتطوير العقاري\n"
    "3️⃣ أرسل *3* : 📦 التجارة العامة والتوريدات\n"
    "4️⃣ أرسل *4* : 🚚 النقل العام والخدمات اللوجستية\n"
    "5️⃣ أرسل *5* : 📞 أرقام الهواتف المباشرة\n"
    "6️⃣ أرسل *6* : 🌐 المنصات الرسمية والموقع الإلكتروني\n\n"
    "💬 _أو تگدر تكتب أي استفسار مباشرة ويسعدني إجابتك فوراً._"
)

PERSISTENT_FOOTER = "\n\n─────────────\n📋 _لعرض أقسام الشركة ومعلومات التواصل، أرسل رقم *0*_"

def get_voice_apology_text(client_name: str, is_call: bool = True) -> str:
    media_type = "المكالمات الصوتية" if is_call else "الرسائل والبصمات الصوتية"
    return (
        f"يا أهلاً وسهلاً بحضرتك {client_name} نورتنا في *شركة البرج المتألق* ✨\n\n"
        f"📞 نعتذر من حضرتك، هذا الرقم مخصص لمنظومة السكرتارية والمراسلات النصية الآلية، ولا يمكن استلام أو معالجة {media_type} عبره.\n\n"
        "💬 *يسعدنا جداً خدمتك:* تفضل بكتابة استفسارك أو طلبك هنا *برسالة نصية* وسأجيبك بكل سرور وفوراً.\n\n"
        "☎️ أو يمكنك الاتصال هاتفياً ومباشرة بكادر الشركة عبر الأرقام التالية:\n"
        "▫️ 009647868006699\n"
        "▫️ 009647737006699\n"
        "▫️ هاتف الإدارة: 07805509298"
        + PERSISTENT_FOOTER
    )

# =============================================================
# 3. دوال التواصل مع Evolution API و Groq
# =============================================================
def send_whatsapp_message(chat_id: str, message: str):
    clean_id = chat_id.replace("@c.us", "").replace("@s.whatsapp.net", "")
    url = f"{EVOLUTION_API_URL}/message/sendText/{INSTANCE_NAME}"
    payload = {
        "number": clean_id,
        "options": {
            "delay": 1200,
            "presence": "composing",
            "linkPreview": False
        },
        "textMessage": {
            "text": message
        }
    }
    headers = {
        "Content-Type": "application/json",
        "apikey": EVOLUTION_API_KEY
    }
    try:
        requests.post(url, json=payload, headers=headers, timeout=10)
    except Exception as e:
        print(f"Error sending message via Evolution API: {e}")

def clean_think_tags(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    text = re.sub(r'<think>.*', '', text, flags=re.DOTALL)
    return text.strip()

def get_available_models():
    try:
        models_data = client.models.list().data
        valid_models = []
        for m in models_data:
            mid = m.id.lower()
            if any(x in mid for x in ["whisper", "guard", "r1", "deepseek", "vision", "qwen-qwq"]):
                continue
            valid_models.append(m.id)
        if valid_models:
            return valid_models
    except Exception:
        pass
    return ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]

def generate_ai_reply(messages_payload):
    models = get_available_models()
    for model_name in models:
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=messages_payload,
                temperature=0.4,
                max_tokens=800
            )
            raw = completion.choices[0].message.content
            cleaned = clean_think_tags(raw)
            if cleaned:
                return cleaned
        except Exception:
            continue
    return "يا أهلاً بحضرتك، شلون أگدر أساعدك اليوم في شركة البرج المتألق؟"

# =============================================================
# 4. مراقبة الـ 15 دقيقة خمول وتوليد التقارير للإدارة
# =============================================================
def background_inactivity_checker():
    while True:
        time.sleep(30)
        current_time = time.time()
        timeout_chats = []

        for chat_id, last_time in list(user_last_active.items()):
            if current_time - last_time >= 900:  # 15 دقيقة
                timeout_chats.append(chat_id)

        for chat_id in timeout_chats:
            history = user_conversations.get(chat_id, [])
            meta = user_meta.get(chat_id, {})

            user_last_active.pop(chat_id, None)
            user_conversations.pop(chat_id, None)
            user_meta.pop(chat_id, None)

            if not history:
                continue

            dialog_text = ""
            for msg in history:
                sender = "الزبون" if msg["role"] == "user" else "السكرتيرة"
                dialog_text += f"{sender}: {msg['content']}\n"

            summary_prompt = f"""
قم بتحليل محادثة خدمة العملاء التالية على واتساب لشركة 'البرج المتألق':
{dialog_text}

استخرج تقريراً رسمياً مختصراً جداً للإدارة:
1. ماذا كان يحتاج الزبون بالتحديد؟ (الطلب الجوهري)
2. كيف تمت إجابته والحل المقدم؟
3. الإجراء المقترح للمتابعة (إن وجد).
"""
            try:
                models = get_available_models()
                summary_res = client.chat.completions.create(
                    model=models[0],
                    messages=[{"role": "user", "content": summary_prompt}],
                    temperature=0.3,
                    max_tokens=400
                )
                executive_summary = clean_think_tags(summary_res.choices[0].message.content)
            except Exception:
                executive_summary = "تمت الجلسة بنجاح (يرجى مراجعة نص المحادثة المرفق أدناه)."

            clean_num = chat_id.split("@")[0]
            wa_link = f"https://wa.me/{clean_num}"
            client_name = meta.get("name", "زبون واتساب")

            admin_report = (
                f"📊 *تقرير جلسة واتساب مكتملة (بعد 15 دقيقة خمول)*\n\n"
                f"👤 *العميل:* {client_name}\n"
                f"📱 *الرقم:* +{clean_num}\n\n"
                f"📌 *الملخص الجوهري للمحادثة:*\n{executive_summary}\n\n"
                f"────────────────\n"
                f"📝 *نص المحادثة بالكامل:*\n{dialog_text[:2500]}\n"
                f"────────────────\n"
                f"👉 *مراسلة العميل مباشرة:*\n{wa_link}"
            )

            if clean_num not in ADMIN_CHAT_ID:
                send_whatsapp_message(ADMIN_CHAT_ID, admin_report)

threading.Thread(target=background_inactivity_checker, daemon=True).start()

# =============================================================
# 5. استقبال الأحداث والرسائل (Webhook)
# =============================================================
@app.route("/", methods=["GET"])
def health():
    return "Evolution API Bot is Live 24/7", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json or {}
    event = data.get("event", "")

    # 1) معالجة المكالمات الواردة
    if "call" in str(event).lower():
        call_data = data.get("data", {})
        caller_id = call_data.get("from") or call_data.get("chatId", "")
        caller_name = call_data.get("pushName") or "أستاذنا الفاضل"

        if caller_id and "@g.us" not in caller_id:
            clean_num = caller_id.split("@")[0]
            send_whatsapp_message(caller_id, get_voice_apology_text(caller_name, is_call=True))

            if clean_num not in ADMIN_CHAT_ID:
                admin_alert = (
                    "🔔 *تنبيه: مكالمة صوتية واردة*\n\n"
                    f"👤 *المتصل:* {caller_name}\n"
                    f"📱 *الرقم:* +{clean_num}\n"
                    "ℹ️ تم إرسال رسالة اعتذار آلية فوراً للمتصل بالأرقام المباشرة.\n\n"
                    f"👉 *لمعاودة الاتصال:* https://wa.me/{clean_num}"
                )
                send_whatsapp_message(ADMIN_CHAT_ID, admin_alert)
        return jsonify({"status": "call processed"}), 200

    # 2) معالجة الرسائل
    if event == "messages.upsert":
        msg_payload = data.get("data", {})
        key = msg_payload.get("key", {})
        from_me = key.get("fromMe", False)

        # تجاهل الرسائل المرسلة من حساب البوت نفسه
        if from_me:
            return jsonify({"status": "from_me ignored"}), 200

        chat_id = key.get("remoteJid", "")
        if "@g.us" in chat_id or not chat_id:
            return jsonify({"status": "group ignored"}), 200

        sender_name = msg_payload.get("pushName") or "أستاذنا الفاضل"
        message_obj = msg_payload.get("message", {}) or {}

        # أ. معالجة الرسائل والبصمات الصوتية
        if "audioMessage" in message_obj:
            clean_num = chat_id.split("@")[0]
            send_whatsapp_message(chat_id, get_voice_apology_text(sender_name, is_call=False))

            if clean_num not in ADMIN_CHAT_ID:
                admin_alert = (
                    "🎙️ *تنبيه: استلام رسالة / بصمة صوتية*\n\n"
                    f"👤 *العميل:* {sender_name}\n"
                    f"📱 *الرقم:* +{clean_num}\n"
                    "ℹ️ تم إرسال اعتذار آلي يوضح أن الرقم مخصص للنصوص.\n\n"
                    f"👉 *للاستماع والمراسلة:* https://wa.me/{clean_num}"
                )
                send_whatsapp_message(ADMIN_CHAT_ID, admin_alert)
            return jsonify({"status": "audio handled"}), 200

        # ب. استخراج النص
        text_message = (
            message_obj.get("conversation")
            or message_obj.get("extendedTextMessage", {}).get("text")
            or ""
        ).strip()

        if not text_message:
            return jsonify({"status": "non-text ignored"}), 200

        user_last_active[chat_id] = time.time()
        user_meta[chat_id] = {"name": sender_name, "phone": chat_id}

        if chat_id not in user_conversations:
            user_conversations[chat_id] = []

        lower_msg = text_message.lower()

        # فحص القوائم المباشرة
        if lower_msg in ["0", "الاقسام", "الأقسام", "القائمة", "قائمة", "menu"]:
            send_whatsapp_message(chat_id, COMPANY_MENU_TEXT)
            return jsonify({"status": "menu sent"}), 200

        dept_responses = {
            "1": "🏗️ *قسم المقاولات العامة والإنشاءات:*\n\n• تنفيذ الهياكل الإنشائية والخرسانية بدقة هندسية عالية.\n• تشطيبات متكاملة ديلوكس (تسليم مفتاح).\n• تصاميم معمارية وديكورات حديثة.\n• إشراف كادر هندسي معتمد وضمان شامل للجودة.\n\n💬 _تفضل بكتابة تفاصيل مشروعك أو مساحته وسأجيبك فوراً._",
            "2": "🏢 *قسم الاستثمارات والتطوير العقاري:*\n\n• دراسات جدوى واستشارات عقارية استثمارية متخصصة.\n• فرص عقارية وأراضٍ ممتازة تحقق أعلى عائد استثماري.\n• إدارة وتطوير وتسويق المشاريع العقارية.",
            "3": "📦 *قسم التجارة العامة والتوريدات:*\n\n• استيراد وتأمين المواد الإنشائية ومستلزمات البناء.\n• صفقات تجارية وسلاسل إمداد موثوقة للشركات والمشاريع.\n• أسعار تنافسية مطابقة للمواصفات القياسية المعتمدة.",
            "4": "🚚 *قسم النقل العام والخدمات اللوجستية:*\n\n• نقل بري آمن للمواد والبضائع بين كافة المحافظات.\n• إدارة الأساطيل وتأمين المسارات اللوجستية.\n• التزام تام بالمواعيد وسرعة في التسليم.",
            "5": "📞 *أرقام الهواتف وقنوات الاتصال المباشرة:*\n\n▫️ هاتف: 009647868006699\n▫️ هاتف: 009647737006699\n▫️ هاتف الإدارة: 07805509298\n▫️ البريد الإلكتروني: RTCo2025@gmail.com\n\nيسعدنا تواصلكم دائماً.",
            "6": "🌐 *منصاتنا وموقعنا الرسمي:*\n\n• الموقع الإلكتروني: www.alburjmutalaliq.co\n• تيليجرام: https://t.me/RTCo2025\n• إنستغرام وتيك توك وفيسبوك: @rtco2025"
        }

        if lower_msg in dept_responses:
            send_whatsapp_message(chat_id, dept_responses[lower_msg] + PERSISTENT_FOOTER)
            return jsonify({"status": "dept sent"}), 200

        # المعالجة الذكية
        is_first = len(user_conversations[chat_id]) == 0
        user_conversations[chat_id].append({"role": "user", "content": text_message})
        if len(user_conversations[chat_id]) > 8:
            user_conversations[chat_id] = user_conversations[chat_id][-8:]

        payload = [{"role": "system", "content": SYSTEM_INSTRUCTION}] + user_conversations[chat_id]
        ai_reply = generate_ai_reply(payload)
        user_conversations[chat_id].append({"role": "assistant", "content": ai_reply})

        if is_first and any(w in lower_msg for w in ["سلام", "مرحبا", "هلو", "صباح", "مساء", "start"]):
            final_reply = (
                "يا أهلاً وسهلاً بحضرتك نورتنا في *شركة البرج المتألق* ✨\n"
                "_(للمقاولات العامة • الاستثمارات العقارية • التجارة العامة • النقل العام)_\n\n"
                + ai_reply + PERSISTENT_FOOTER
            )
        else:
            final_reply = ai_reply + PERSISTENT_FOOTER

        send_whatsapp_message(chat_id, final_reply)

    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
