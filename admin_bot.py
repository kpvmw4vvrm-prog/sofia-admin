import logging
import os
import psycopg2
import psycopg2.extras
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN")
SOFIA_TOKEN = os.environ.get("SOFIA_TOKEN")
ADMIN_ID = 944447597
DATABASE_URL = os.environ.get("DATABASE_URL")

logging.basicConfig(level=logging.INFO)
db_conn = None

def init_db():
    global db_conn
    db_conn = psycopg2.connect(DATABASE_URL)
    db_conn.autocommit = True

def db_fetchval(query, *args):
    with db_conn.cursor() as cur:
        cur.execute(query, args)
        row = cur.fetchone()
        return row[0] if row else None

def db_fetch(query, *args):
    with db_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(query, args)
        return cur.fetchall()

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("Нет доступа.")
        return

    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("👥 Пользователи", callback_data="users")],
        [InlineKeyboardButton("📢 Рассылка", callback_data="announce")],
        [InlineKeyboardButton("💬 Последние сообщения", callback_data="messages")],
    ]
    await update.message.reply_text(
        "🌸 *Панель управления Софией*\n\nВыберите раздел:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        return

    if query.data == "stats":
        total = db_fetchval("SELECT COUNT(*) FROM users WHERE onboarded = TRUE")
        today = db_fetchval("SELECT COUNT(DISTINCT user_id) FROM history WHERE created_at >= NOW() - INTERVAL '1 day'")
        week = db_fetchval("SELECT COUNT(DISTINCT user_id) FROM history WHERE created_at >= NOW() - INTERVAL '7 days'")
        total_messages = db_fetchval("SELECT COUNT(*) FROM history WHERE role = 'user'")

        text = (
            "📊 *Статистика Софии*\n\n"
            f"👥 Всего пользователей: *{total}*\n"
            f"🟢 Активных сегодня: *{today}*\n"
            f"📅 Активных за 7 дней: *{week}*\n"
            f"💬 Всего сообщений: *{total_messages}*"
        )
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif query.data == "users":
        users = db_fetch("SELECT name, username, onboarded FROM users ORDER BY name LIMIT 20")
        if users:
            lines = []
            for u in users:
                name = u["name"] or "—"
                username = f"@{u['username']}" if u["username"] and u["username"] != "нет username" else "—"
                status = "✅" if u["onboarded"] else "⏳"
                lines.append(f"{status} {name} {username}")
            text = "👥 *Пользователи:*\n\n" + "\n".join(lines)
        else:
            text = "👥 Пользователей пока нет."
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif query.data == "messages":
        messages = db_fetch(
            """SELECT u.name, h.content, h.created_at 
            FROM history h 
            JOIN users u ON h.user_id = u.user_id 
            WHERE h.role = 'user' 
            ORDER BY h.created_at DESC LIMIT 10"""
        )
        if messages:
            lines = []
            for m in messages:
                name = m["name"] or "—"
                content = m["content"][:50] + "..." if len(m["content"]) > 50 else m["content"]
                lines.append(f"👤 *{name}*: {content}")
            text = "💬 *Последние сообщения:*\n\n" + "\n\n".join(lines)
        else:
            text = "💬 Сообщений пока нет."
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif query.data == "announce":
        context.user_data["waiting_announce"] = True
        keyboard = [[InlineKeyboardButton("◀️ Отмена", callback_data="back")]]
        await query.edit_message_text(
            "📢 *Рассылка*\n\nНапишите текст сообщения — я разошлю всем пользователям:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    elif query.data == "back":
        keyboard = [
            [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
            [InlineKeyboardButton("👥 Пользователи", callback_data="users")],
            [InlineKeyboardButton("📢 Рассылка", callback_data="announce")],
            [InlineKeyboardButton("💬 Последние сообщения", callback_data="messages")],
        ]
        await query.edit_message_text(
            "🌸 *Панель управления Софией*\n\nВыберите раздел:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

async def handle_announce(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    if context.user_data.get("waiting_announce"):
        text = update.message.text
        context.user_data["waiting_announce"] = False

        users = db_fetch("SELECT user_id FROM users WHERE onboarded = TRUE")

        sent = 0
        failed = 0
        sofia_app = ApplicationBuilder().token(SOFIA_TOKEN).build()
        async with sofia_app:
            for u in users:
                try:
                    await sofia_app.bot.send_message(chat_id=u["user_id"], text=f"📢 {text}")
                    sent += 1
                except:
                    failed += 1

        await update.message.reply_text(
            f"✅ Рассылка завершена!\n\nОтправлено: {sent}\nНе доставлено: {failed}"
        )

        keyboard = [
            [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
            [InlineKeyboardButton("👥 Пользователи", callback_data="users")],
            [InlineKeyboardButton("📢 Рассылка", callback_data="announce")],
            [InlineKeyboardButton("💬 Последние сообщения", callback_data="messages")],
        ]
        await update.message.reply_text(
            "🌸 *Панель управления Софией*\n\nВыберите раздел:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

async def post_init(application):
    init_db()

if __name__ == "__main__":
    app = ApplicationBuilder().token(ADMIN_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", main_menu))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_announce))
    print("🌸 Admin панель запущена!")
    app.run_polling()
