from flask import Flask, request, jsonify, render_template_string
from google import genai
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

client = genai.Client(
    api_key=GEMINI_API_KEY
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

    يتم:
    1. إنشاء المستخدم الموحد.
    2. نقل الذكريات القديمة.
    3. نقل المحادثات القديمة.
    4. حذف المستخدمين القدامى.

    العملية كلها داخل Transaction واحدة.
    """

    print("[MIGRATION] Checking old user IDs...")

    conn = get_db()

    try:
        cur = conn.cursor(
            cursor_factory=RealDictCursor
        )

        # -------------------------------------------------
        # تأكد من وجود المستخدم الموحد
        # -------------------------------------------------

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

        # -------------------------------------------------
        # الحصول على المستخدمين القدامى
        # -------------------------------------------------

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
        # نقل الذكريات
        # -------------------------------------------------
        #
        # نرتب حسب updated_at DESC
        # حتى أحدث قيمة لنفس memory_key
        # يتم اعتمادها أولاً.
        #
        # ON CONFLICT DO NOTHING
        # يمنع استبدال القيمة الأحدث بقيمة أقدم.
        # -------------------------------------------------

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

        # -------------------------------------------------
        # نقل المحادثات
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
        # حذف المستخدمين القدامى
        #
        # ON DELETE CASCADE
        # يحذف أي بيانات قديمة بقيت.
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

    # -----------------------------------------------------
    # بعد إنشاء الجداول:
    # وحد كل بيانات الاختبارات القديمة
    # -----------------------------------------------------

    migrate
