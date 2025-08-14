import logging
import sqlite3
import asyncio
import os # এই নতুন লাইনটি যোগ করা হয়েছে
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# --- কনফিগারেশন (এখন থেকে এই তথ্যগুলো Render থেকে আসবে) ---
BOT_TOKEN = os.environ.get('BOT_TOKEN')
MAIN_CHANNEL = os.environ.get('MAIN_CHANNEL')
PAYMENT_CHANNEL = os.environ.get('PAYMENT_CHANNEL')
ADMIN_CHAT_ID = os.environ.get('ADMIN_CHAT_ID')

# --- অপরিবর্তিত ভ্যারিয়েবল ---
CHANNELS_TO_JOIN = [MAIN_CHANNEL, PAYMENT_CHANNEL]
REFERRAL_BONUS = 1.0
MIN_WITHDRAWAL = 10.0

# --- লগিং সেটআপ ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- ডাটাবেস ফাংশন ---
DB_PATH = '/data/airdrop_data.db' 

def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        balance REAL DEFAULT 0.0,
        wallet TEXT,
        referrer_id INTEGER
    )
    ''')
    conn.commit()
    conn.close()

# ... (বাকি কোডের কোনো পরিবর্তন হবে না, যা আগে ছিল তেমনই থাকবে) ...
# The rest of the functions (get_user, add_user, start, button_handler, etc.) remain exactly the same as the last version I provided.
# I will omit them here for brevity, but the user should use the full script with just the configuration part changed as shown above.
# For the purpose of providing a complete answer, I will include the full code below.
def get_user(user_id):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def add_user(user_id, referrer_id=None):
    if not get_user(user_id):
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO users (user_id, referrer_id) VALUES (?, ?)', (user_id, referrer_id))
        conn.commit()
        conn.close()
        if referrer_id and get_user(referrer_id):
            update_balance(referrer_id, REFERRAL_BONUS)
            logger.info(f"User {referrer_id} received {REFERRAL_BONUS} USDT for referring {user_id}")

def update_balance(user_id, amount):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
    conn.commit()
    conn.close()

def set_wallet(user_id, wallet):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET wallet = ? WHERE user_id = ?', (wallet, user_id))
    conn.commit()
    conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id
    referrer_id = None
    if context.args and len(context.args) > 0:
        try:
            ref_id = int(context.args[0])
            if ref_id != user_id: referrer_id = ref_id
        except (ValueError, IndexError): pass
    add_user(user_id, referrer_id)
    welcome_text = f"👋 <b>Hi {user.first_name}! Welcome to the Airdrop Bot.</b>"
    task_keyboard = [[InlineKeyboardButton(f"🚀 Join Airdrop Channel", url=f"https://t.me/{MAIN_CHANNEL.lstrip('@')}")],[InlineKeyboardButton(f"📢 Join Payment Channel", url=f"https://t.me/{PAYMENT_CHANNEL.lstrip('@')}")],[InlineKeyboardButton("✅ Done, Check My Tasks", callback_data='check_join')]]
    task_markup = InlineKeyboardMarkup(task_keyboard)
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.HTML)
    await update.message.reply_text('👇 <b>Please join our channels to be eligible for the airdrop.</b>\n\nAfter joining, click the "Done" button below.',reply_markup=task_markup, parse_mode=ParseMode.HTML)

async def check_membership(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    for channel in CHANNELS_TO_JOIN:
        try:
            member = await context.bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status not in ['member', 'administrator', 'creator']: return False
        except Exception as e:
            logger.error(f"Error checking membership for {channel}: {e}")
            await context.bot.send_message(chat_id=user_id, text=f"<b>Error:</b> Could not check channel <code>{channel}</code>.\nPlease make sure the bot is an admin in this channel and the username is correct.", parse_mode=ParseMode.HTML)
            return False
    return True

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if query.data == 'check_join':
        if await check_membership(user_id, context):
            text = "🎉 <b>Congratulations! You have completed all tasks.</b>\n\nWelcome to our community! You can now use the menu below."
            await query.edit_message_text(text=text, parse_mode=ParseMode.HTML, reply_markup=main_menu_keyboard())
        else:
            await query.message.reply_text("❌ <b>You haven't joined all channels yet.</b>\nPlease join them and try again.", parse_mode=ParseMode.HTML)
    elif query.data == 'my_balance':
        user_data = get_user(user_id)
        balance = user_data[1] if user_data else 0.0
        wallet = f"<code>{user_data[2]}</code>" if user_data and user_data[2] else "Not Set"
        text = f"💰 <b>Your Balance Details</b> 💰\n\n🆔 <b>Account ID:</b> <code>{user_id}</code>\n💸 <b>Balance:</b> {balance:.2f} USDT\n💼 <b>Your Wallet:</b> {wallet}"
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=main_menu_keyboard())
    elif query.data == 'set_wallet':
        context.user_data['awaiting_wallet'] = True
        await query.edit_message_text("✏️ Please send your <b>BEP-20 (BSC)</b> wallet address.\n\nExample: `0x123...abc`", parse_mode=ParseMode.HTML)
    elif query.data == 'withdraw':
        user_data = get_user(user_id)
        balance = user_data[1] if user_data else 0.0
        wallet = user_data[2] if user_data and user_data[2] else None
        if not wallet:
            await query.message.reply_text("⚠️ You need to set your wallet address first. Use the '⚙️ Set Wallet' button.", reply_markup=main_menu_keyboard())
        elif balance < MIN_WITHDRAWAL:
            await query.message.reply_text(f"❌ <b>Insufficient balance!</b>\nYou need at least {MIN_WITHDRAWAL} USDT to withdraw.", parse_mode=ParseMode.HTML, reply_markup=main_menu_keyboard())
        else:
            try:
                admin_text = f"🏧 New Withdrawal Request:\n\nUser ID: `{user_id}`\nAmount: `{balance}` USDT\nWallet: `{wallet}`"
                await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_text, parse_mode=ParseMode.MARKDOWN)
                await query.edit_message_text("✅ Your withdrawal request has been submitted. It will be processed within 24 hours.", reply_markup=main_menu_keyboard())
            except Exception as e:
                logger.error(f"Failed to send withdrawal notification to admin: {e}")
                await query.edit_message_text("❌ Could not process your request at this time. Please try again later.", reply_markup=main_menu_keyboard())
    elif query.data == 'referral':
        bot_username = (await context.bot.get_me()).username
        referral_link = f"https://t.me/{bot_username}?start={user_id}"
        text = f"👥 <b>Referral Program</b> 👥\n\nInvite your friends and earn <b>{REFERRAL_BONUS} USDT</b> for each valid referral!\n\nYour unique referral link is:\n👇👇👇\n`{referral_link}`\n\nShare this link and earn more!"
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu_keyboard())

def main_menu_keyboard():
    keyboard = [[InlineKeyboardButton("💰 My Balance", callback_data='my_balance'), InlineKeyboardButton("👥 Referral", callback_data='referral')],[InlineKeyboardButton("⚙️ Set Wallet", callback_data='set_wallet'), InlineKeyboardButton("🏧 Withdraw", callback_data='withdraw')]]
    return InlineKeyboardMarkup(keyboard)

async def wallet_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if context.user_data.get('awaiting_wallet'):
        wallet_address = update.message.text
        if len(wallet_address) == 42 and wallet_address.startswith('0x'):
            set_wallet(user_id, wallet_address)
            await update.message.reply_text(f"✅ Your wallet has been successfully set to:\n<code>{wallet_address}</code>", parse_mode=ParseMode.HTML)
            context.user_data['awaiting_wallet'] = False
            await update.message.reply_text("You can now check your balance or request a withdrawal.", reply_markup=main_menu_keyboard())
        else:
            await update.message.reply_text("❌ Invalid wallet address. Please send a valid <b>BEP-20 (BSC)</b> address starting with `0x`.", parse_mode=ParseMode.HTML)

def main() -> None:
    init_db()
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, wallet_handler))
    logger.info("Bot is running... Press Ctrl+C to stop.")
    application.run_polling()

if __name__ == '__main__':
    main()