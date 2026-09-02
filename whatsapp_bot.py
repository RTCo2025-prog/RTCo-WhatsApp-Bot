"""
نظام السكرتيرة الذكية على واتساب - شركة البرج المتألق
الملف: whatsapp_bot.py
الميزات: الذاكرة التفاعلية + القائمة المدمجة + تقرير بعد 15 دقيقة خمول مع رابط مراسلة مباشر
"""

import os
import re
import threading
import time
from flask import Flask, request
from groq import Groq
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client as TwilioClient

app = Flask(__name__)

# =============================================================
# 1. المفاتيح وإعدادات الاتصال
# =============================================================
GROQ_API_KEY = "gsk_ضع_مفتاح_جروك_الجديد_هنا".strip()

# بيانات حساب Twilio الخاص بك
TWILIO_ACCOUNT_SID = "AC_ضع_account_sid_هنا"
TWILIO_AUTH_TOKEN = "ضع_auth_token_هنا"

# رقم هاتف الإدارة لاستلام التقارير (بالصيغة الدولية مع +)
ADMIN_WHATSAPP_NUMBER = "whatsapp:+9647805509298"

groq_client = Groq(api_key=GROQ_API_KEY)
twilio_client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# هياكل تخزين المحادثات والمؤقتات بالذاكرة
user_conversations = {}    # {phone_number: [ {role, content}, ... ]}
user_last_active = {}      # {phone_number: timestamp}
user_meta = {}             # {phone_number: {"name": str, "bot_number": str}}

# =============================================================
# 2. نصوص وهوية السكرتيرة الذكية (System Prompt)
# =============================================================
SYSTEM_INSTRUCTION = """
أنتِ السكرتيرة التنفيذية والمستشارة الفنية لشركة "البرج المتألق للمقاولات العامة والاستثمارات العقارية والتجارة العامة والنقل العام".
أسلوبكِ: أنثوي، لبق، راقٍ، ومهذب جداً بلهجة عراقية محترمة وبيئة أعمال راقية (مثل: "يا أهلاً وسهلاً بحضرتك"، "تدلل/تدللين"، "يسعدنا نخدمك").

قواعد الردود على واتساب:
1. أجيبي مباشرة عن سؤال العميل باللغة العربية مع تقديم تفاصيل هندسية وفنية مفيدة.
2. لا تضعي أرقام هواتف أو إيميل أو روابط في نهاية الأجوبة العادية؛ لأن العميل لديه خيار إرسال رقم 0 لعرض القائمة.
3. اذكري أرقام الهواتف فقط إذا طلبها الزبون بصراحة.
4. الحوار مستمر ومترابط؛ إذا سأل الزبون سؤالاً إضافياً، اربطي الجواب مباشرة بالسياق السابق دون إعادة ترحيب.
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

# =============================================================
# 3. دوال المعالجة واختيار النماذج
# =============================================================
def clean_think_tags(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    text = re.sub(r'<think>.*', '', text, flags=re.DOTALL)
    return text.strip()

def get_available_models():
    try:
        models_data = groq_client.models.list().data
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
            completion = groq_client.chat.completions.create(
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
# 4. نظام المراقبة وإرسال التقارير بعد 15 دقيقة خمول
# =============================================================
def background_inactivity_checker():
    """خيط خلفي يفحص الجلسات التي توقفت لأكثر من 15 دقيقة (900 ثانية)"""
    while True:
        time.sleep(30)
        current_time = time.time()
        timeout_users = []

        for phone, last_time in list(user_last_active.items()):
            if current_time - last_time >= 900:  # 15 دقيقة خمول
                timeout_users.append(phone)

        for phone in timeout_users:
            history = user_conversations.get(phone, [])
            meta = user_meta.get(phone, {})
            
            # حذف المستخدم من المراقبة حتى لا يتكرر التقرير
            user_last_active.pop(phone, None)
            user_conversations.pop(phone, None)
            user_meta.pop(phone, None)

            if not history:
                continue

            # تجميع نص المحادثة
            dialog_text = ""
            for msg in history:
                sender = "الزبون" if msg["role"] == "user" else "السكرتيرة"
                dialog_text += f"{sender}: {msg['content']}\n"

            # استخراج ملخص تنفيذي عبر الذكاء الاصطناعي
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
                summary_res = groq_client.chat.completions.create(
                    model=models[0],
                    messages=[{"role": "user", "content": summary_prompt}],
                    temperature=0.3,
                    max_tokens=400
                )
                executive_summary = clean_think_tags(summary_res.choices[0].message.content)
            except Exception:
                executive_summary = "تمت الجلسة (يرجى الاطلاع على نص المحادثة المرفق أدناه)."

            clean_num = phone.replace("whatsapp:", "").replace("+", "")
            wa_link = f"https://wa.me/{clean_num}"
            client_name = meta.get("name", "زبون واتساب")
            bot_phone = meta.get("bot_number", "")

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

            # إرسال التقرير لرقم الإدارة عبر Twilio
            try:
                if phone != ADMIN_WHATSAPP_NUMBER and bot_phone:
                    twilio_client.messages.create(
                        body=admin_report,
                        from_=bot_phone,
                        to=ADMIN_WHATSAPP_NUMBER
                    )
            except Exception as e:
                print(f"Error sending admin report: {e}")

# تشغيل خيط المراقبة في الخلفية
threading.Thread(target=background_inactivity_checker, daemon=True).start()

# =============================================================
# 5. السيرفر ونقاط الاستقبال (Webhooks)
# =============================================================
@app.route("/", methods=["GET"])
def health():
    return "RTCo WhatsApp Secretary is Live 24/7", 200

@app.route("/webhook", methods=["POST"])
def whatsapp_webhook():
    incoming_msg = request.values.get("Body", "").strip()
    sender_whatsapp = request.values.get("From", "")
    bot_whatsapp = request.values.get("To", "")
    profile_name = request.values.get("ProfileName", "زبون واتساب")

    if not incoming_msg:
        return str(MessagingResponse())

    # تحديث بيانات المستخدم ووقت آخر نشاط
    user_last_active[sender_whatsapp] = time.time()
    user_meta[sender_whatsapp] = {
        "name": profile_name,
        "bot_number": bot_whatsapp
    }

    if sender_whatsapp not in user_conversations:
        user_conversations[sender_whatsapp] = []

    reply_text = ""
    lower_msg = incoming_msg.lower()

    # فحص الرسائل التوجيهية والأقسام
    if lower_msg in ["0", "الاقسام", "الأقسام", "القائمة", "قائمة", "menu"]:
        reply_text = COMPANY_MENU_TEXT

    elif lower_msg == "1":
        reply_text = (
            "🏗️ *قسم المقاولات العامة والإنشاءات:*\n\n"
            "• تنفيذ الهياكل الإنشائية والخرسانية بدقة هندسية عالية.\n"
            "• تشطيبات متكاملة ديلوكس (تسليم مفتاح).\n"
            "• تصاميم معمارية وديكورات داخلية حديثة.\n"
            "• إشراف كادر هندسي معتمد مع ضمان شامل للجودة.\n\n"
            "💬 _تگدر تكتب تفاصيل مشروعك أو مساحته هنا وسأجيبك فوراً._"
        )
    elif lower_msg == "2":
        reply_text = (
            "🏢 *قسم الاستثمارات والتطوير العقاري:*\n\n"
            "• دراسات جدوى واستشارات عقارية استثمارية متخصصة.\n"
            "• فرص عقارية وأراضٍ ممتازة تحقق أعلى عائد وقيمة مضافة.\n"
            "• إدارة وتطوير وتسويق المشاريع العقارية."
        )
    elif lower_msg == "3":
        reply_text = (
            "📦 *قسم التجارة العامة والتوريدات:*\n\n"
            "• استيراد وتأمين المواد الإنشائية ومستلزمات البناء.\n"
            "• صفقات تجارية وسلاسل إمداد موثوقة للشركات والمشاريع.\n"
            "• أسعار تنافسية مطابقة للمواصفات القياسية المعتمدة."
        )
    elif lower_msg == "4":
        reply_text = (
            "🚚 *قسم النقل العام والخدمات اللوجستية:*\n\n"
            "• نقل بري آمن ومنتظم للمواد والبضائع بين المحافظات.\n"
            "• إدارة الأساطيل وتأمين المسارات اللوجستية بأمان.\n"
            "• التزام تام بالمواعيد وسرعة في التسليم."
        )
    elif lower_msg == "5":
        reply_text = (
            "📞 *أرقام الهواتف وقنوات الاتصال المباشرة:*\n\n"
            "▫️ هاتف: 009647868006699\n"
            "▫️ هاتف: 009647737006699\n"
            "▫️ هاتف الإدارة: 07805509298\n"
            "▫️ البريد الإلكتروني: RTCo2025@gmail.com\n\n"
            "كادر الشركة بخدمتكم دائماً."
        )
    elif lower_msg == "6":
        reply_text = (
            "🌐 *منصاتنا وموقعنا الرسمي:*\n\n"
            "• الموقع الإلكتروني: www.alburjmutalaliq.co\n"
            "• تيليجرام: https://t.me/RTCo2025\n"
            "• إنستغرام وتيك توك وفيسبوك: @rtco2025"
        )
    else:
        # إذا كانت المحادثة تبدأ بكلمات تحية لأول مرة
        is_first_interaction = len(user_conversations[sender_whatsapp]) == 0
        
        # إضافة الرسالة للذاكرة
        user_conversations[sender_whatsapp].append({"role": "user", "content": incoming_msg})
        if len(user_conversations[sender_whatsapp]) > 8:
            user_conversations[sender_whatsapp] = user_conversations[sender_whatsapp][-8:]

        payload = [{"role": "system", "content": SYSTEM_INSTRUCTION}] + user_conversations[sender_whatsapp]
        ai_reply = generate_ai_reply(payload)
        user_conversations[sender_whatsapp].append({"role": "assistant", "content": ai_reply})

        if is_first_interaction and any(w in lower_msg for w in ["سلام", "مرحبا", "هلو", "صباح", "مساء", "start"]):
            reply_text = (
                "يا أهلاً وسهلاً بحضرتك نورتنا في *شركة البرج المتألق* ✨\n"
                "_(للمقاولات العامة • الاستثمارات العقارية • التجارة العامة • النقل العام)_\n\n"
                + ai_reply + PERSISTENT_FOOTER
            )
        else:
            reply_text = ai_reply + PERSISTENT_FOOTER

    # إرسال رد واتساب
    twiml_resp = MessagingResponse()
    twiml_resp.message(reply_text)
    return str(twiml_resp)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
