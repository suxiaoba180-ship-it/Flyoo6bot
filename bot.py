import os
import re
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)


# ==================================================
# Bot Token
# ==================================================
BOT_TOKEN = os.environ["BOT_TOKEN"]


# ==================================================
# 管理员 Telegram ID
# ==================================================
ADMIN_ID = 7995750937

# ==================================================
# 客服群 ID
# ==================================================
SUPPORT_GROUP_ID = -1004349164935
CUSTOMER_TOPICS = {}
TOPIC_CUSTOMERS = {}

# ==================================================
# 定时群发广告配置
# ==================================================
ACTIVE_GROUPS = set()
AD_CONTENT = (
    "🌟 【热门推荐公告】 🌟\n\n"
    "欢迎来到我们的官方频道！\n"
    "🔥 注册平台、新人彩金、签到与日存彩金火热进行中！\n\n"
    "请点击下方机器人菜单了解详情👇"
)

# ==================================================
# 文件所在目录
# ==================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 如果你需要海报图片，可以放一张叫做 poster.png 在同级目录下，如果没有会纯发文字
POSTER_IMAGE = os.path.join(BASE_DIR, "poster.png")

ALIPAY_QR = os.path.join(BASE_DIR, "alipay.png")
WECHAT_QR = os.path.join(BASE_DIR, "wechat.png")
USDT_QR = os.path.join(BASE_DIR, "usdt.png")
USDT_ADDRESS = "TAm7hZ3sXDctxFfera4xiTnWffAxRgeFQg"
USDT_AMOUNT = "10 USDT"
USDT_NETWORK = "TRC20"

# ============================================================
# Telegram 左下角菜单 / 键盘布局
# ============================================================

async def setup_bot_commands(application):
    await application.bot.set_my_commands([
        BotCommand("start", "🏠 开始使用"),
        BotCommand("register", "📝 注册平台"),
        BotCommand("newbie", "🎁 新人彩金"),
        BotCommand("checkin", "📅 签到彩金"),
        BotCommand("deposit", "💰 日存彩金"),
        BotCommand("invite", "👥 推荐好礼"),
        BotCommand("explore", "🗺 探索秘境"),
        BotCommand("support", "📞 联系客服"),
    ])

# 底部固定键盘（按你要求的顺序：注册平台、新人彩金、签到彩金、日存彩金、推荐好礼、探索秘境 + 客服）
MAIN_REPLY_KEYBOARD = [
    ["📝 注册平台", "🎁 新人彩金"],
    ["📅 签到彩金", "💰 日存彩金"],
    ["👥 推荐好礼", "🗺 探索秘境"],
    ["📞 联系客服"],
]

MAIN_REPLY_MARKUP = ReplyKeyboardMarkup(
    MAIN_REPLY_KEYBOARD,
    resize_keyboard=True,
    is_persistent=True,
)

# 聊天界面内嵌网格按钮（类似你提供的截图排版风格）
def get_inline_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📝 注册平台", callback_data="register"),
            InlineKeyboardButton("🎁 新人彩金", callback_data="newbie")
        ],
        [
            InlineKeyboardButton("📅 签到彩金", callback_data="checkin"),
            InlineKeyboardButton("💰 日存彩金", callback_data="deposit")
        ],
        [
            InlineKeyboardButton("👥 推荐好礼", callback_data="invite"),
            InlineKeyboardButton("🗺 探索秘境", callback_data="explore")
        ],
        [
            InlineKeyboardButton("📞 联系客服", callback_data="support")
        ]
    ])

# ==================================================
# 统一的图文发送助手（支持图片海报 + 文字 + 内嵌按钮）
# ==================================================
async def send_feature_message(update_or_query, text_content):
    # 兼容 callback_query 和 message
    if hasattr(update_or_query, "message") and update_or_query.message:
        target_message = update_or_query.message
    else:
        target_message = update_or_query

    # 如果存在海报文件 poster.png，则以图文海报形式发送
    if os.path.exists(POSTER_IMAGE):
        with open(POSTER_IMAGE, "rb") as photo:
            try:
                await target_message.reply_photo(
                    photo=photo,
                    caption=text_content,
                    reply_markup=get_inline_keyboard()
                )
                return
            except Exception:
                pass
    
    # 如果没有海报或发送失败，则纯文字带内嵌键盘发送
    await target_message.reply_text(
        text=text_content,
        reply_markup=get_inline_keyboard()
    )


# ==================================================
# /start
# ==================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("🔥 START 被调用了！")
    welcome_text = (
        "👋 欢迎来到平台！\n\n"
        "🔥 请点击下方按钮或菜单栏选择您需要体验的服务："
    )
    # 发送带底部键盘、正文带内嵌按钮的消息
    if os.path.exists(POSTER_IMAGE):
        with open(POSTER_IMAGE, "rb") as photo:
            await update.message.reply_photo(
                photo=photo,
                caption=welcome_text,
                reply_markup=get_inline_keyboard()
            )
    else:
        await update.message.reply_text(
            text=welcome_text,
            reply_markup=get_inline_keyboard()
        )
    
    # 顺便展示底部键盘
    await update.message.reply_text(
        "👇 您也可以直接使用下方固定键盘：",
        reply_markup=MAIN_REPLY_MARKUP
    )

# ==================================================
# 获取当前群组 ID
# ==================================================
async def groupid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type in ["group", "supergroup"]:
        ACTIVE_GROUPS.add(chat.id)

    await update.message.reply_text(
        f"📌 当前聊天信息\n\n"
        f"群组名称：{chat.title}\n"
        f"Chat ID：{chat.id}\n"
        f"类型：{chat.type}"
    )

# ==================================================
# /myid
# ==================================================
async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"👤 你的 Telegram 信息\n\n"
        f"姓名：{user.full_name}\n"
        f"用户名：@{user.username if user.username else '未设置'}\n"
        f"Telegram ID：{user.id}"
    )


# ==================================================
# /admin
# ==================================================
async def admin_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ 你没有管理员权限。")
        return

    await update.message.reply_text(
        "👑 管理员权限验证成功！\n\n"
        "你现在是这个机器人的管理员。"
    )


# ==================================================
# 按钮（内联键盘）点击处理
# ==================================================
async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    print("🔥 BUTTON_HANDLER 被调用了！")
    query = update.callback_query
    await query.answer()

    if query.data == "register":
        await send_feature_message(query, "📝 【1. 注册平台】\n\n点击下方链接或访问官网完成账号注册：\nhttps://t.me/your_channel_link")
    elif query.data == "newbie":
        await send_feature_message(query, "🎁 【2. 新人彩金】\n\n新用户首次绑定并完成实名，即可联系客服领取丰厚新人彩金！")
    elif query.data == "checkin":
        await send_feature_message(query, "📅 【3. 签到彩金】\n\n每日打卡签到，连续签到天数越多，签到彩金越丰厚！")
    elif query.data == "deposit":
        await send_feature_message(query, "💰 【4. 日存彩金】\n\n每日充值尊享日存彩金加赠，多充多送，实时到账！")
    elif query.data == "invite":
        await send_feature_message(query, "👥 【5. 推荐好礼】\n\n分享您的专属邀请链接给好友，共同享受丰厚推荐返利与好礼！")
    elif query.data == "explore":
        await send_feature_message(query, "🗺 【6. 探索秘境】\n\n欢迎来到秘境探索频道，点击开启您的奇妙旅程：\nhttps://t.me/your_channel_link")
    elif query.data == "support":
        await send_feature_message(query, "📞 【联系客服】\n\n如有任何疑问，请直接在对话框发送消息，专属客服将为您解答。")


# ============================================================
# 客服系统：客户 → 客服群独立话题
# ============================================================

async def forward_customer_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    message = update.effective_message
    user = update.effective_user

    if not message or not user:
        return

    if update.effective_chat.type in ["group", "supergroup"]:
        ACTIVE_GROUPS.add(update.effective_chat.id)
        return

    if update.effective_chat.type != "private":
        return

    if user.is_bot:
        return

    username = f"@{user.username}" if user.username else "未设置"
    customer_id = user.id

    if customer_id not in CUSTOMER_TOPICS:
        try:
            topic_name = f"👤 {user.full_name}"
            topic = await context.bot.create_forum_topic(
                chat_id=SUPPORT_GROUP_ID,
                name=topic_name
            )

            CUSTOMER_TOPICS[customer_id] = topic.message_thread_id
            TOPIC_CUSTOMERS[topic.message_thread_id] = customer_id
            
            await context.bot.send_message(
                chat_id=SUPPORT_GROUP_ID,
                message_thread_id=topic.message_thread_id,
                text=(
                    "🆕 新客户咨询\n\n"
                    f"👤 姓名：{user.full_name}\n"
                    f"🔹 用户名：{username}\n"
                    f"🆔 Telegram ID：{user.id}\n\n"
                    "💬 客户消息："
                )
            )
        except Exception as e:
            print(f"❌ 创建客户话题失败：{e}")
            return

    topic_id = CUSTOMER_TOPICS[customer_id]

    if message.text:
        text = (
            "👤 客户咨询\n\n"
            f"👤 姓名：{user.full_name}\n"
            f"🔹 用户名：{username}\n"
            f"🆔 Telegram ID：{user.id}\n\n"
            "💬 客户消息：\n"
            f"{message.text}"
        )
        await context.bot.send_message(
            chat_id=SUPPORT_GROUP_ID,
            message_thread_id=topic_id,
            text=text
        )
    elif message.photo:
        await context.bot.send_photo(
            chat_id=SUPPORT_GROUP_ID,
            message_thread_id=topic_id,
            photo=message.photo[-1].file_id,
            caption=f"👤 客户图片\nID: {user.id}"
        )
    else:
        await context.bot.send_message(
            chat_id=SUPPORT_GROUP_ID,
            message_thread_id=topic_id,
            text=f"👤 客户发送了消息 (ID: {user.id})"
        )


# ==================================================
# 客服系统：管理员回复 → 客户
# ==================================================

async def admin_reply_customer(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if not message or not user or not chat:
        return

    if chat.id != SUPPORT_GROUP_ID:
        return

    try:
        member = await context.bot.get_chat_member(
            chat_id=SUPPORT_GROUP_ID,
            user_id=user.id
        )
        if member.status not in ("administrator", "creator"):
            return
    except Exception:
        return

    customer_id = None
    if message.reply_to_message:
        replied_message = message.reply_to_message
        source_text = replied_message.text or replied_message.caption or ""
        match = re.search(r"Telegram ID:\s*(\d+)", source_text)
        if match:
            customer_id = int(match.group(1))

    if customer_id is None:
        thread_id = message.message_thread_id
        if thread_id:
            for cid, tid in CUSTOMER_TOPICS.items():
                if tid == thread_id:
                    customer_id = cid
                    break

    if customer_id is None:
        return

    try:
        if message.text:
            await context.bot.send_message(chat_id=customer_id, text=message.text)
        elif message.photo:
            await context.bot.send_photo(chat_id=customer_id, photo=message.photo[-1].file_id, caption=message.caption)
        
        await message.reply_text("✅ 已发送给客户。")
    except Exception as e:
        print(f"❌ 客服回复失败：{e}")
        await message.reply_text("❌ 发送失败，用户可能屏蔽了机器人。")


# ==========================================
# 底部固定菜单（ReplyKeyboard）点击处理
# ==========================================
async def reply_keyboard_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    text = update.message.text

    if text == "📝 注册平台":
        await send_feature_message(update, "📝 【1. 注册平台】\n\n点击下方链接或访问官网完成账号注册：\nhttps://t.me/your_channel_link")
    elif text == "🎁 新人彩金":
        await send_feature_message(update, "🎁 【2. 新人彩金】\n\n新用户首次绑定并完成实名，即可联系客服领取丰厚新人彩金！")
    elif text == "📅 签到彩金":
        await send_feature_message(update, "📅 【3. 签到彩金】\n\n每日打卡签到，连续签到天数越多，签到彩金越丰厚！")
    elif text == "💰 日存彩金":
        await send_feature_message(update, "💰 【4. 日存彩金】\n\n每日充值尊享日存彩金加赠，多充多送，实时到账！")
    elif text == "👥 推荐好礼":
        await send_feature_message(update, "👥 【5. 推荐好礼】\n\n分享您的专属邀请链接给好友，共同享受丰厚推荐返利与好礼！")
    elif text == "🗺 探索秘境":
        await send_feature_message(update, "🗺 【6. 探索秘境】\n\n欢迎来到秘境探索频道，点击开启您的奇妙旅程：\nhttps://t.me/your_channel_link")
    elif text == "📞 联系客服":
        await send_feature_message(update, "📞 【联系客服】\n\n如有任何疑问，请直接在对话框发送消息，专属客服将为您解答。")


# ============================================================
# 定时群发广告任务（使用官方 JobQueue）
# ============================================================
async def send_scheduled_ads(context: ContextTypes.DEFAULT_TYPE):
    for chat_id in list(ACTIVE_GROUPS):
        try:
            # 群发时如果也有海报，也可以带上海报或纯文字
            if os.path.exists(POSTER_IMAGE):
                with open(POSTER_IMAGE, "rb") as photo:
                    await context.bot.send_photo(chat_id=chat_id, photo=photo, caption=AD_CONTENT, reply_markup=get_inline_keyboard())
            else:
                await context.bot.send_message(chat_id=chat_id, text=AD_CONTENT, reply_markup=get_inline_keyboard())
        except Exception as e:
            print(f"❌ 向群组 {chat_id} 发送广告失败: {e}")


# ============================================================
# Render 健康检查服务器
# ============================================================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"AvGood Bot is running!")

    def log_message(self, format, *args):
        pass


def start_health_server():
    port = int(os.environ.get("PORT", "10000"))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    print(f"Health server started on port {port}")
    server.serve_forever()


# ==================================================
# 主程序
# ==================================================
def main():
    app = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .post_init(setup_bot_commands)
        .build()
    )

    # 注册 1 小时（3600秒）循环一次的广告定时任务
    if app.job_queue:
        app.job_queue.run_repeating(send_scheduled_ads, interval=3600, first=60)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("admin", admin_test))
    app.add_handler(CommandHandler("groupid", groupid))
    
    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE
            & filters.Regex(r"^(📝 注册平台|🎁 新人彩金|📅 签到彩金|💰 日存彩金|👥 推荐好礼|🗺 探索秘境|📞 联系客服)$"),
            reply_keyboard_handler
        )
    )
    
    app.add_handler(CallbackQueryHandler(button_handler))

    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & ~filters.COMMAND,
            forward_customer_message
        )
    )

    app.add_handler(
        MessageHandler(
            filters.Chat(SUPPORT_GROUP_ID) & ~filters.COMMAND,
            admin_reply_customer
        )
    )

    print("🤖 AvGood Bot 已启动... v5")
    print("等待用户发送 /start")

    import threading
    threading.Thread(target=start_health_server, daemon=True).start()

    app.run_polling(
        poll_interval=1,
        timeout=30,
        bootstrap_retries=-1,
        drop_pending_updates=False
    )

if __name__ == "__main__":
    main()
