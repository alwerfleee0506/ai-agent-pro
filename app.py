from flask import Flask, request, jsonify, render_template_string
from openai import OpenAI
import os

app = Flask(__name__)

client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY")
)

HTML = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
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
    cursor: pointer;
}
</style>
</head>

<body>
<div class="container">
<h1>🤖 PRO AI Agent</h1>

<div id="chat">
<div class="message ai">السلام عليكم 👋 أنا PRO AI Agent. شن نقدر نساعدك فيه؟</div>
</div>

<form id="form">
<input id="message" placeholder="اكتب رسالتك..." autocomplete="off">
<button type="submit">إرسال</button>
</form>
</div>

<script>
const form = document.getElementById("form");
const input = document.getElementById("message");
const chat = document.getElementById("chat");

form.addEventListener("submit", async (e) => {
    e.preventDefault();

    const message = input.value.trim();
    if (!message) return;

    chat.innerHTML += `<div class="message user">${message}</div>`;
    input.value = "";

    const loading = document.createElement("div");
    loading.className = "message ai";
    loading.textContent = "جاري التفكير...";
    chat.appendChild(loading);
    chat.scrollTop = chat.scrollHeight;

    try {
        const response = await fetch("/chat", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                message: message
            })
        });

        const data = await response.json();

        loading.textContent = data.reply || data.error || "صار خطأ.";

    } catch (error) {
        loading.textContent = "تعذر الاتصال بالوكيل.";
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

    if not message:
        return jsonify({"error": "اكتب رسالة أولاً"}), 400

    try:
        response = client.responses.create(
            model="gpt-5-mini",
            input=[
                {
                    "role": "system",
                    "content": "أنت PRO AI Agent، مساعد ذكي مفيد وواضح."
                },
                {
                    "role": "user",
                    "content": message
                }
            ]
        )

        return jsonify({
            "reply": response.output_text
        })

    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )
