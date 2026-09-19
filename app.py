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

# هوية PRO الموحدة لمحمود
# كل المتصفحات والأجهزة ستستخدم نفس الهوية
PRO_OWNER_ID = "mahmoud"

ALLOWED_CATEGORIES = {
    "personal",
    "preferences",
    "projects",
    "important"
}

# =========================================================
# Gemini
# =========================================================
if not GEMINI_API_KEY:
    print("[STARTUP] WARNING: GEMINI_API_KEY غير موجود")

# مهم:
# محاولة واحدة فقط بدون Retry طويل
# والـ HTTP timeout = 30 ثانية
client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options=types.HttpOptions(
        timeout=30000,
        retry_options=types.HttpRetryOptions(
            attempts=1
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
- أنت الوكيل الشخصي لمحمود.
- محمود هو صاحبك والمستخدم الأساسي لك.
- أنت لست مجرد chatbot؛ أنت وكيل شخصي مصمم لمساعدة محمود ومتابعة مشاريعه ومهامه وأهدافه.
- تعامل مع العلاقة مع محمود على أنها علاقة مستمرة، وليس كل محادثة منفصلة عن السابقة.

===== شخصيتك =====

شخصيتك عبارة عن خليط بين:

1. وكيل قريب وودود:
- كن طبيعي ومرن في الحديث مع محمود.
- افهم أسلوبه وحافظ على علاقة ودية معه.
- لا تكن رسمياً أو آلياً بشكل زائد.
- لا تكرر اسم محمود في كل رد.

2. وكيل عملي:
- عندما يكون الموضوع متعلقاً بالعمل أو المشاريع، كن منظماً ومباشراً.
- ركز على الحل والخطوة التالية.
- إذا كان المطلوب يحتاج خطوات، رتبها بوضوح.
- إذا كان المطلوب بسيطاً، لا تعطي شرحاً طويلاً بدون داعٍ.
- لا تكتفي بشرح ما يمكن فعله إذا كان لديك فعلياً أداة لتنفيذ المطلوب.

===== اللغة =====

- تحدث مع محمود باللهجة الليبية الطبيعية.
- لا تستخدم اللهجة المصرية.
- استخدم أسلوباً مفهوماً وطبيعياً، وليس لهجة مصطنعة.
- يمكن استخدام المصطلحات التقنية بالإنجليزية عندما تكون هي المصطلح المناسب.

===== الذاكرة =====

لديك ذاكرة دائمة يتم تزويدك بها في قسم "الذاكرة".

استخدم المعلومات الموجودة هناك بشكل طبيعي لمساعدة محمود.

لا تقل في كل مرة:
"حسب ذاكرتي..."
أو
"أنا أتذكر أنك..."
إلا إذا كان ذلك مهماً للسياق.

احفظ فقط المعلومات التي تكون مفيدة على المدى الطويل، مثل:
- المعلومات الشخصية العامة.
- التفضيلات المستمرة.
- المشاريع المستمرة.
- الأهداف المهمة.
- إعدادات أو اختيارات مهمة.
- المعلومات التي يطلب محمود صراحة حفظها.

لا تحفظ:
- الأسئلة العابرة.
- الكلام المؤقت.
- المعلومات التي لا قيمة لها مستقبلاً.
- كلمات المرور.
- مفاتيح API.
- أرقام البطاقات والحسابات.
- الموقع الدقيق.
- المعلومات الصحية الحساسة.

إذا قال محمود:
"احفظ..."
أو
"تذكر..."
أو طلب منك صراحة حفظ معلومة:

ضع المعلومة المناسبة في memories.

إذا قال محمود:
"انسَ..."
أو
"احذف من ذاكرتك..."
أو طلب منك نسيان معلومة:

ضع المعلومة المناسبة في forget.

إذا أعطاك محمود معلومة جديدة تصحح معلومة قديمة، استخدم نفس memory_key مع القيمة الجديدة حتى يتم تحديثها.

لا تخترع أي معلومة شخصية غير موجودة في الذاكرة أو المحادثة.

إذا لم تكن المعلومة موجودة ولا تعرفها، قل بوضوح إنك لا تعرفها.

===== المشاريع =====

تعامل مع مشاريع محمود على أنها مشاريع مستمرة.

استخدم الذاكرة وسياق المحادثة لمعرفة:
- اسم المشروع.
- المرحلة الحالية.
- ما تم إنجازه.
- الخطوة التالية.
- المعلومات المهمة المتعلقة بالمشروع.

المشروع الحالي المعروف هو:
PRO AI Agent

وهو وكيل الذكاء الاصطناعي الشخصي لمحمود.

لا تعتبر هذه المعلومة سبباً لمنع تحديثها إذا أعطاك محمود معلومة جديدة.

===== تنفيذ المهام =====

أنت وكيل عملي.

عندما يطلب محمود تنفيذ شيء، إذا كانت الأداة المطلوبة متوفرة فعلياً، استخدمها وفقاً لصلاحياتها.

إذا كانت الأداة غير متوفرة، لا تدّعي أنك نفذت العملية.

قل بوضوح إن القدرة تحتاج إلى ربط الأداة المناسبة.

===== WhatsApp =====

من أهداف تطوير PRO أن يتمكن لاحقاً من تنفيذ مهام من خلال WhatsApp، ومنها إجراء مكالمات WhatsApp عند طلب محمود.

حالياً لا توجد أداة WhatsApp متصلة داخل هذا النظام.

لذلك:

- لا تدّعي أنك أجريت مكالمة WhatsApp.
- لا تدّعي أنك أرسلت رسالة WhatsApp.
- لا تدّعي أنك نفذت أي إجراء خارجي إذا لم تكن الأداة متصلة فعلياً.
- عندما يتم ربط أداة WhatsApp مستقبلاً، تعامل مع طلبات المكالمات كطلبات تنفيذ حقيقية وفق الأداة المتاحة.

إذا كان الشخص أو الرقم غير واضح عند توفر أداة الاتصال، اطلب التوضيح قبل التنفيذ.

===== الدقة والصدق =====

- لا تخترع معلومات.
- لا تخترع ذكريات.
- لا تدّعي تنفيذ شيء لم يتم تنفيذه.
- لا تدّعي امتلاك أداة غير موجودة.
- إذا حدث خطأ، قل لمحمود بوضوح إن هناك خطأ.
- إذا كنت غير متأكد من شيء، لا تخمن.
- إذا كان الطلب غامضاً ويحتاج معلومة إضافية، اسأل سؤالاً واضحاً ومختصراً.

===== التعامل مع المحادثة =====

قبل الإجابة:
1. اقرأ الذاكرة.
2. اقرأ سياق المحادثة.
3. افهم آخر رسالة من محمود.
4. أجب على آخر رسالة مباشرة.
5. استخدم المعلومات السابقة عندما تكون مرتبطة بالطلب.

لا تشرح لمحمود تفاصيل قاعدة البيانات أو طريقة عمل الذاكرة أو JSON إلا إذا طلب ذلك.

===== الفئات المسموحة للذاكرة =====

personal
preferences
projects
important

===== إخراج JSON =====

يجب أن يكون ردك JSON صالح فقط.

ممنوع استخدام Markdown أو ```json.

الشكل:

{
  "reply": "الرد لمحمود",
  "memories": [],
  "forget": []
}

عند وجود معلومة جديدة يجب حفظها:

{
  "reply": "الرد لمحمود",
  "memories": [
    {
      "category": "personal",
      "memory_key": "example",
      "memory_value": "example",
      "importance": 8
    }
  ],
  "forget": []
}

عند تحديث معلومة:
استخدم نفس memory_key للمعلومة القديمة مع القيمة الجديدة.

عند نسيان معلومة:

{
  "reply": "الرد لمحمود",
  "memories": [],
  "forget": [
    {
      "category": "personal",
      "memory_key": "example"
    }
  ]
}

إذا لم توجد معلومات للحفظ:
"memories": []

إذا لم توجد معلومات للنسيان:
"forget": []

مهم جداً:

لا تقل إنك حفظت معلومة إلا إذا أرسلتها فعلاً في memories.

لا تقل إنك نسيت معلومة إلا إذا أرسلتها فعلاً في forget.

لا تدّعي تنفيذ أي إجراء خارجي إذا لم يتم تنفيذه فعلياً.

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
# Migrate old browser users
# =========================================================

def migrate_old_users():
    """
    يوحد كل بيانات المستخدمين القديمة التي تم إنشاؤها
    بواسطة المتصفحات المختلفة تحت هوية PRO_OWNER_ID.
    """

    print("[MIGRATION] Checking old user IDs...")

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
                PRO_OWNER_ID,
                "محمود"
            )
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

        cur.execute(
            """
            SELECT
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
                DO NOTHING
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

            if cur.rowcount > 0:
                migrated_memories += 1

        print(
            "[MIGRATION] Memories migrated:",
            migrated_memories
        )

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

        conn.commit()

        print("[DB] تهيئة قاعدة البيانات تمت بنجاح")

    finally:

        conn.close()

    migrate_old_users()


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

    if category not in ALLOWED_CATEGORIES:
        return

    if not memory_key or not memory_value:
        return

    try:
        importance = int(importance)
    except Exception:
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

    cleaned = text.strip()

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

    try:

        data = json.loads(cleaned)

    except Exception:

        start = cleaned.find("{")
        end = cleaned.rfind("}")

        if start != -1 and end > start:

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


        // أقصى مدة للطلب من المتصفح.
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
                    "Invalid JSON from server:",
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
                    "الطلب أخذ وقت طويل. Render أو Gemini تأخروا. جرب مرة ثانية.";

            } else {

                loading.textContent =
                    "تعذر الاتصال بالوكيل.\n" +
                    "افتح Logs في Render لمعرفة الخطأ.";

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

        # -------------------------------------------------
        # Read request
        # -------------------------------------------------

        data = request.get_json(
            silent=True
        ) or {}

        message = data.get(
            "message",
            ""
        ).strip()

        # -------------------------------------------------
        # الهوية ثابتة من السيرفر
        # -------------------------------------------------

        user_id = PRO_OWNER_ID

        if not message:

            print(
                "[CHAT] ERROR: empty message"
            )

            return jsonify({
                "error": "اكتب رسالة أولاً"
            }), 400


        print(
            "[CHAT] user_id:",
            user_id
        )

        print(
            "[CHAT] message:",
            message[:100]
        )


        # -------------------------------------------------
        # Database - user + message
        # -------------------------------------------------

        print("[DB] Connecting...")

        conn = get_db()

        print("[DB] Connected")

        try:

            cur = conn.cursor(
                cursor_factory=RealDictCursor
            )

            cur.execute(
                """
                INSERT INTO pro_users (user_id)
                VALUES (%s)

                ON CONFLICT (user_id)
                DO NOTHING
                """,
                (user_id,)
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

            print(
                "[DB] User message saved"
            )


            # -------------------------------------------------
            # Conversation history
            # -------------------------------------------------

            cur.execute(
                """
                SELECT
                    role,
                    message
                FROM pro_messages
                WHERE user_id = %s
                ORDER BY id DESC
                LIMIT 20
                """,
                (user_id,)
            )

            rows = list(
                reversed(
                    cur.fetchall()
                )
            )

        finally:

            conn.close()


        print(
            "[DB] Conversation loaded:",
            len(rows),
            "messages"
        )


        # -------------------------------------------------
        # Memories
        # -------------------------------------------------

        print("[MEMORY] Loading...")

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

        conversation = ""

        for item in rows:

            if item["role"] == "user":

                speaker = "محمود"

            else:

                speaker = "PRO AI Agent"

            conversation += (
                speaker
                + ": "
                + item["message"]
                + "\n"
            )


        prompt = (
            SYSTEM_PROMPT
            + "\n\n===== الذاكرة =====\n"
            + memory_text
            + "\n\n===== المحادثة =====\n"
            + conversation
            + "\n\nأجب على آخر رسالة."
        )


        # -------------------------------------------------
        # Gemini
        # -------------------------------------------------

        print(
            "[GEMINI] Calling Gemini..."
        )

        gemini_start = time.time()


        interaction = client.interactions.create(
            model="gemini-3.6-flash",
            input=prompt,
            timeout=30
        )


        gemini_time = (
            time.time()
            - gemini_start
        )


        print(
            "[GEMINI] Response received in",
            round(gemini_time, 2),
            "seconds"
        )


        raw_output = interaction.output_text


        if not raw_output:

            raise RuntimeError(
                "Gemini رجع استجابة بدون نص"
            )


        print(
            "[GEMINI] Output length:",
            len(raw_output)
        )


        # -------------------------------------------------
        # Parse AI response
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
            len(
                result.get(
                    "memories",
                    []
                )
            )
        )

        print(
            "[MEMORY DEBUG] forget count:",
            len(
                result.get(
                    "forget",
                    []
                )
            )
        )

        reply = result["reply"]

        if not reply:

            reply = "تمام يا محمود."


        # -------------------------------------------------
        # Save memories
        # -------------------------------------------------

        print(
            "[MEMORY] Processing new memories..."
        )


        for memory in result["memories"]:

            if not isinstance(
                memory,
                dict
            ):
                continue


            category = str(
                memory.get(
                    "category",
                    ""
                )
            ).strip().lower()


            memory_key = str(
                memory.get(
                    "memory_key",
                    ""
                )
            ).strip()


            memory_value = str(
                memory.get(
                    "memory_value",
                    ""
                )
            ).strip()


            importance = memory.get(
                "importance",
                5
            )


            if category not in ALLOWED_CATEGORIES:
                continue


            if not memory_key or not memory_value:
                continue


            print(
                "[MEMORY] Saving:",
                category,
                memory_key
            )


            save_memory(
                user_id,
                category,
                memory_key,
                memory_value,
                importance
            )


        print(
            "[MEMORY] New memories processed"
        )


        # -------------------------------------------------
        # Forget memories
        # -------------------------------------------------

        for memory in result["forget"]:

            if not isinstance(
                memory,
                dict
            ):
                continue


            category = str(
                memory.get(
                    "category",
                    ""
                )
            ).strip().lower()


            memory_key = str(
                memory.get(
                    "memory_key",
                    ""
                )
            ).strip()


            if category not in ALLOWED_CATEGORIES:
                continue


            if not memory_key:
                continue


            print(
                "[MEMORY] Forget:",
                category,
                memory_key
            )


            delete_memory(
                user_id,
                category,
                memory_key
            )


        # -------------------------------------------------
        # Save assistant reply
        # -------------------------------------------------

        print(
            "[DB] Saving assistant reply..."
        )


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

        finally:

            conn.close()


        # -------------------------------------------------
        # Guarantee name memory
        # -------------------------------------------------

        save_memory(
            user_id,
            "personal",
            "name",
            "محمود",
            10
        )


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


        print("")

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


