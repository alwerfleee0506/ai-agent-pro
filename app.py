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

SYSTEM_PROMPT = """
أنتSYSTEM_PROMPT = """
أنت PRO AI Agent، وكيل ذكاء اصطناعي شخصي لمحمود.

هويتك:
- اسمك: PRO AI Agent.
- المستخدم الأساسي الذي تتعامل معه هو محمود.
- أنت وكيل شخصي طويل المدى، وليس مجرد روبوت محادثة.
- هدفك مساعدة محمود وفهم سياق كلامه والاستفادة من المعلومات المحفوظة في الذاكرة.

أسلوبك:
- تحدث مع محمود باللهجة الليبية بشكل طبيعي.
- كن ودوداً وقريباً منه، لكن بدون مبالغة.
- كن واضحاً ومباشراً.
- لا تستخدم اللهجة المصرية.
- لا تكرر اسم محمود في كل جملة.
- إذا كان السؤال بسيطاً، أجب باختصار.
- إذا كان الموضوع يحتاج شرحاً، اشرح خطوة بخطوة.
- لا تخترع معلومات عن محمود.
- إذا كنت لا تعرف شيئاً، قل بوضوح إنك لا تعرفه.

الذاكرة:
لديك ذاكرة دائمة يتم تخزينها في قاعدة بيانات.

يمكنك استخدام المعلومات الموجودة في قسم الذاكرة لفهم محمود ومساعدته.

احفظ فقط المعلومات طويلة المدى والمفيدة مستقبلاً، مثل:
- الاسم والمعلومات الشخصية العامة.
- التفضيلات المستمرة.
- المشاريع التي يعمل عليها محمود.
- أهدافه أو إعداداته المهمة.
- أي معلومة يطلب منك صراحة الاحتفاظ بها.

لا تحفظ تلقائياً:
- الأسئلة العابرة.
- المعلومات المؤقتة.
- كلمات المرور.
- مفاتيح API.
- أرقام البطاقات والحسابات.
- الموقع الدقيق.
- المعلومات الصحية الحساسة.

إذا قال محمود:
"احفظ..."
أو
"تذكر..."
أو طلب منك صراحة الاحتفاظ بمعلومة:
قم بإضافتها إلى memories.

إذا قال محمود:
"انسَ..."
أو
"احذف من ذاكرتك..."
أو طلب منك نسيان معلومة:
ضع المعلومة المناسبة في forget.

إذا تغيرت معلومة محفوظة:
استخدم نفس memory_key مع القيمة الجديدة حتى يتم تحديثها.

مهم جداً:
- لا تقل إنك حفظت أو حذفت معلومة إلا إذا أرسلتها فعلاً في memories أو forget.
- لا تدّعي أنك نفذت شيئاً خارج نظام الذاكرة إذا لم يتم تنفيذه.
- لا تخترع ذاكرة غير موجودة في قسم الذاكرة.
- إذا لم توجد المعلومة في الذاكرة، قل إنك لا تملكها.
- إذا تم نسيان معلومة، لا تستخدمها مرة أخرى باعتبارها ذاكرة محفوظة.

المشاريع:
إذا تحدث محمود عن مشروع أو نظام يعمل عليه، تعامل معه كسياق مهم وطويل المدى عندما يكون مناسباً.
مشروعه الحالي هو PRO AI Agent، وهو الوكيل الذي تعمل بداخله الآن.

التعامل مع المحادثة:
- اقرأ الذاكرة أولاً.
- اقرأ سياق المحادثة.
- افهم آخر رسالة لمحمود.
- أجب على آخر رسالة مباشرة.
- لا تشرح لمحمود تفاصيل النظام الداخلي أو JSON إلا إذا طلب ذلك.

الفئات المسموحة للذاكرة:
personal
preferences
projects
important

قواعد JSON:
يجب أن يكون ردك JSON فقط، بدون Markdown وبدون ```json.

استخدم الشكل التالي:

{
  "reply": "الرد لمحمود",
  "memories": [
    {
      "category": "preferences",
      "memory_key": "مثال",
      "memory_value": "مثال",
      "importance": 8
    }
  ],
  "forget": []
}

إذا لا توجد ذاكرة جديدة:
"memories": []

إذا لا توجد معلومة للنسيان:
"forget": []

إذا كان هناك شيء يجب نسيانه:
ضعه في forget بالشكل:

{
  "category": "preferences",
  "memory_key": "مثال"
}

لا تخترع معلومات شخصية عن محمود.
"""


ALLOWED_CATEGORIES = {
    "personal",
    "preferences",
    "projects",
    "important"
}


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

    finally:
        conn.close()


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

    reply = data.get("reply", "")

    if not isinstance(reply, str):
        reply = str(reply)

    memories = data.get("memories", [])
    forget = data.get("forget", [])

    if not isinstance(memories, list):
        memories = []

    if not isinstance(forget, list):
        forget = []

    return {
        "reply": reply.strip(),
        "memories": memories,
        "forget": forget
    }


HTML = r"""
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

form.addEventListener(
    "submit",
    async function(e) {

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

        const loading =
            document.createElement("div");

        loading.className = "message ai";
        loading.textContent = "جاري التفكير...";

        chat.appendChild(loading);

        try {

            const response =
                await fetch("/chat", {

                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body: JSON.stringify({
                        message: message,
                        user_id: userId
                    })

                });

            const data =
                await response.json();

            loading.textContent =
                data.reply ||
                data.error ||
                "صار خطأ.";

        } catch (error) {

            loading.textContent =
                "تعذر الاتصال بالوكيل.";

        }

        chat.scrollTop =
            chat.scrollHeight;

    }
);

</script>

</body>

</html>
"""


@app.route("/")
def home():

    return render_template_string(HTML)


@app.route(
    "/chat",
    methods=["POST"]
)
def chat():

    data = request.get_json(
        silent=True
    ) or {}

    message = data.get(
        "message",
        ""
    ).strip()

    user_id = data.get(
        "user_id",
        ""
    ).strip()

    if not user_id:

        user_id = str(
            uuid.uuid4()
        )

    if not message:

        return jsonify({
            "error": "اكتب رسالة أولاً"
        }), 400

    try:

        init_db()

        conn = get_db()

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

        conn.close()

        memories = get_memories(
            user_id
        )

        memory_text = format_memories(
            memories
        )

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

        interaction = client.interactions.create(
            model="gemini-3.6-flash",
            input=prompt
        )

        raw_output = interaction.output_text

        result = parse_ai_response(
            raw_output
        )

        reply = result["reply"]

        if not reply:
            reply = "تمام يا محمود."

        # حفظ الذكريات الجديدة
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

            save_memory(
                user_id,
                category,
                memory_key,
                memory_value,
                importance
            )

        # نسيان الذكريات
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

            delete_memory(
                user_id,
                category,
                memory_key
            )

        # حفظ رد PRO
        conn = get_db()

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

        conn.close()

        # ضمان حفظ اسم محمود
        save_memory(
            user_id,
            "personal",
            "name",
            "محمود",
            10
        )

        return jsonify({
            "reply": reply,
            "user_id": user_id
        })

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                10000
            )
        )
    )
