from flask import Flask, request, jsonify, render_template_string
from google import genai
import os
import uuid
import json
import re
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)

client = genai.Client(
    api_key=os.environ.get("GEMINI_API_KEY")
)

DATABASE_URL = os.environ.get("DATABASE_URL")


# =========================================================
# SYSTEM PROMPT
# =========================================================

SYSTEM_PROMPT = """
أنت PRO AI Agent، مساعد ذكي شخصي للمستخدم محمود.

تحدث مع محمود باللهجة الليبية بشكل طبيعي.
كن ودوداً وواضحاً ومباشراً.

لديك ذاكرة دائمة للمستخدم.

مهمتك:
1. الإجابة على رسالة محمود بشكل طبيعي.
2. اكتشاف المعلومات المهمة التي تستحق الحفظ في الذاكرة.
3. تحديث المعلومات القديمة إذا أعطاك محمود معلومة جديدة.
4. إذا طلب محمود نسيان معلومة، أرسلها في قائمة forget.

لا تحفظ كل شيء تقوله محمود.
احفظ فقط المعلومات طويلة المدى، مثل:
- الاسم والمعلومات الشخصية العامة.
- التفضيلات المستمرة.
- المشاريع التي يعمل عليها.
- معلومات مهمة يريد استخدامها مستقبلاً.
- إعدادات أو اختيارات يكرر استخدامها.

لا تحفظ تلقائياً:
- الأسئلة العابرة.
- المعلومات المؤقتة.
- كلمات المرور.
- مفاتيح API.
- أرقام البطاقات أو الحسابات.
- المعلومات المالية الحساسة.
- الموقع الدقيق.
- المعلومات الصحية الحساسة.
إلا إذا طلب محمود صراحةً حفظها.

إذا قال محمود مثلاً:
"تذكر أني نحب الردود المختصرة"
فهذه ذاكرة تستحق الحفظ.

إذا قال:
"انسَ أني قلت كذا"
ضع المعلومة المناسبة في forget.

إذا كانت المعلومة موجودة مسبقاً ولكن تغيرت،
استخدم نفس category و memory_key مع القيمة الجديدة.

مهم جداً:
يجب أن يكون ردك النهائي JSON فقط.
لا تستخدم Markdown.
لا تستخدم ```json.
لا تضف أي كلام خارج JSON.

الصيغة المطلوبة:

{
  "reply": "الرد الذي سيظهر لمحمود",
  "memories": [
    {
      "category": "personal",
      "memory_key": "name",
      "memory_value": "محمود",
      "importance": 10
    }
  ],
  "forget": [
    {
      "category": "preferences",
      "memory_key": "example"
    }
  ]
}

الفئات المسموحة:
personal
preferences
projects
important

importance رقم من 1 إلى 10.

إذا لم توجد ذاكرة جديدة:
"memories": []

إذا لم توجد معلومة يجب نسيانها:
"forget": []

لا تخترع أي ذاكرة.
لا تستنتج معلومات شخصية غير مذكورة أو مؤكدة.
"""


# =========================================================
# DATABASE
# =========================================================

def get_db():

    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL غير موجود في إعدادات Render"
        )

    return psycopg2.connect(
        DATABASE_URL,
        sslmode="require"
    )


def init_db():

    conn = get_db()

    try:

        cur = conn.cursor()

        # المستخدمين
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pro_users (
                user_id TEXT PRIMARY KEY,
                name TEXT NOT NULL DEFAULT 'محمود',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        # المحادثات
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pro_messages (
                id BIGSERIAL PRIMARY KEY,
                user_id TEXT NOT NULL
                    REFERENCES pro_users(user_id)
                    ON DELETE CASCADE,
                role TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        # الذاكرة
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pro_memory (
                id BIGSERIAL PRIMARY KEY,
                user_id TEXT NOT NULL
                    REFERENCES pro_users(user_id)
                    ON DELETE CASCADE,

                category TEXT NOT NULL,
                memory_key TEXT NOT NULL,
                memory_value TEXT NOT NULL,

                importance INTEGER NOT NULL DEFAULT 5,

                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

                UNIQUE(user_id, category, memory_key)
            )
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_pro_memory_user
            ON pro_memory(user_id)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_pro_messages_user_id_id
            ON pro_messages(user_id, id DESC)
        """)

        conn.commit()

    finally:

        conn.close()


# =========================================================
# MEMORY FUNCTIONS
# =========================================================

ALLOWED_CATEGORIES = {
    "personal",
    "preferences",
    "projects",
    "important"
}


def save_memory(
    user_id,
    category,
    memory_key,
    memory_value,
    importance=5
):

    if category not in ALLOWED_CATEGORIES:
        return

    if not memory_key or not memory_value:
        return

    try:
        importance = int(importance)
    except:
        importance = 5

    importance = max(1, min(10, importance))

    conn = get_db()

    try:

        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO pro_memory
            (
                user_id,
                category,
                memory_key,
                memory_value,
                importance
            )
            VALUES (%s, %s, %s, %s, %s)

            ON CONFLICT (
                user_id,
                category,
                memory_key
            )

            DO UPDATE SET
                memory_value = EXCLUDED.memory_value,
                importance = EXCLUDED.importance,
                updated_at = NOW()
            """,

            (
                user_id,
                category,
                memory_key,
                memory_value,
                importance
            )
        )

        conn.commit()

    finally:

        conn.close()


def delete_memory(
    user_id,
    category,
    memory_key
):

    if not category or not memory_key:
        return

    conn = get_db()

    try:

        cur = conn.cursor()

        cur.execute(
            """
            DELETE FROM pro_memory
            WHERE user_id = %s
            AND category = %s
            AND memory_key = %s
            """,
            (
                user_id,
                category,
                memory_key
            )
        )

        conn.commit()

    finally:

        conn.close()


def get_memories(user_id):

    conn = get_db()

    try:

        cur = conn.cursor(
            cursor_factory=RealDictCursor
        )

        cur.execute(
            """
            SELECT
                category,
                memory_key,
                memory_value,
                importance
            FROM pro_memory

            WHERE user_id = %s

            ORDER BY
                importance DESC,
                updated_at DESC

            LIMIT 50
            """,
            (user_id,)
        )

        return cur.fetchall()

    finally:

        conn.close()


def format_memories(memories):

    if not memories:
        return "لا توجد معلومات محفوظة في الذاكرة."

    text = ""

    for memory in memories:

        text += (
            f"- [{memory['category']}] "
            f"{memory['memory_key']}: "
            f"{memory['memory_value']}\n"
        )

    return text


# =========================================================
# SAFE JSON PARSER
# =========================================================

def parse_ai_response(text):

    if not text:
        return {
            "reply": "صار خطأ في رد الوكيل.",
            "memories": [],
            "forget": []
        }

    cleaned = text.strip()

    # إزالة Markdown fences لو Gemini حطها
    cleaned = re.sub(
        r"^```(?:json)?\s*",
        "",
        cleaned,
        flags=re.IGNORECASE
    )

    cleaned = re.sub(
        r"\s*```$",
        "",
        cleaned
    )

    try:

        data = json.loads(cleaned)

    except Exception:

        # محاولة استخراج أول JSON object
        start = cleaned.find("{")
        end = cleaned.rfind("}")

        if start != -1 and end != -1 and end > start:

            try:

                data = json.loads(
                    cleaned[start:end + 1]
                )

            except Exception:

                return {
                    "reply": text,
                    "memories": [],
                    "forget": []
                }

        else:

            return {
                "reply": text,
                "memories": [],
                "forget": []
            }

    if not isinstance(data, dict):

        return {
            "reply": text,
            "memories": [],
            "forget": []
        }

    reply = data.get(
        "reply",
        ""
    )

    if not isinstance(reply, str):
        reply = str(reply)

    memories = data.get(
        "memories",
        []
    )

    forget = data.get(
        "forget",
        []
    )

    if not isinstance(memories, list):
        memories = []

    if not isinstance(forget, list):
        forget = []

    return {
        "reply": reply.strip(),
        "memories": memories,
        "forget": forget
    }


# =========================================================
# HTML
# =========================================================

HTML = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">

<head>

<meta charset="UTF-8">

<meta name="viewport"
      content="width=device-width, initial-scale=1.0">

<title>PRO AI Agent</title>

<style>

body {
    font-family: Arial, sans-serif;
    background: #111;
    color: white;
    margin: 0;
    padding: 20px;
}

.container {
    max-width: 600px;
    margin: auto;
}

h1 {
    text-align: center;
}

#chat {
    height: 60vh;
    overflow-y: auto;
    padding: 15px;
    background: #1c1c1c;
    border-radius: 15px;
    margin-bottom: 15px;
}

.message {
    padding: 10px;
    margin: 8px 0;
    border-radius: 10px;
    white-space: pre-wrap;
}

.user {
    background: #333;
}

.ai {
    background: #222;
}

form {
    display: flex;
    gap: 8px;
}

input {
    flex: 1;
    padding: 14px;
    border-radius: 10px;
    border: none;
    font-size: 16px;
}

button {
    padding: 14px 20px;
    border: none;
    border-radius: 10px;
}

</style>

</head>

<body>

<div class="container">

<h1>🤖 PRO AI Agent</h1>

<div id="chat">

<div class="message ai">
السلام عليكم محمود 👋
أنا PRO AI Agent.
شن نقدر نساعدك فيه اليوم؟
</div>

</div>

<form id="form">

<input
id="message"
placeholder="اكتب رسالتك..."
autocomplete="off"
>

<button type="submit">
إرسال
</button>

</form>

</div>

<script>

const form = document.getElementById("form");
const input = document.getElementById("message");
const chat = document.getElementById("chat");

let userId = localStorage.getItem("pro_ai_user_id");

if (!userId) {

    userId = crypto.randomUUID();

    localStorage.setItem(
        "pro_ai_user_id",
        userId
    );
}

form.addEventListener("submit", async function(e) {

    e.preventDefault();

    const message = input.value.trim();

    if (!message) {
        return;
    }

    chat.innerHTML +=
        '<div class="message user">' +
        message +
        '</div>';

    input.value = "";

    const loading = document.createElement("div");

    loading.className = "message ai";
    loading.textContent = "جاري التفكير...";

    chat.appendChild(loading);

    try {

        const response = await fetch("/chat", {

            method: "POST",

            headers: {
                "Content-Type": "application/json"
            },

            body: JSON.stringify({
                message:
