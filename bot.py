import os
import re
import threading
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
# 把这里换成你刚刚从 BotFather 获取的新 Token
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
        BotCommand("products", "🛒 商品"),
        BotCommand("orders", "📦 我的订单"),
        BotCommand("support", "📞 联系客服"),
    ])

MAIN_REPLY_KEYBOARD = [
    ["🛒 商品", "📦 我的订单"],
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

    keyboard = [
        [
            InlineKeyboardButton(
                "🛒 商品",
                callback_data="products"
            )
        ],
        [
            InlineKeyboardButton(
                "📦 我的订单",
                callback_data="orders"
            )
        ],
        [
            InlineKeyboardButton(
                "📞 联系客服",
                callback_data="support"
            )
        ],
    ]

    await update.message.reply_text(
        "👋 欢迎来到 AvGood！\n\n"
        "请选择你需要的服务：",
        reply_markup=MAIN_REPLY_MARKUP,
    )

# ==================================================
# 获取当前群组 ID（临时使用）
# ==================================================
async def groupid(update: Update, context: ContextTypes.DEFAULT_TYPE):

    chat = update.effective_chat

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
        await update.message.reply_text(
            "❌ 你没有管理员权限。"
        )
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

    if query.data == "products":

        keyboard = [
            [
                InlineKeyboardButton(
                    "💎 VIP会员 ¥100",
                    callback_data="buy_vip"
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ 返回主菜单",
                    callback_data="main_menu"
                )
            ]
        ]

        await query.edit_message_text(
            "🛒 商品列表\n\n"
            "💎 VIP会员\n"
            "价格：¥100\n\n"
            "请选择商品：",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif query.data == "orders":

        keyboard = [
            [
                InlineKeyboardButton(
                    "⬅️ 返回主菜单",
                    callback_data="main_menu"
                )
            ]
        ]

        await query.edit_message_text(
            "📦 我的订单\n\n"
            "目前还没有订单。",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif query.data == "support":

        keyboard = [
            [
                InlineKeyboardButton(
                    "⬅️ 返回主菜单",
                    callback_data="main_menu"
                )
            ]
        ]

        await query.edit_message_text(
            "📞 联系客服\n\n"
            "如有问题，请联系客服。",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif query.data == "main_menu":

        keyboard = [
            [
                InlineKeyboardButton(
                    "🛒 商品",
                    callback_data="products"
                )
            ],
            [
                InlineKeyboardButton(
                    "📦 我的订单",
                    callback_data="orders"
                )
            ],
            [
                InlineKeyboardButton(
                    "📞 联系客服",
                    callback_data="support"
                )
            ]
        ]

        await query.edit_message_text(
            "👋 欢迎来到 AvGood！\n\n"
            "请选择你需要的服务：",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

# ============================================================
# 支付
# ============================================================
    elif query.data == "buy_vip":

        keyboard = [
            [
                InlineKeyboardButton(
                    "💰 支付宝",
                    callback_data="alipay"
                ),
                InlineKeyboardButton(
                    "💚 微信支付",
                    callback_data="wechat"
                ),
                InlineKeyboardButton(
                    "₮ USDT",
                    callback_data="usdt"
                )
            ]
        ]

        await query.edit_message_text(
            "💎 VIP会员\n\n"
            "价格：¥100\n\n"
            "请选择支付方式：",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif query.data == "alipay":

        keyboard = [
            [
                InlineKeyboardButton(
                    "📸 我已完成支付",
                    callback_data="paid_alipay"
                )
            ]
        ]

        if not os.path.exists(ALIPAY_QR):

            await query.message.reply_text(
                "❌ 找不到支付宝收款码。\n\n"
                "请确认 alipay.png 在机器人文件夹中。"
            )

            return

        with open(ALIPAY_QR, "rb") as photo:

            await query.message.reply_photo(
                photo=photo,
                caption=(
                    "💰 支付宝支付\n\n"
                    "订单金额：¥100\n\n"
                    "请扫描上面的二维码完成支付。\n\n"
                    "⚠️ 请准确支付 ¥100\n\n"
                    "支付完成后，点击下面：\n"
                    "📸 我已完成支付"
                ),
                reply_markup=InlineKeyboardMarkup(keyboard),
            )

    elif query.data == "wechat":

        keyboard = [
            [
                InlineKeyboardButton(
                    "📸 我已完成支付",
                    callback_data="paid_wechat"
                )
            ]
        ]

        if not os.path.exists(WECHAT_QR):

            await query.message.reply_text(
                "❌ 找不到微信收款码。\n\n"
                "请确认 wechat.png 在机器人文件夹中。"
            )

            return

        with open(WECHAT_QR, "rb") as photo:

            await query.message.reply_photo(
                photo=photo,
                caption=(
                    "💚 微信支付\n\n"
                    "订单金额：¥100\n\n"
                    "请扫描上面的微信二维码完成支付。\n\n"
                    "⚠️ 请准确支付 ¥100\n\n"
                    "支付完成后，点击下面：\n"
                    "📸 我已完成支付"
                ),
                reply_markup=InlineKeyboardMarkup(keyboard),
            )

    elif query.data == "usdt":

        keyboard = [
            [
                InlineKeyboardButton(
                    "📋 复制收款地址",
                    callback_data="copy_usdt"
                )
            ],
            [
                InlineKeyboardButton(
                    "📸 我已完成支付",
                    callback_data="paid_usdt"
                )
            ]
        ]

        if not os.path.exists(USDT_QR):

            await query.message.reply_text(
                "❌ 找不到 USDT 二维码。\n\n"
                "请确认 usdt.png 已放在机器人文件夹中。"
            )

            return

        with open(USDT_QR, "rb") as photo:

            await query.message.reply_photo(
                photo=photo,
                caption=(
                    "₮ USDT-TRC20 支付\n\n"
                    f"订单金额：{USDT_AMOUNT}\n"
                    f"网络：{USDT_NETWORK}\n\n"
                    "💳 收款地址：\n"
                    f"{USDT_ADDRESS}\n\n"
                    "⚠️ 请务必确认网络为 TRC20。\n"
                    "⚠️ 转账前请仔细核对收款地址。\n\n"
                    "请扫描上面的二维码完成支付。\n\n"
                    "支付完成后，点击下面：\n"
                    "📸 我已完成支付"
                ),
                reply_markup=InlineKeyboardMarkup(keyboard),
            )

    elif query.data == "paid_alipay":

        context.user_data["awaiting_payment_screenshot"] = True
        context.user_data["payment_method"] = "支付宝"
        
        await query.message.reply_text(
            "📸 请上传你的支付宝付款截图。\n\n"
            "上传后，我们会提交给管理员审核。"
        )

    elif query.data == "paid_wechat":

        context.user_data["awaiting_payment_screenshot"] = True
        context.user_data["payment_method"] = "微信支付"
        
        await query.message.reply_text(
            "📸 请上传你的微信付款截图。\n\n"
            "上传后，我们会提交给管理员审核。"
        )

    elif query.data == "copy_usdt":

        await query.answer(
            "USDT地址已显示，请长按地址复制。",
            show_alert=True
        )

        await query.message.reply_text(
            "📋 USDT-TRC20 收款地址：\n\n"
            f"{USDT_ADDRESS}\n\n"
            "⚠️ 网络：TRC20\n"
            "⚠️ 请核对地址后再转账。"
        )

    elif query.data == "paid_usdt":

        context.user_data["awaiting_payment_screenshot"] = True
        context.user_data["payment_method"] = "USDT"
    
        await query.message.reply_text(
            "📸 请上传你的 USDT 转账截图。\n\n"
            "请确保截图能够清楚显示：\n"
            "• 转账金额\n"
            "• 转账状态\n"
            "• TRC20 网络\n\n"
            "上传后，我们会提交给管理员审核。"
        )

    elif query.data.startswith("approve_"):

        if update.effective_user.id != ADMIN_ID:

            await query.answer(
                "❌ 只有管理员可以操作",
                show_alert=True
            )

            return

        user_id = int(query.data.split("_")[1])

        product_content = (
            "🎁 AvGood VIP会员\n\n"
            "感谢你的购买！\n\n"
            "📌 商品编号：AVG001\n"
            "📌 有效期：30天\n\n"
            "这是你的测试商品内容。\n\n"
            "如有问题，请联系客服。"
        )

        await context.bot.send_message(
            chat_id=user_id,
            text=(
                "🎉 支付审核通过！\n\n"
                "💎 商品：VIP会员\n"
                "💰 金额：¥100\n\n"
                "✅ 你的付款已经确认。\n\n"
                "📦 正在为你自动发货……"
            )
        )

        await context.bot.send_message(
            chat_id=user_id,
            text=product_content
        )

        await query.edit_message_caption(
            caption=(
                "✅ 付款审核通过\n\n"
                f"👤 用户 ID：{user_id}\n"
                "💰 金额：¥100\n"
                "💎 商品：VIP会员\n\n"
                "📦 商品已自动发货。"
            )
        )

    elif query.data.startswith("reject_"):

        if update.effective_user.id != ADMIN_ID:

            await query.answer(
                "❌ 只有管理员可以操作",
                show_alert=True
            )

            return

        user_id = int(query.data.split("_")[1])

        await context.bot.send_message(
            chat_id=user_id,
            text=(
                "❌ 付款审核未通过。\n\n"
                "请检查付款金额是否正确，"
                "然后重新提交付款截图。\n\n"
                "如有疑问，请联系客服。"
            )
        )

        await query.edit_message_caption(
            caption=(
                "❌ 付款审核拒绝\n\n"
                f"👤 用户 ID：{user_id}\n"
                "💰 金额：¥100\n"
                "💎 商品：VIP会员\n\n"
                "📩 已通知用户重新提交。"
            )
        )

# ============================================================
# Telegram 菜单命令
# ============================================================

async def products_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton(
                "💎 VIP会员 ¥100",
                callback_data="buy_vip"
            )
        ]
    ]

    await update.message.reply_text(
        "🛒 商品列表\n\n"
        "💎 VIP会员\n"
        "价格：¥100\n\n"
        "请选择商品：",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def orders_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📦 我的订单\n\n"
        "目前还没有订单。"
    )


async def support_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📞 联系客服\n\n"
        "如有问题，请联系客服。"
    )
    
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

    # 只处理客户私聊
    if update.effective_chat.type != "private":
        return

    # 不处理机器人自己的消息
    if user.is_bot:
        return

    username = f"@{user.username}" if user.username else "未设置"

    # ========================================================
    # 获取 / 创建客户对应的话题
    # ========================================================

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
            
            # 记录新客户
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

    else:
        topic_id = CUSTOMER_TOPICS[customer_id]

    # 第一次创建话题时，上面已经保存 topic_id
    topic_id = CUSTOMER_TOPICS[customer_id]

    # ========================================================
    # 📝 文字消息
    # ========================================================

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

    # ========================================================
    # 🖼 图片
    # ========================================================

    elif message.photo:

        caption = (
            "👤 客户图片\n\n"
            f"👤 姓名：{user.full_name}\n"
            f"🔹 用户名：{username}\n"
            f"🆔 Telegram ID：{user.id}\n\n"
            "🖼 客户发送了一张图片"
        )

        if message.caption:
            caption += f"\n\n📝 图片说明：\n{message.caption}"

        await context.bot.send_photo(
            chat_id=SUPPORT_GROUP_ID,
            message_thread_id=topic_id,
            photo=message.photo[-1].file_id,
            caption=caption
        )

    # ========================================================
    # 🎥 视频
    # ========================================================

    elif message.video:

        caption = (
            "👤 客户视频\n\n"
            f"👤 姓名：{user.full_name}\n"
            f"🔹 用户名：{username}\n"
            f"🆔 Telegram ID：{user.id}\n\n"
            "🎥 客户发送了一段视频"
        )

        if message.caption:
            caption += f"\n\n📝 视频说明：\n{message.caption}"

        await context.bot.send_video(
            chat_id=SUPPORT_GROUP_ID,
            message_thread_id=topic_id,
            video=message.video.file_id,
            caption=caption
        )

    # ========================================================
    # 📄 文件
    # ========================================================

    elif message.document:

        caption = (
            "👤 客户文件\n\n"
            f"👤 姓名：{user.full_name}\n"
            f"🔹 用户名：{username}\n"
            f"🆔 Telegram ID：{user.id}\n\n"
            f"📄 文件：{message.document.file_name or '未命名文件'}"
        )

        if message.caption:
            caption += f"\n\n📝 文件说明：\n{message.caption}"

        await context.bot.send_document(
            chat_id=SUPPORT_GROUP_ID,
            message_thread_id=topic_id,
            document=message.document.file_id,
            caption=caption
        )

    # ========================================================
    # 🎤 语音
    # ========================================================

    elif message.voice:

        caption = (
            "👤 客户语音\n\n"
            f"👤 姓名：{user.full_name}\n"
            f"🔹 用户名：{username}\n"
            f"🆔 Telegram ID：{user.id}\n\n"
            "🎤 客户发送了一条语音"
        )

        await context.bot.send_voice(
            chat_id=SUPPORT_GROUP_ID,
            message_thread_id=topic_id,
            voice=message.voice.file_id,
            caption=caption
        )

    # ========================================================
    # 🎵 音频
    # ========================================================

    elif message.audio:

        caption = (
            "👤 客户音频\n\n"
            f"👤 姓名：{user.full_name}\n"
            f"🔹 用户名：{username}\n"
            f"🆔 Telegram ID：{user.id}\n\n"
            "🎵 客户发送了一段音频"
        )

        await context.bot.send_audio(
            chat_id=SUPPORT_GROUP_ID,
            message_thread_id=topic_id,
            audio=message.audio.file_id,
            caption=caption
        )

    # ========================================================
    # 😀 贴纸
    # ========================================================

    elif message.sticker:

        await context.bot.send_sticker(
            chat_id=SUPPORT_GROUP_ID,
            message_thread_id=topic_id,
            sticker=message.sticker.file_id
        )

        await context.bot.send_message(
            chat_id=SUPPORT_GROUP_ID,
            message_thread_id=topic_id,
            text=(
                f"👤 客户：{user.full_name}\n"
                f"🆔 Telegram ID：{user.id}\n"
                "😀 客户发送了一张贴纸"
            )
        )

    # ========================================================
    # 其他类型
    # ========================================================

    else:

        await context.bot.send_message(
            chat_id=SUPPORT_GROUP_ID,
            message_thread_id=topic_id,
            text=(
                "👤 客户发送了新的消息\n\n"
                f"👤 姓名：{user.full_name}\n"
                f"🔹 用户名：{username}\n"
                f"🆔 Telegram ID：{user.id}\n\n"
                "⚠️ 当前消息类型暂不支持自动转发。"
            )
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

    # 只处理客服群
    if chat.id != SUPPORT_GROUP_ID:
        return

    # 只允许客服群管理员回复客户
    try:
        member = await context.bot.get_chat_member(
            chat_id=SUPPORT_GROUP_ID,
            user_id=user.id
        )

        if member.status not in ("administrator", "creator"):
            return

    except Exception:
        return

    # ==============================================
    # 确定要回复的客户
    # 支持两种方式：
    # ① 回复客户消息
    # ② 直接在客户话题中发送
    # ==============================================
    customer_id = None

    # =================================================
    # 方式①：客服点击客户消息进行回复
    # =================================================
    if message.reply_to_message:

        replied_message = message.reply_to_message

        source_text = (
            replied_message.text
            or replied_message.caption
            or ""
        )

        match = re.search(
            r"Telegram ID:\s*(\d+)",
            source_text
        )

        if match:
            customer_id = int(match.group(1))

    # =================================================
    # 方式②：客服直接在客户话题中发送
    # =================================================
    if customer_id is None:

        thread_id = message.message_thread_id

        if thread_id:

            for cid, tid in CUSTOMER_TOPICS.items():

                if tid == thread_id:
                    customer_id = cid
                    break

    # ----------------------------------------------
    # 找不到客户
    # ----------------------------------------------
    if customer_id is None:

        await message.reply_text(
            "⚠️ 无法找到对应客户。\n\n"
            "请确认你是在客户对应的话题中发送消息。"
        )

        return

    try:

        # ==================================================
        # 管理员发送文字
        # ==================================================
        if message.text:

            await context.bot.send_message(
                chat_id=customer_id,
                text=message.text,
            )

        # ==================================================
        # 管理员发送图片
        # ==================================================
        elif message.photo:

            await context.bot.send_photo(
                chat_id=customer_id,
                photo=message.photo[-1].file_id,
                caption=message.caption,
            )

        # ==================================================
        # 管理员发送视频
        # ==================================================
        elif message.video:

            await context.bot.send_video(
                chat_id=customer_id,
                video=message.video.file_id,
                caption=message.caption,
            )

        # ==================================================
        # 管理员发送文件
        # ==================================================
        elif message.document:

            await context.bot.send_document(
                chat_id=customer_id,
                document=message.document.file_id,
                caption=message.caption,
            )

        # ==================================================
        # 管理员发送语音
        # ==================================================
        elif message.voice:

            await context.bot.send_voice(
                chat_id=customer_id,
                voice=message.voice.file_id,
                caption=message.caption,
            )

        # ==================================================
        # 管理员发送音频
        # ==================================================
        elif message.audio:

            await context.bot.send_audio(
                chat_id=customer_id,
                audio=message.audio.file_id,
                caption=message.caption,
            )

        # ==================================================
        # 管理员发送贴纸
        # ==================================================
        elif message.sticker:

            await context.bot.send_sticker(
                chat_id=customer_id,
                sticker=message.sticker.file_id,
            )

        else:

            await message.reply_text(
                "⚠️ 这个消息类型暂时不支持转发给客户。"
            )

            return

        # 客服群提示
        await message.reply_text(
            "✅ 已发送给客户。"
        )

    except Exception as e:

        print(
            f"❌ 客服回复客户失败：{e}"
        )

        await message.reply_text(
            "❌ 发送失败。\n\n"
            "可能是客户已经屏蔽机器人，"
            "或者机器人无法向该用户发送消息。"
        )

# ==================================================
# 接收付款截图
# ==================================================
async def payment_screenshot(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not context.user_data.get("awaiting_payment_screenshot"):
        await forward_customer_message(update, context)
        return
   
    user = update.effective_user
    photo = update.message.photo[-1]

    context.user_data["awaiting_payment_screenshot"] = False

    keyboard = [
        [
            InlineKeyboardButton(
                "✅ 通过",
                callback_data=f"approve_{user.id}",
            ),
            InlineKeyboardButton(
                "❌ 拒绝",
                callback_data=f"reject_{user.id}",
            ),
        ]
    ]

    caption = (
        "📥 收到新的付款截图\n\n"
        f"👤 用户：{user.full_name}\n"
        f"🆔 Telegram ID：{user.id}\n"
        "💰 订单金额：¥100\n"
        "💎 商品：VIP会员\n\n"
        "请管理员审核："
    )

    # 发送给管理员
    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=photo.file_id,
        caption=caption,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

    # 通知用户
    await update.message.reply_text(
        "✅ 付款截图已提交！\n\n"
        "📋 我们已经把你的付款截图发送给管理员审核。\n\n"
        "⏳ 请等待审核结果。"
    )

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

    server = HTTPServer(
        ("0.0.0.0", port),
        HealthHandler
    )

    print(f"Health server started on port {port}")

    server.serve_forever()

# ==========================================
# 底部固定菜单处理
# ==========================================
async def reply_keyboard_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    text = update.message.text

    if text == "🛒 商品":
        await products_command(update, context)

    elif text == "📦 我的订单":
        await orders_command(update, context)

    elif text == "📞 联系客服":
        await support_command(update, context)

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

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    app.add_handler(
      CommandHandler(
            "products",
           products_command
        )
    )


    app.add_handler(
       CommandHandler(
            "orders",
            orders_command
        )
    )


    app.add_handler(
       CommandHandler(
            "support",
            support_command
        )
    )

    app.add_handler(
       MessageHandler(
        filters.ChatType.PRIVATE
            & filters.Regex(r"^(🛒 商品|📦 我的订单|📞 联系客服)$"),
            reply_keyboard_handler
        )
    )
    
    app.add_handler(
        CommandHandler(
            "myid",
            myid
        )
    )

    app.add_handler(
        CommandHandler(
            "admin",
            admin_test
        )
    )

    app.add_handler(
    CommandHandler(
        "groupid",
        groupid
    )
)
    
    app.add_handler(
        CallbackQueryHandler(
            button_handler
        )
    )

    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.PHOTO,
            payment_screenshot
        )
    )

    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & ~filters.COMMAND & ~filters.PHOTO,
            forward_customer_message
        )
    )

    app.add_handler(
        MessageHandler(
            filters.Chat(SUPPORT_GROUP_ID)
        & ~filters.COMMAND,
            admin_reply_customer
        )
    )
    print("🤖 AvGood Bot 已启动... v2")
    print("等待用户发送 /start")

    threading.Thread(
        target=start_health_server,
        daemon=True
    ).start()

    app.run_polling(
        poll_interval=1,
        timeout=30,
        bootstrap_retries=-1,
        drop_pending_updates=False
    )
# =========================================
# 启动
# ==================================================
if __name__ == "__main__":
    main()
