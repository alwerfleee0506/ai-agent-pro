from flask import Flask, request, jsonify
from openai import OpenAI
import os

app = Flask(__name__)

client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY")
)

@app.route("/")
def home():
    return jsonify({
        "status": "online",
        "agent": "PRO AI Agent",
        "message": "الوكيل الذكي شغال 🚀"
    })

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()

    if not message:
        return jsonify({
            "error": "اكتب رسالة أولاً"
        }), 400

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
