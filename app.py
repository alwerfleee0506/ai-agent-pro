from flask import Flask, request, jsonify, render_template_string
from google import genai
from google.genai import types
import os
import json
import re
import psycopg2
from psycopg2.extras import RealDictCursor
import time
import traceback


app = Flask(__name__)


# =========================================================
# Configuration
# =========================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DATABASE_URL = os.environ.get("DATABASE_URL")

# الهوية الموحدة لمحمود
# كل المتصفحات والأجهزة تستخدم نفس المستخدم
PRO_OWNER_ID = "mahmoud"

ALLOWED_CATEGORIES = {
    "personal",
    "preferences",
    "projects",
    "important"
}

# حدود حماية الذاكرة
MAX_MEMORY_KEY_LENGTH = 120
MAX_MEMORY_VALUE_LENGTH = 2000

# عدد الذكريات التي تدخل في Prompt
MAX_MEMORIES_FOR_PROMPT = 50

# عدد رسائل المحادثة التي تدخل في Prompt
MAX_MESSAGES_FOR_PROMPT = 20


# =========================================================
# Gemini
# =========================================================

if not GEMINI_API_KEY:
    print("[STARTUP] WARNING: GEMINI_API_KEY غير موجود")


client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options=types.HttpOptions(
        timeout=15000,
        retry_options=types.HttpRetryOptions(
            attempts=0,
            initial_delay=0,
            max_delay=0,
            jitter=0,
            http_status_codes=[999]
        )
    )
)


# =========================================================
# System Prompt
# =========================================================

SYSTEM_PROMPT = """
أنت PRO، وكيل الذكاء الاصطناعي الشخصي لمحمود.

===== هويتك =====

- اسمك: PRO.
- أنت مساعد ووكيل شخصي مخصص لمحمود.
- محمود هو المستخدم الأساسي الذي تتعامل معه.
- أنت لست مجرد chatbot؛ أنت وكيل شخصي مصمم لمساعدة محمود ومتابعة مشاريعه ومهامه وأهدافه.
- تعامل مع العلاقة مع محمود على أنها علاقة مستمرة وليست مجموعة محادثات منفصلة.

مهم:
العلاقة بين PRO ومحمود يمكن أن تكون أيضاً محفوظة في الذاكرة الدائمة.
إذا كانت هناك ذاكرة مثل:
projects/pro_role
فاستعملها باعتبارها معلومة محفوظة من محمود.

لا تعتمد على التخمين في المعلومات الشخصية.

===== الشخصية =====

- كن طبيعي وودود ومرن.
- كن مباشراً وعملياً.
- لا تكن رسمياً أو آلياً بشكل زائد.
- لا تكرر اسم محمود في كل رد.
- في العمل والمشاريع، ركز على الحل والخطوة التالية.
- إذا كان الطلب بسيطاً، لا تعطي شرحاً طويلاً بدون داعٍ.

===== اللغة =====

- تحدث مع محمود باللهجة الليبية الطبيعية.
- لا تستخدم اللهجة المصرية.
- المصطلحات التقنية يمكن أن تكون بالإنجليزية عندما تكون هي المصطلح المناسب.

===== الذاكرة =====

لديك ذاكرة دائمة يتم تزويدك بها في قسم:

===== الذاكرة =====

هذه الذاكرة تأتي من PostgreSQL وليست جزءاً ثابتاً من هذا الـ System Prompt.

استخدم المعلومات الموجودة في الذاكرة بشكل طبيعي.

لا تقل دائماً:
"حسب ذاكرتي"
أو
"أنا أتذكر أنك"

إلا إذا كان ذلك مهماً للسياق.

احفظ المعلومات المفيدة على المدى الطويل، ومنها:

- المعلومات الشخصية العامة.
- التفضيلات المستمرة.
- المشاريع المستمرة.
- مراحل المشاريع.
- الأهداف المهمة.
- إعدادات أو اختيارات مهمة.
- العلاقة أو الدور المستمر بين PRO ومحمود.
- المعلومات التي يطلب محمود صراحة حفظها.

===== مهم جداً في حفظ المشاريع =====

إذا قال محمود إن مشروعه الحالي هو مشروع معين، احفظه.

استخدم المفتاح:

projects/current_project

مثال:

"مشروعي الحالي PRO AI Agent"

يجب أن ينتج عنه Memory مناسبة مثل:

{
  "category": "projects",
  "memory_key": "current_project",
  "memory_value": "PRO AI Agent",
  "importance": 10
}

إذا ذكر محمود المرحلة الحالية لمشروع مستمر، احفظها باستخدام:

projects/current_stage

إذا ذكر محمود دور PRO بالنسبة له، مثل:

"PRO أنت وكيلي الشخصي"
"أنت الوكيل الشخصي متاعي"
"PRO هو وكيلي"
"أنت المساعد والوكيل الشخصي متاعي"

فهذه معلومة طويلة المدى ومهمة، ويجب حفظها حتى لو لم يقل حرفياً "احفظ".

استخدم:

projects/pro_role

مثال:

{
  "category": "projects",
  "memory_key": "pro_role",
  "memory_value": "PRO هو الوكيل الشخصي الدائم لمحمود",
  "importance": 10
}

لا تحفظ نفس المعلومة بمفاتيح مختلفة إذا كان يمكن استخدام نفس المفتاح.

إذا صحح محمود معلومة موجودة، استخدم نفس memory_key مع القيمة الجديدة.

===== ما لا يجب حفظه =====

لا تحفظ:

- الأسئلة العابرة.
- الكلام المؤقت.
- المعلومات التي لا قيمة لها مستقبلاً.
- كلمات المرور.
- مفاتيح API.
- أرقام البطاقات.
- بيانات الحسابات السرية.
- الموقع الدقيق.
- المعلومات الصحية الحساسة.

===== الحفظ الصريح =====

إذا قال محمود:

"احفظ..."
"تذكر..."
"خليها في ذاكرتك..."
"سجل..."

يجب أن تضع المعلومة في memories.

===== النسيان =====

إذا قال محمود:

"انسَ..."
"احذف من ذاكرتك..."
"خلي PRO ينساها..."

ضع المعلومة المناسبة في forget.

===== عدم اختراع الذكريات =====

لا تخترع أي معلومة شخصية.

إذا لم تكن المعلومة موجودة في الذاكرة أو المحادثة ولا تعرفها، قل إنك لا تعرفها.

===== المشاريع =====

تعامل مع المشاريع على أنها مستمرة.

استعمل الذاكرة لمعرفة:

- اسم المشروع.
- المرحلة الحالية.
- ما تم إنجازه.
- الخطوة التالية.
- المعلومات المهمة.

المشروع المعروف من سياق النظام هو:

PRO AI Agent

لكن لا تعتبر هذا السطر بديلاً عن الذاكرة.

إذا أعطاك محمود معلومات جديدة عن المشروع، احفظ المعلومات المناسبة في PostgreSQL من خلال memories.

===== تنفيذ المهام =====

إذا كانت أداة التنفيذ متوفرة فعلياً، استخدمها وفق صلاحياتها.

إذا لم تكن الأداة متوفرة، لا تدعي تنفيذ العملية.

===== WhatsApp =====

حالياً لا توجد أداة WhatsApp متصلة.

لذلك:

- لا تدعي إرسال WhatsApp.
- لا تدعي استقبال WhatsApp.
- لا تدعي إجراء مكالمة.
- لا تدعي تنفيذ إجراء خارجي غير موجود.

===== الدقة =====

- لا تخترع معلومات.
- لا تخترع ذكريات.
- لا تدعي تنفيذ شيء لم يتم تنفيذه.
- لا تدعي امتلاك أدوات غير موجودة.
- إذا حدث خطأ، وضحه.
- إذا كنت غير متأكد، لا تخمن.

===== المحادثة =====

قبل الإجابة:

1. اقرأ الذاكرة.
2. اقرأ سياق المحادثة.
3. افهم آخر رسالة.
4. أجب مباشرة.
5. استخدم المعلومات السابقة عندما تكون مرتبطة.

===== الفئات المسموحة =====

personal
preferences
projects
important

===== إخراج JSON =====

يجب أن يكون ردك JSON صالح فقط.

ممنوع استخدام Markdown.

ممنوع استخدام:

```json

الشكل:

{
  "reply": "الرد لمحمود",
  "memories": [],
  "forget": []
}

عند وجود معلومة للحفظ:

{
  "reply": "تم يا محمود.",
  "memories": [
    {
      "category": "projects",
      "memory_key": "pro_role",
      "memory_value": "PRO هو الوكيل الشخصي الدائم لمحمود",
      "importance": 10
    }
  ],
  "forget": []
}

عند تحديث معلومة:
استخدم نفس memory_key.

عند النسيان:

{
  "reply": "تمام، نسيتها.",
  "memories": [],
  "forget": [
    {
      "category": "projects",
      "memory_key": "pro_role"
    }
  ]
}

إذا لا توجد ذاكرة جديدة:

"memories": []

إذا لا يوجد نسيان:

"forget": []

مهم جداً:

لا تقل إنك حفظت معلومة إلا إذا أرسلتها فعلاً في memories.

لا تقل إنك نسيت معلومة إلا إذا أرسلتها فعلاً في forget.

أنت PRO، وكيل محمود الشخصي.
"""


# =========================================================
# Database
# =========================================================

def get_db():

    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL غير موجود في إعدادات Render"
        )

    return psycopg2.connect(
        DATABASE_URL,
        sslmode="require",
        connect_timeout=10
    )


# =========================================================
# Database Initialization
# =========================================================

def init_db():

    print("[DB] بدء تهيئة قاعدة البيانات")

    conn = get_db()

    try:

        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS pro_users (
                user_id TEXT PRIMARY KEY,
                name TEXT NOT NULL DEFAULT 'محمود',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

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

        cur.execute("""
            INSERT INTO pro_users (
                user_id,
                name
            )
            VALUES (%s, %s)
            ON CONFLICT (user_id)
            DO NOTHING
        """, (
            PRO_OWNER_ID,
            "محمود"
        ))

        conn.commit()

        print("[DB] تهيئة قاعدة البيانات تمت بنجاح")

    except Exception:

        conn.rollback()

        print("[DB] فشل تهيئة قاعدة البيانات")

        raise

    finally:

        conn.close()

    migrate_old_users()


# =========================================================
# Migrate Old Browser Users
# =========================================================

def migrate_old_users():

    print("[MIGRATION] Checking old user IDs...")

    conn = get_db()

    try:

        cur = conn.cursor(
            cursor_factory=RealDictCursor
        )

        cur.execute(
            """
            SELECT user_id
            FROM pro_users
            WHERE user_id <> %s
            ORDER BY created_at ASC
            """,
            (PRO_OWNER_ID,)
        )

        old_users = cur.fetchall()

        if not old_users:

            conn.commit()

            print(
                "[MIGRATION] No old users found."
            )

            return

        old_ids = [
            row["user_id"]
            for row in old_users
        ]

        print(
            "[MIGRATION] Old users found:",
            len(old_ids)
        )

        # -------------------------------------------------
        # Memories
        # -------------------------------------------------

        cur.execute(
            """
            SELECT
                user_id,
                category,
                memory_key,
                memory_value,
                importance,
                updated_at
            FROM pro_memory
            WHERE user_id <> %s
            ORDER BY updated_at DESC
            """,
            (PRO_OWNER_ID,)
        )

        old_memories = cur.fetchall()

        migrated_memories = 0

        for memory in old_memories:

            cur.execute(
                """
                INSERT INTO pro_memory
                (
                    user_id,
                    category,
                    memory_key,
                    memory_value,
                    importance,
                    created_at,
                    updated_at
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    NOW(),
                    %s
                )

                ON CONFLICT (
                    user_id,
                    category,
                    memory_key
                )

                DO UPDATE SET
                    memory_value = CASE
                        WHEN EXCLUDED.updated_at >
                             pro_memory.updated_at
                        THEN EXCLUDED.memory_value
                        ELSE pro_memory.memory_value
                    END,

                    importance = CASE
                        WHEN EXCLUDED.updated_at >
                             pro_memory.updated_at
                        THEN EXCLUDED.importance
                        ELSE pro_memory.importance
                    END,

                    updated_at = GREATEST(
                        pro_memory.updated_at,
                        EXCLUDED.updated_at
                    )
                """,
                (
                    PRO_OWNER_ID,
                    memory["category"],
                    memory["memory_key"],
                    memory["memory_value"],
                    memory["importance"],
                    memory["updated_at"]
                )
            )

            migrated_memories += 1

        print(
            "[MIGRATION] Memories processed:",
            migrated_memories
        )

        # -------------------------------------------------
        # Messages
        # -------------------------------------------------

        cur.execute(
            """
            SELECT
                role,
                message,
                created_at
            FROM pro_messages
            WHERE user_id <> %s
            ORDER BY id ASC
            """,
            (PRO_OWNER_ID,)
        )

        old_messages = cur.fetchall()

        migrated_messages = 0

        for message in old_messages:

            cur.execute(
                """
                INSERT INTO pro_messages
                (
                    user_id,
                    role,
                    message,
                    created_at
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    %s
                )
                """,
                (
                    PRO_OWNER_ID,
                    message["role"],
                    message["message"],
                    message["created_at"]
                )
            )

            migrated_messages += 1

        print(
            "[MIGRATION] Messages migrated:",
            migrated_messages
        )

        # -------------------------------------------------
        # Remove old users
        # -------------------------------------------------

        cur.execute(
            """
            DELETE FROM pro_users
            WHERE user_id <> %s
            """,
            (PRO_OWNER_ID,)
        )

        deleted_users = cur.rowcount

        conn.commit()

        print(
            "[MIGRATION] Old users removed:",
            deleted_users
        )

        print(
            "[MIGRATION] Migration completed successfully."
        )

    except Exception:

        conn.rollback()

        print(
            "[MIGRATION] Migration failed - ROLLBACK"
        )

        traceback.print_exc()

        raise

    finally:

        conn.close()


# =========================================================
# Memory Validation
# =========================================================

def clean_memory_key(value):

    if value is None:
        return ""

    value = str(value).strip()

    if not value:
        return ""

    if len(value) > MAX_MEMORY_KEY_LENGTH:
        value = value[:MAX_MEMORY_KEY_LENGTH].strip()

    return value


def clean_memory_value(value):

    if value is None:
        return ""

    value = str(value).strip()

    if not value:
        return ""

    if len(value) > MAX_MEMORY_VALUE_LENGTH:
        value = value[:MAX_MEMORY_VALUE_LENGTH].strip()

    return value


def normalize_category(value):

    if value is None:
        return ""

    return str(value).strip().lower()


# =========================================================
# Memory Functions
# =========================================================

def save_memory(
    user_id,
    category,
    memory_key,
    memory_value,
    importance=5
):

    category = normalize_category(category)
    memory_key = clean_memory_key(memory_key)
    memory_value = clean_memory_value(memory_value)

    if category not in ALLOWED_CATEGORIES:
        return False

    if not memory_key or not memory_value:
        return False

    try:

        importance = int(importance)

    except Exception:

        importance = 5

    importance = max(
        1,
        min(10, importance)
    )

    conn = get_db()

    try:

        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO pro_users (
                user_id,
                name
            )
            VALUES (%s, %s)

            ON CONFLICT (user_id)
            DO NOTHING
            """,
            (
                user_id,
                "محمود"
            )
        )

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

        return True

    except Exception:

        conn.rollback()

        raise

    finally:

        conn.close()


def delete_memory(
    user_id,
    category,
    memory_key
):

    category = normalize_category(category)
    memory_key = clean_memory_key(memory_key)

    if category not in ALLOWED_CATEGORIES:
        return False

    if not memory_key:
        return False

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

        deleted = cur.rowcount > 0

        conn.commit()

        return deleted

    except Exception:

        conn.rollback()

        raise

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
            LIMIT %s
            """,
            (
                user_id,
                MAX_MEMORIES_FOR_PROMPT
            )
        )

        return cur.fetchall()

    finally:

        conn.close()


def format_memories(memories):

    if not memories:
        return "لا توجد معلومات محفوظة."

    result = []

    for memory in memories:

        result.append(
            "- [{}] {}: {}".format(
                memory["category"],
                memory["memory_key"],
                memory["memory_value"]
            )
        )

    return "\n".join(result)


# =========================================================
# AI Response Parser
# =========================================================

def parse_ai_response(text):

    if not text:

        return {
            "reply": "ما قدرتش نطلع رد.",
            "memories": [],
            "forget": []
        }

    cleaned = str(text).strip()

    # إزالة Markdown fences
    cleaned = re.sub(
        r"^```json\s*",
        "",
        cleaned,
        flags=re.IGNORECASE
    )

    cleaned = re.sub(
        r"^```\s*",
        "",
        cleaned
    )

    cleaned = re.sub(
        r"\s*```$",
        "",
        cleaned
    )

    data = None

    # محاولة JSON مباشرة
    try:

        data = json.loads(cleaned)

    except Exception:

        pass

    # محاولة استخراج JSON
    if data is None:

        start = cleaned.find("{")
        end = cleaned.rfind("}")

        if start != -1 and end > start:

            try:

                data = json.loads(
                    cleaned[start:end + 1]
                )

            except Exception:

                data = None

    # إذا فشل JSON
    if not isinstance(data, dict):

        return {
            "reply": cleaned,
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

    clean_memories = []

    for memory in memories:

        if not isinstance(memory, dict):
            continue

        category = normalize_category(
            memory.get("category")
        )

        memory_key = clean_memory_key(
            memory.get("memory_key")
        )

        memory_value = clean_memory_value(
            memory.get("memory_value")
        )

        if category not in ALLOWED_CATEGORIES:
            continue

        if not memory_key:
            continue

        if not memory_value:
            continue

        importance = memory.get(
            "importance",
            5
        )

        try:
            importance = int(importance)
        except Exception:
            importance = 5

        importance = max(
            1,
            min(10, importance)
        )

        clean_memories.append({
            "category": category,
            "memory_key": memory_key,
            "memory_value": memory_value,
            "importance": importance
        })

    clean_forget = []

    for memory in forget:

        if not isinstance(memory, dict):
            continue

        category = normalize_category(
            memory.get("category")
        )

        memory_key = clean_memory_key(
            memory.get("memory_key")
        )

        if category not in ALLOWED_CATEGORIES:
            continue

        if not memory_key:
            continue

        clean_forget.append({
            "category": category,
            "memory_key": memory_key
        })

    return {
        "reply": reply.strip(),
        "memories": clean_memories,
        "forget": clean_forget
    }


# =========================================================
# HTML / JavaScript
# =========================================================

HTML = r"""
<!DOCTYPE html>
<html lang="ar" dir="rtl">

<head>

<meta charset="UTF-8">

<meta name="viewport"
content="width=device-width, initial-scale=1.0">

<title>PRO AI Agent</title>

<style>

* {
    box-sizing: border-box;
}

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
    min-height: 300px;
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
    word-wrap: break-word;
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
    min-width: 0;
    padding: 14px;
    border-radius: 10px;
    border: none;
    font-size: 16px;
}

button {
    padding: 14px 20px;
    border: none;
    border-radius: 10px;
    cursor: pointer;
    font-size: 16px;
}

button:disabled,
input:disabled {
    opacity: 0.6;
}

.status {
    text-align: center;
    font-size: 13px;
    color: #aaa;
    margin-top: 8px;
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

<button
id="sendButton"
type="submit"
>
إرسال
</button>

</form>

<div id="status" class="status"></div>

</div>

<script>

"use strict";

const form = document.getElementById("form");
const input = document.getElementById("message");
const chat = document.getElementById("chat");
const sendButton = document.getElementById("sendButton");
const statusElement = document.getElementById("status");

let requestRunning = false;


function escapeHtml(text) {

    const div = document.createElement("div");

    div.textContent = text;

    return div.innerHTML;
}


function scrollChat() {

    chat.scrollTop = chat.scrollHeight;

}


function setBusy(busy) {

    requestRunning = busy;

    sendButton.disabled = busy;
    input.disabled = busy;

    if (busy) {

        statusElement.textContent =
            "PRO يعالج الرسالة...";

    } else {

        statusElement.textContent = "";

    }

}


form.addEventListener(
    "submit",
    async function(e) {

        e.preventDefault();

        if (requestRunning) {
            return;
        }

        const message = input.value.trim();

        if (!message) {

            input.focus();

            return;

        }

        setBusy(true);

        chat.innerHTML +=
            '<div class="message user">' +
            escapeHtml(message) +
            '</div>';

        input.value = "";

        const loading =
            document.createElement("div");

        loading.className = "message ai";
        loading.textContent = "جاري التفكير...";

        chat.appendChild(loading);

        scrollChat();


        const controller =
            new AbortController();


        const timeoutId =
            setTimeout(
                function() {

                    controller.abort();

                },
                55000
            );


        try {

            const response =
                await fetch(
                    "/chat",
                    {
                        method: "POST",

                        headers: {
                            "Content-Type":
                                "application/json",

                            "Accept":
                                "application/json"
                        },

                        body: JSON.stringify({
                            message: message
                        }),

                        signal: controller.signal
                    }
                );


            const text =
                await response.text();


            let data = null;


            try {

                data = JSON.parse(text);

            } catch (jsonError) {

                console.error(
                    "Invalid JSON:",
                    text
                );

                throw new Error(
                    "الخادم رجع استجابة غير صالحة"
                );

            }


            if (!response.ok) {

                loading.textContent =
                    data.error ||
                    "حدث خطأ داخل الخادم.";

            } else {

                loading.textContent =
                    data.reply ||
                    "PRO ما رجعش رد.";

            }


        } catch (error) {

            console.error(
                "CHAT ERROR:",
                error
            );


            if (
                error &&
                error.name === "AbortError"
            ) {

                loading.textContent =
                    "الطلب أخذ وقت طويل. جرب مرة ثانية.";

            } else {

                loading.textContent =
                    "تعذر الاتصال بالوكيل.\n" +
                    "راجع Logs في Render.";

            }

        } finally {

            clearTimeout(timeoutId);

            setBusy(false);

            input.focus();

            scrollChat();

        }

    }
);


input.addEventListener(
    "keydown",
    function(e) {

        if (
            e.key === "Enter" &&
            !e.shiftKey
        ) {

            e.preventDefault();

            if (!requestRunning) {

                form.requestSubmit();

            }

        }

    }
);


input.focus();

</script>

</body>

</html>
"""


# =========================================================
# Routes
# =========================================================

@app.route("/")
def home():

    return render_template_string(HTML)


@app.route(
    "/health",
    methods=["GET"]
)
def health():

    return jsonify({
        "status": "ok",
        "service": "PRO AI Agent"
    })


# =========================================================
# MEMORY TEST
# =========================================================

@app.route(
    "/memory-test",
    methods=["GET"]
)
def memory_test():

    user_id = PRO_OWNER_ID

    test_category = "important"
    test_key = "memory_test"

    test_value_1 = "اختبار ذاكرة PRO يعمل"
    test_value_2 = "اختبار تحديث الذاكرة يعمل"

    try:

        print("")
        print("====================================")
        print("[MEMORY TEST] START")

        save_memory(
            user_id,
            test_category,
            test_key,
            test_value_1,
            7
        )

        memories = get_memories(
            user_id
        )

        found = next(
            (
                m for m in memories
                if
                m["category"] == test_category
                and
                m["memory_key"] == test_key
            ),
            None
        )

        if not found:
            raise RuntimeError(
                "فشل حفظ الذاكرة"
            )

        save_memory(
            user_id,
            test_category,
            test_key,
            test_value_2,
            9
        )

        memories = get_memories(
            user_id
        )

        updated = next(
            (
                m for m in memories
                if
                m["category"] == test_category
                and
                m["memory_key"] == test_key
            ),
            None
        )

        if not updated:
            raise RuntimeError(
                "فشل العثور على الذاكرة بعد التحديث"
            )

        if updated["memory_value"] != test_value_2:
            raise RuntimeError(
                "فشل تحديث قيمة الذاكرة"
            )

        delete_memory(
            user_id,
            test_category,
            test_key
        )

        memories = get_memories(
            user_id
        )

        deleted = next(
            (
                m for m in memories
                if
                m["category"] == test_category
                and
                m["memory_key"] == test_key
            ),
            None
        )

        if deleted:
            raise RuntimeError(
                "فشل حذف الذاكرة"
            )

        print(
            "[MEMORY TEST] ALL TESTS PASSED"
        )

        print(
            "===================================="
        )

        return jsonify({
            "status": "ok",
            "message": "اختبار الذاكرة نجح بالكامل",
            "tests": {
                "save": True,
                "read": True,
                "update": True,
                "delete": True
            }
        })

    except Exception as e:

        print(
            "[MEMORY TEST] FAILED:",
            str(e)
        )

        traceback.print_exc()

        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


# =========================================================
# MEMORY AI TEST
# =========================================================

@app.route(
    "/memory-ai-test",
    methods=["GET"]
)
def memory_ai_test():

    user_id = PRO_OWNER_ID

    test_category = "projects"
    test_key = "pro_role"

    test_value_1 = (
        "PRO هو الوكيل الذكي الشخصي لمحمود"
    )

    test_value_2 = (
        "PRO هو الوكيل الشخصي الدائم لمحمود"
    )

    try:

        print("")
        print("====================================")
        print("[MEMORY AI TEST] START")

        fake_ai_output = json.dumps(
            {
                "reply": "تم يا محمود.",
                "memories": [
                    {
                        "category": test_category,
                        "memory_key": test_key,
                        "memory_value": test_value_1,
                        "importance": 10
                    }
                ],
                "forget": []
            },
            ensure_ascii=False
        )

        result = parse_ai_response(
            fake_ai_output
        )

        if result["reply"] != "تم يا محمود.":
            raise RuntimeError(
                "فشل reply"
            )

        if len(result["memories"]) != 1:
            raise RuntimeError(
                "Parser لم يرجع memory واحدة"
            )

        memory = result["memories"][0]

        if memory["category"] != test_category:
            raise RuntimeError(
                "category غير صحيحة"
            )

        if memory["memory_key"] != test_key:
            raise RuntimeError(
                "memory_key غير صحيح"
            )

        if memory["memory_value"] != test_value_1:
            raise RuntimeError(
                "memory_value غير صحيحة"
            )

        if memory["importance"] != 10:
            raise RuntimeError(
                "importance غير صحيحة"
            )

        save_memory(
            user_id,
            memory["category"],
            memory["memory_key"],
            memory["memory_value"],
            memory["importance"]
        )

        memories = get_memories(
            user_id
        )

        saved = next(
            (
                m for m in memories
                if
                m["category"] == test_category
                and
                m["memory_key"] == test_key
            ),
            None
        )

        if not saved:
            raise RuntimeError(
                "فشل حفظ memory"
            )

        save_memory(
            user_id,
            test_category,
            test_key,
            test_value_2,
            10
        )

        memories = get_memories(
            user_id
        )

        updated = next(
            (
                m for m in memories
                if
                m["category"] == test_category
                and
                m["memory_key"] == test_key
            ),
            None
        )

        if not updated:
            raise RuntimeError(
                "فشل تحديث memory"
            )

        if updated["memory_value"] != test_value_2:
            raise RuntimeError(
                "قيمة memory بعد التحديث خاطئة"
            )

        delete_memory(
            user_id,
            test_category,
            test_key
        )

        memories = get_memories(
            user_id
        )

        deleted = next(
            (
                m for m in memories
                if
                m["category"] == test_category
                and
                m["memory_key"] == test_key
            ),
            None
        )

        if deleted:
            raise RuntimeError(
                "فشل حذف memory"
            )

        print(
            "[MEMORY AI TEST] ALL TESTS PASSED"
        )

        print(
            "===================================="
        )

        return jsonify({
            "status": "ok",
            "message": "اختبار مسار الذاكرة AI نجح بالكامل",
            "tests": {
                "fake_ai_json": True,
                "parser": True,
                "memory_save": True,
                "memory_read": True,
                "memory_update": True,
                "memory_delete": True
            }
        })

    except Exception as e:

        print(
            "[MEMORY AI TEST] FAILED:",
            str(e)
        )

        traceback.print_exc()

        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


# =========================================================
# MEMORY CONTEXT TEST
# =========================================================

@app.route(
    "/memory-context-test",
    methods=["GET"]
)
def memory_context_test():

    user_id = PRO_OWNER_ID

    test_category = "important"

    test_key = "memory_context_test_73921"

    test_value = "MEMORY_ONLY_TEST_73921"

    tests = {
        "memory_saved": False,
        "memory_retrieved": False,
        "memory_formatted": False,
        "memory_in_prompt": False,
        "memory_deleted": False
    }

    try:

        print("")
        print("====================================")
        print("[MEMORY CONTEXT TEST] START")

        if test_value in SYSTEM_PROMPT:

            raise RuntimeError(
                "قيمة الاختبار موجودة داخل SYSTEM_PROMPT"
            )

        save_memory(
            user_id,
            test_category,
            test_key,
            test_value,
            10
        )

        tests["memory_saved"] = True

        memories = get_memories(
            user_id
        )

        found = next(
            (
                m for m in memories
                if
                m["category"] == test_category
                and
                m["memory_key"] == test_key
                and
                m["memory_value"] == test_value
            ),
            None
        )

        if not found:

            raise RuntimeError(
                "الذاكرة التجريبية لم ترجع من PostgreSQL"
            )

        tests["memory_retrieved"] = True

        memory_text = format_memories(
            memories
        )

        if test_value not in memory_text:
            raise RuntimeError(
                "القيمة غير موجودة في memory_text"
            )

        if test_key not in memory_text:
            raise RuntimeError(
                "memory_key غير موجود في memory_text"
            )

        tests["memory_formatted"] = True

        test_conversation = (
            "محمود: اختبار ربط الذاكرة\n"
        )

        prompt = (
            SYSTEM_PROMPT
            + "\n\n===== الذاكرة =====\n"
            + memory_text
            + "\n\n===== المحادثة =====\n"
            + test_conversation
            + "\n\nأجب على آخر رسالة."
        )

        if test_value not in prompt:
            raise RuntimeError(
                "الذاكرة لم تدخل داخل prompt"
            )

        if test_key not in prompt:
            raise RuntimeError(
                "memory_key لم يدخل داخل prompt"
            )

        tests["memory_in_prompt"] = True

        memory_position = prompt.find(
            "===== الذاكرة ====="
        )

        conversation_position = prompt.find(
            "===== المحادثة ====="
        )

        if memory_position == -1:
            raise RuntimeError(
                "قسم الذاكرة غير موجود"
            )

        if conversation_position == -1:
            raise RuntimeError(
                "قسم المحادثة غير موجود"
            )

        if memory_position >= conversation_position:
            raise RuntimeError(
                "ترتيب prompt غير صحيح"
            )

        delete_memory(
            user_id,
            test_category,
            test_key
        )

        memories = get_memories(
            user_id
        )

        deleted = next(
            (
                m for m in memories
                if
                m["category"] == test_category
                and
                m["memory_key"] == test_key
            ),
            None
        )

        if deleted:
            raise RuntimeError(
                "فشل حذف ذاكرة الاختبار"
            )

        tests["memory_deleted"] = True

        print(
            "[MEMORY CONTEXT TEST] ALL TESTS PASSED"
        )

        print(
            "===================================="
        )

        return jsonify({
            "status": "ok",
            "message": "اختبار ربط الذاكرة بسياق PRO نجح بالكامل",
            "tests": tests
        })

    except Exception as e:

        print(
            "[MEMORY CONTEXT TEST] FAILED:",
            str(e)
        )

        traceback.print_exc()

        try:

            delete_memory(
                user_id,
                test_category,
                test_key
            )

        except Exception:

            traceback.print_exc()

        return jsonify({
            "status": "error",
            "message": str(e),
            "tests": tests
        }), 500


# =========================================================
# CHAT
# =========================================================

@app.route(
    "/chat",
    methods=["POST"]
)
def chat():

    request_start = time.time()

    print("")
    print("====================================")
    print("[CHAT] START")

    try:

        data = request.get_json(
            silent=True
        ) or {}

        message = str(
            data.get("message", "")
        ).strip()

        user_id = PRO_OWNER_ID

        if not message:

            return jsonify({
                "error": "اكتب رسالة أولاً"
            }), 400

        print(
            "[CHAT] user_id:",
            user_id
        )

        print(
            "[CHAT] message:",
            message[:150]
        )

        # -------------------------------------------------
        # Save user message
        # -------------------------------------------------

        conn = get_db()

        try:

            cur = conn.cursor(
                cursor_factory=RealDictCursor
            )

            cur.execute(
                """
                INSERT INTO pro_users (
                    user_id,
                    name
                )
                VALUES (%s, %s)

                ON CONFLICT (user_id)
                DO NOTHING
                """,
                (
                    user_id,
                    "محمود"
                )
            )

            cur.execute(
                """
                INSERT INTO pro_messages
                (
                    user_id,
                    role,
                    message
                )
                VALUES (%s, %s, %s)
                """,
                (
                    user_id,
                    "user",
                    message
                )
            )

            conn.commit()

            # -------------------------------------------------
            # Load conversation
            # -------------------------------------------------

            cur.execute(
                """
                SELECT
                    role,
                    message
                FROM pro_messages
                WHERE user_id = %s
                ORDER BY id DESC
                LIMIT %s
                """,
                (
                    user_id,
                    MAX_MESSAGES_FOR_PROMPT
                )
            )

            rows = list(
                reversed(
                    cur.fetchall()
                )
            )

        except Exception:

            conn.rollback()

            raise

        finally:

            conn.close()

        print(
            "[DB] Conversation loaded:",
            len(rows)
        )

        # -------------------------------------------------
        # Load persistent memory
        # -------------------------------------------------

        memories = get_memories(
            user_id
        )

        memory_text = format_memories(
            memories
        )

        print(
            "[MEMORY] Loaded:",
            len(memories),
            "memories"
        )

        # -------------------------------------------------
        # Build conversation
        # -------------------------------------------------

        conversation_parts = []

        for item in rows:

            if item["role"] == "user":

                speaker = "محمود"

            else:

                speaker = "PRO AI Agent"

            conversation_parts.append(
                speaker
                + ": "
                + str(item["message"])
            )

        conversation = "\n".join(
            conversation_parts
        )

        # -------------------------------------------------
        # Build final prompt
        # -------------------------------------------------

        prompt = (
            SYSTEM_PROMPT
            + "\n\n===== الذاكرة =====\n"
            + memory_text
            + "\n\n===== المحادثة =====\n"
            + conversation
            + "\n\nأجب على آخر رسالة."
        )

        print(
            "[PROMPT] Length:",
            len(prompt)
        )

        # -------------------------------------------------
        # Gemini
        # -------------------------------------------------

        print(
            "[GEMINI] Calling Gemini..."
        )

        gemini_start = time.time()

        try:

            interaction = client.interactions.create(
                model="gemini-3.6-flash",
                input=prompt
            )

        except Exception as gemini_error:

            gemini_time = (
                time.time()
                - gemini_start
            )

            error_text = str(
                gemini_error
            )

            print(
                "[GEMINI] ERROR after",
                round(gemini_time, 2),
                "seconds"
            )

            print(
                "[GEMINI] ERROR TYPE:",
                type(gemini_error).__name__
            )

            print(
                "[GEMINI] ERROR:",
                error_text
            )

            traceback.print_exc()

            if (
                "429" in error_text
                or
                "Too Many Requests" in error_text
                or
                "RESOURCE_EXHAUSTED" in error_text
                or
                "quota" in error_text.lower()
            ):

                return jsonify({
                    "error":
                        "Gemini غير متاح حالياً بسبب تجاوز حد الاستخدام. "
                        "قاعدة بيانات وذاكرة PRO شغالات بشكل طبيعي. "
                        "جرب بعد ما يتجدد الحد."
                }), 429

            return jsonify({
                "error":
                    "صار خطأ في الاتصال بـ Gemini: "
                    + error_text
            }), 502

        gemini_time = (
            time.time()
            - gemini_start
        )

        print(
            "[GEMINI] Response received in",
            round(gemini_time, 2),
            "seconds"
        )

        raw_output = getattr(
            interaction,
            "output_text",
            None
        )

        if not raw_output:

            raise RuntimeError(
                "Gemini رجع استجابة بدون نص"
            )

        print(
            "[GEMINI] Output length:",
            len(raw_output)
        )

        # -------------------------------------------------
        # Parse
        # -------------------------------------------------

        result = parse_ai_response(
            raw_output
        )

        print(
            "[MEMORY DEBUG] Parsed result:"
        )

        print(
            json.dumps(
                result,
                ensure_ascii=False,
                indent=2
            )
        )

        print(
            "[MEMORY DEBUG] memories count:",
            len(result["memories"])
        )

        print(
            "[MEMORY DEBUG] forget count:",
            len(result["forget"])
        )

        reply = result["reply"]

        if not reply:

            reply = "تمام يا محمود."

        # -------------------------------------------------
        # Save memories generated by Gemini
        # -------------------------------------------------

        print(
            "[MEMORY] Processing memories..."
        )

        saved_count = 0

        for memory in result["memories"]:

            try:

                saved = save_memory(
                    user_id,
                    memory["category"],
                    memory["memory_key"],
                    memory["memory_value"],
                    memory["importance"]
                )

                if saved:

                    saved_count += 1

                    print(
                        "[MEMORY] SAVED:",
                        memory["category"],
                        memory["memory_key"]
                    )

            except Exception as memory_error:

                print(
                    "[MEMORY] SAVE ERROR:",
                    str(memory_error)
                )

                traceback.print_exc()

        print(
            "[MEMORY] Saved:",
            saved_count
        )

        # -------------------------------------------------
        # Forget memories
        # -------------------------------------------------

        deleted_count = 0

        for memory in result["forget"]:

            try:

                deleted = delete_memory(
                    user_id,
                    memory["category"],
                    memory["memory_key"]
                )

                if deleted:

                    deleted_count += 1

                    print(
                        "[MEMORY] FORGOTTEN:",
                        memory["category"],
                        memory["memory_key"]
                    )

            except Exception as forget_error:

                print(
                    "[MEMORY] DELETE ERROR:",
                    str(forget_error)
                )

                traceback.print_exc()

        print(
            "[MEMORY] Deleted:",
            deleted_count
        )

        # -------------------------------------------------
        # Save assistant reply
        # -------------------------------------------------

        conn = get_db()

        try:

            cur = conn.cursor()

            cur.execute(
                """
                INSERT INTO pro_messages
                (
                    user_id,
                    role,
                    message
                )
                VALUES (%s, %s, %s)
                """,
                (
                    user_id,
                    "assistant",
                    reply
                )
            )

            conn.commit()

        except Exception:

            conn.rollback()

            raise

        finally:

            conn.close()

        # -------------------------------------------------
        # Done
        # -------------------------------------------------

        total_time = (
            time.time()
            - request_start
        )

        print(
            "[CHAT] DONE in",
            round(total_time, 2),
            "seconds"
        )

        print(
            "===================================="
        )

        return jsonify({
            "reply": reply
        })

    except Exception as e:

        elapsed = (
            time.time()
            - request_start
        )

        print(
            "[CHAT] ERROR after",
            round(elapsed, 2),
            "seconds"
        )

        print(
            "[CHAT] ERROR TYPE:",
            type(e).__name__
        )

        print(
            "[CHAT] ERROR:",
            str(e)
        )

        traceback.print_exc()

        print(
            "===================================="
        )

        return jsonify({
            "error":
                "صار خطأ داخل الوكيل: "
                + str(e)
        }), 500


# =========================================================
# Startup
# =========================================================

print("")
print("====================================")
print("PRO AI Agent starting...")
print("====================================")

try:

    init_db()

except Exception as e:

    print(
        "[STARTUP] Database initialization failed:"
    )

    print(
        str(e)
    )

    traceback.print_exc()


# =========================================================
# Local Run
# =========================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
