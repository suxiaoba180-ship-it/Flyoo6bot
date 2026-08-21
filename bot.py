import os
import re
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
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
# 存放需要自动发送广告的群组ID集合（机器人被拉入群后会自动收集，也可以手动在这里添加）
ACTIVE_GROUPS = set()
AD_INTERVAL = 3600  # 约1小时 (3600秒)
AD_CONTENT = (
    "🌟 【热门推荐公告】 🌟\n\n"
    "欢迎来到我们的官方频道！\n"
    "🔥 探索无敌秘境，尽享丰厚新人彩金与签到福利！\n"
    "💰 注册平台即送好礼，首存更有超值加赠！\n\n"
    "请点击下方机器人菜单了解详情👇"
)

# ==================================================
# 文件所在目录
# ==================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

ALIPAY_QR = os.path.join(BASE_DIR, "alipay.png")
WECHAT_QR = os.path.join(BASE_DIR, "wechat.png")
USDT_QR = os.path.join(BASE_DIR, "usdt.png")
USDT_ADDRESS = "TAm7hZ3sXDctxFfera4xiTnWffAxRgeFQg"
USDT_AMOUNT = "10 USDT"
USDT_NETWORK = "TRC20"

# ============================================================
# Telegram 左下角菜单
# ============================================================

async def setup_bot_commands(application):
    await application.bot.set_my_commands([
        BotCommand("start", "🏠 开始使用"),
        BotCommand("explore", "🗺 探索秘境"),
        BotCommand("register", "📝 注册平台"),
        BotCommand("newbie", "🎁 新人彩金"),
        BotCommand("invite", "👥 推荐好礼"),
        BotCommand("checkin", "签到彩金"),
        BotCommand("deposit", "💰 首存彩金"),
        BotCommand("support", "📞 联系客服"),
    ])

# 底部固定键盘修改为指定功能
MAIN_REPLY_KEYBOARD = [
    ["🗺 探索秘境", "📝 注册平台"],
    ["🎁 新人彩金", "👥 推荐好礼"],
    ["📅 签到彩金", "💰 首存彩金"],
    ["📞 联系客服"],
]

MAIN_REPLY_MARKUP = ReplyKeyboardMarkup(
    MAIN_REPLY_KEYBOARD,
    resize_keyboard=True,
    is_persistent=True,
)

# ==================================================
# /start
# ==================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("🔥 START 被调用了！")

    await update.message.reply_text(
        "👋 欢迎光临！\n\n"
        "请点击下方功能栏选择你需要的服务：",
        reply_markup=MAIN_REPLY_MARKUP,
    )

# ==================================================
# 获取当前群组 ID（临时使用）
# ==================================================
async def groupid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    # 自动记录群组用于广告群发
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
# 按钮处理
# ==================================================
async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    print("🔥 BUTTON_HANDLER 被调用了！")
    query = update.callback_query
    await query.answer()

    if query.data == "explore":
        await query.message.reply_text("🗺 【探索秘境】\n\n点击链接进入探索：https://t.me/your_channel_link")
    elif query.data == "register":
        await query.message.reply_text("📝 【注册平台】\n\n点击此处完成平台注册：https://t.me/your_channel_link[cite: 1]")
    elif query.data == "newbie":
        await query.message.reply_text("🎁 【新人彩金】\n\n新用户首次绑定即可领取丰厚新人彩金！详情请联系客服[cite: 1]。")
    elif query.data == "invite":
        await query.message.reply_text("👥 【推荐好礼】\n\n邀请好友加入，即可享受多重推荐返利和好礼！[cite: 1]")
    elif query.data == "checkin":
        await query.message.reply_text("📅 【签到彩金】\n\n每日坚持签到，天天领取签到彩金！[cite: 1]")
    elif query.data == "deposit":
        await query.message.reply_text("💰 【首存彩金】\n\n首次充值立享超高比例首存彩金回馈！[cite: 1]")
    elif query.data == "support":
        await query.message.reply_text("📞 【联系客服】\n\n如有任何疑问，请直接发送消息，客服会为您解答。")


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

    # 收集机器人所在的群组（用于定时广告）
    if update.effective_chat.type in ["group", "supergroup"]:
        ACTIVE_GROUPS.add(update.effective_chat.id)
        return

    # 只处理客户私聊
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
                    "🆕 新客户咨询[cite: 1]\n\n"
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
# 底部固定菜单处理
# ==========================================
async def reply_keyboard_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    text = update.message.text

    if text == "🗺 探索秘境":
        await update.message.reply_text("🗺 【探索秘境】\n\n欢迎来到秘境探索，点击开始您的奇妙旅程[cite: 1]！")
    elif text == "📝 注册平台":
        await update.message.reply_text("📝 【注册平台】\n\n请点击以下链接进行账号注册：https://t.me/your_channel_link[cite: 1]")
    elif text == "🎁 新人彩金":
        await update.message.reply_text("🎁 【新人彩金】\n\n新注册用户专享福利，完成新手任务即可领取新人彩金[cite: 1]！")
    elif text == "👥 推荐好礼":
        await update.message.reply_text("👥 【推荐好礼】\n\n分享给好友，共同享受丰厚推荐好礼与奖励[cite: 1]！")
    elif text == "📅 签到彩金":
        await update.message.reply_text("📅 【签到彩金】\n\n每日打卡签到，连续签到更有额外惊喜彩金[cite: 1]！")
    elif text == "💰 首存彩金":
        await update.message.reply_text("💰 【首存彩金】\n\n首次充值尊享超值福利，多充多送[cite: 1]！")
    elif text == "📞 联系客服":
        await update.message.reply_text("📞 【联系客服】\n\n如有任何问题，请直接发送内容，客服将为您解答。")


# ============================================================
# 定时群发广告后台任务
# ============================================================
def start_ad_loop(application):
    def run():
        # 等待 bot 启动稳定
        time.sleep(10)
        while True:
            try:
                # 每隔约1小时执行一次
                time.sleep(AD_INTERVAL)
                # 使用 application 提供的 bot 实例发送消息到已收集的群组
                for chat_id in list(ACTIVE_GROUPS):
                    try:
                        # 在异步事件循环中安全调用发送
                        import asyncio
                        asyncio.run_coroutine_threadsafe(
                            application.bot.send_message(chat_id=chat_id, text=AD_CONTENT),
                            application.loop
                        )
                    except Exception as e:
                        print(f"❌ 向群组 {chat_id} 发送广告失败: {e}")
            except Exception as e:
                print(f"❌ 广告群发线程异常: {e}")

    t = threading.Thread(target=run, daemon=True)
    t.start()


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

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("admin", admin_test))
    app.add_handler(CommandHandler("groupid", groupid))
    
    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE
            & filters.Regex(r"^(🗺 探索秘境|📝 注册平台|🎁 新人彩金|👥 推荐好礼|📅 签到彩金|💰 首存彩金|📞 联系客服)$"),
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

    # 启动群发广告后台线程
    start_ad_loop(app)

    print("🤖 AvGood Bot 已启动... v3")
    print("等待用户发送 /start")

    threading.Thread(target=start_health_server, daemon=True).start()

    app.run_polling(
        poll_interval=1,
        timeout=30,
        bootstrap_retries=-1,
        drop_pending_updates=False
    )

if __name__ == "__main__":
    main()
