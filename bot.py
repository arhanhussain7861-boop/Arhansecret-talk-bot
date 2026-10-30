import os
import logging
from collections import deque
from telegram import Update
from telegram.ext import (
    Application, CommandHandler,
    MessageHandler, ContextTypes, filters
)

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_CHAT_ID")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

waiting = deque()
partners = {}
blocked = set()
pending_inbox = {}
last_sender = {}

def pair_key(a, b):
    return tuple(sorted((a, b)))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    if context.args and context.args[0].startswith("inbox_"):
        try:
            target = int(context.args[0][6:])
            if target == uid:
                await update.message.reply_text("You cannot message yourself.")
                return
            pending_inbox[uid] = target
            await update.message.reply_text(
                "Send your anonymous message as your next text message."
            )
            return
        except ValueError:
            pass

    await update.message.reply_text(
        "Welcome to SecretTalk!\n\n"
        "/link - Get your anonymous inbox link\n"
        "/reply TEXT - Reply anonymously\n"
        "/random - Find a random chat partner\n"
        "/next - Find another partner\n"
        "/stop - End random chat\n"
        "/block - Block current partner\n"
        "/report - Report current partner\n"
        "/help - Show commands\n\n"
        "Stay safe: never share personal information."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def link_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    me = await context.bot.get_me()
    uid = update.effective_user.id
    link = f"https://t.me/{me.username}?start=inbox_{uid}"
    await update.message.reply_text(
        "Share this link to receive anonymous messages:\n" + link
    )

async def random_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    if uid in partners:
        await update.message.reply_text("You are already chatting. Use /stop first.")
        return

    if uid in waiting:
        await update.message.reply_text("You are already waiting for a partner.")
        return

    while waiting:
        other = waiting.popleft()
        if other == uid or other in partners:
            continue
        if pair_key(uid, other) in blocked:
            continue

        partners[uid] = other
        partners[other] = uid

        await context.bot.send_message(uid, "You are connected! Say hello.")
        await context.bot.send_message(other, "You are connected! Say hello.")
        return

    waiting.append(uid)
    await update.message.reply_text(
        "You are in the waiting queue. Use /stop to cancel."
    )

async def stop_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    other = partners.pop(uid, None)

    if other is not None:
        partners.pop(other, None)
        await context.bot.send_message(other, "Your partner left the chat.")
        await update.message.reply_text("Chat ended.")
    else:
        try:
            waiting.remove(uid)
        except ValueError:
            pass
        await update.message.reply_text("You are no longer waiting or chatting.")

async def next_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await stop_chat(update, context)
    await random_command(update, context)

async def block_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    other = partners.get(uid)
    if other is None:
        await update.message.reply_text("No active random chat partner.")
        return
    blocked.add(pair_key(uid, other))
    await stop_chat(update, context)
    await update.message.reply_text("Partner blocked for this bot session.")

async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    other = partners.get(uid) or last_sender.get(uid)

    if other is None:
        await update.message.reply_text("No recent sender or active partner to report.")
        return

    if ADMIN_ID:
        try:
            await context.bot.send_message(
                int(ADMIN_ID),
                f"SecretTalk report\nReporter ID: {uid}\nReported user ID: {other}"
            )
        except Exception:
            log.exception("Could not send report")

    await update.message.reply_text("Report submitted. Thank you.")
    if uid in partners:
        await stop_chat(update, context)

async def reply_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    other = last_sender.get(uid)
    message = " ".join(context.args)

    if not other or not message:
        await update.message.reply_text("Usage: /reply your message")
        return

    try:
        await context.bot.send_message(other, "Anonymous reply:\n" + message)
        await update.message.reply_text("Reply sent.")
    except Exception:
        await update.message.reply_text("Could not deliver your reply.")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    message = update.message.text

    if uid in pending_inbox:
        target = pending_inbox.pop(uid)
        try:
            await context.bot.send_message(
                target, "New anonymous inbox message:\n" + message
            )
            last_sender[target] = uid
            await update.message.reply_text("Your anonymous message was sent.")
        except Exception:
            await update.message.reply_text("Message could not be delivered.")
        return

    other = partners.get(uid)
    if other is None:
        await update.message.reply_text(
            "No active chat. Use /random or /link."
        )
        return

    if pair_key(uid, other) in blocked:
        await stop_chat(update, context)
        return

    try:
        await context.bot.send_message(other, message)
    except Exception:
        await stop_chat(update, context)
        await update.message.reply_text("Your partner is unavailable.")

def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is missing")

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("link", link_command))
    app.add_handler(CommandHandler("random", random_command))
    app.add_handler(CommandHandler("stop", stop_chat))
    app.add_handler(CommandHandler("next", next_chat))
    app.add_handler(CommandHandler("block", block_command))
    app.add_handler(CommandHandler("report", report_command))
    app.add_handler(CommandHandler("reply", reply_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    log.info("SecretTalk is starting")
    app.run_polling()

if __name__ == "__main__":
    main()
  
