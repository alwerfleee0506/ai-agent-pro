from flask import Flask, request, jsonify, render_template_string
from google import genai
import os
import uuid
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)

client = genai.Client(
    api_key=os.environ.get("GEMINI_API_KEY")
)

DATABASE_URL = os.environ.get("DATABASE_URL")

SYSTEM_PROMPT = """
أنت PRO AI Agent، مساعد ذكي شخصي للمستخدم محمود.
تحدث مع محمود باللهجة الليبية بشكل طبيعي.
كن ودوداً وواضحاً ومباشراً.
تذكر سياق المحادثة الحالية.
لا تخترع معلومات شخصية عن محمود.
إذا لم تعرف معلومة شخصية عنه، قل إنك لا تعرفها.
"""


def get_db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL غير موجود في إعدادات Render")

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
            CREATE INDEX IF NOT EXISTS idx_pro_messages_user_id_id
            ON pro_messages(user_id, id DESC)
        """)

        conn.commit()

    finally:
        conn.close()


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
                message: message,
                user_id: userId
            })

        });

        const data = await response.json();

        loading.textContent =
            data.reply ||
            data.error ||
            "صار خطأ.";

    } catch (error) {

        loading.textContent =
            "تعذر الاتصال بالوكيل.";

    }

    chat.scrollTop = chat.scrollHeight;

});

</script>

</body>

</html>
"""


@app.route("/")
def home():

    return render_template_string(HTML)


@app.route("/chat", methods=["POST"])
def chat():

    data = request.get_json(silent=True) or {}

    message = data.get("message", "").strip()

    user_id = data.get("user_id", "").strip()

    if not user_id:
        user_id = str(uuid.uuid4())

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
            ON CONFLICT (user_id) DO NOTHING
            """,
            (user_id,)
        )

        cur.execute(
            """
            INSERT INTO pro_messages
            (user_id, role, message)
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
            SELECT role, message
            FROM pro_messages
            WHERE user_id = %s
            ORDER BY id DESC
            LIMIT 20
            """,
            (user_id,)
        )

        rows = list(
            reversed(cur.fetchall())
        )

        conn.close()

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
            + "\n\nاسم المستخدم: محمود"
            + "\n\nالمحادثة السابقة:\n"
            + conversation
            + "\n\nأجب على آخر رسالة مباشرة باللهجة الليبية."
        )

        interaction = client.interactions.create(
            model="gemini-3.6-flash",
            input=prompt
        )

        reply = interaction.output_text

        conn = get_db()

        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO pro_messages
            (user_id, role, message)
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
