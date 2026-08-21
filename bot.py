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
# 客服群 ID（请确保这里是你的真实群 ID）
# ==================================================
SUPPORT_GROUP_ID = -1003749620184
CUSTOMER_TOPICS = {}
TOPIC_CUSTOMERS = {}

# ==================================================
# 客服锁定状态管理
# ==================================================
CUSTOMER_AGENTS = {}  # 记录 customer_id -> 当前接待的 admin_id (int)
CUSTOMER_AGENT_NAMES = {} # 记录 customer_id -> 管理员姓名

# ==================================================
# 定时群发广告配置（支持不同群发送不同的【文案】和【图片】）
# ==================================================
GROUP_ADS = {
    -100371994486: {
        "text": (
            "📢 T1体育｜娱乐俱乐部 ⚽️🔥\n"
            "✅ 免实名｜无需绑卡｜无需手机号\n"
            "✅ 不限IP｜支持 USDT 充值提现\n"
            "🎁 新人福利\n"
            "❤️ 注册送彩金 + 首单包赔\n"
            "❤️ 首存500，享足球宝贝福利\n"
            "❤️ 达到月流水，可享高端会所服务\n"
            "📩 开户请联系我\n"
            "⚠️ 群内其他人员主动私信、均为诈骗！\n"
            "🔗 唯一永久防失联导航：\n"
            "https://jully.pw\n"
            "🚨 防骗提醒\n"
            "群主、管理员不会主动私聊或要求充值。\n"
            "如有疑问，请直接在群内 @管理员 公开咨询。"
        ),
        "image": "ad1.png"  # 第一个群专属的图片文件名
    },
    -1001150445713: {
        "text": (
            "📢 T1体育｜赛事情报站 ⚽️🔥\n"
            "✅ 免实名｜无需绑卡｜无需手机号\n"
            "✅ 不限IP｜支持 USDT 充值提现\n"
            "🎁 新人福利\n"
            "❤️ 注册送彩金 + 首单包赔\n"
            "❤️ 首存500，享足球宝贝福利\n"
            "❤️ 达到月流水，可享高端会所服务\n"
            "📩 开户请联系我\n"
            "⚠️ 群内其他人员主动私信、均为诈骗！\n"
            "🔗 唯一永久防失联导航：\n"
            "https://jully.pw\n"
            "🚨 防骗提醒\n"
            "群主、管理员不会主动私聊或要求充值。\n"
            "如有疑问，请直接在群内 @管理员 公开咨询。"
        ),
        "image": "ad2.png"  # 第二个群专属的图片文件名
    },
}

ACTIVE_GROUPS = set(GROUP_ADS.keys())

# ============================================================
# 定时群发广告任务（图文完全独立版）
# ============================================================
async def send_scheduled_ads(context: ContextTypes.DEFAULT_TYPE):
    for chat_id, data in GROUP_ADS.items():
        ad_text = data["text"]
        ad_image_name = data["image"]
        try:
            ad_image_path = os.path.join(BASE_DIR, ad_image_name)
            if os.path.exists(ad_image_path):
                with open(ad_image_path, "rb") as photo:
                    await context.bot.send_photo(
                        chat_id=chat_id, 
                        photo=photo, 
                        caption=ad_text, 
                        reply_markup=get_inline_keyboard()
                    )
            else:
                await context.bot.send_message(
                    chat_id=chat_id, 
                    text=ad_text, 
                    reply_markup=get_inline_keyboard()
                )
        except Exception as e:
            print(f"❌ 向群组 {chat_id} 发送广告失败: {e}")

# ==================================================
# 文件所在目录
# ==================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

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
    ])

MAIN_REPLY_KEYBOARD = [
    ["📝 注册平台", "🎁 新人彩金"],
    ["📅 签到彩金", "💰 日存彩金"],
    ["👥 推荐好礼", "🗺 探索秘境"],
]

MAIN_REPLY_MARKUP = ReplyKeyboardMarkup(
    MAIN_REPLY_KEYBOARD,
    resize_keyboard=True,
    is_persistent=True,
)

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
        ]
    ])

# 生成接入工单的内联按钮
def get_support_control_keyboard(customer_id, current_agent_name=None):
    if current_agent_name:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(f"🔒 已由 【{current_agent_name}】 接待", callback_data="none")],
            [InlineKeyboardButton("🔓 释放/转交客户", callback_data=f"release_agent_{customer_id}")]
        ])
    else:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 点击接入接待", callback_data=f"take_agent_{customer_id}")]
        ])

# ==================================================
# 核心公共函数：确保客户私聊时在群里有专属话题
# ==================================================
async def ensure_customer_topic(context: ContextTypes.DEFAULT_TYPE, user):
    customer_id = user.id
    username = f"@{user.username}" if user.username else "未设置"

    if customer_id in CUSTOMER_TOPICS:
        return CUSTOMER_TOPICS[customer_id]

    try:
        topic_name = f"👤 {user.full_name}"
        topic = await context.bot.create_forum_topic(
            chat_id=SUPPORT_GROUP_ID,
            name=topic_name
        )

        CUSTOMER_TOPICS[customer_id] = topic.message_thread_id
        TOPIC_CUSTOMERS[topic.message_thread_id] = customer_id
        
        # 第一次创建话题时，发送完整的客户名片信息，并附带“点击接入”按钮
        card_msg = await context.bot.send_message(
            chat_id=SUPPORT_GROUP_ID,
            message_thread_id=topic.message_thread_id,
            text=(
                "🆕 新客户咨询\n\n"
                f"👤 姓名：{user.full_name}\n"
                f"🔹 用户名：{username}\n"
                f"🆔 Telegram ID：{user.id}\n\n"
                "📌 【此客户名片已置顶，请点击下方按钮抢单/接入】"
            ),
            reply_markup=get_support_control_keyboard(customer_id)
        )
        
        # 尝试置顶这条名片消息
        try:
            await context.bot.pin_chat_message(
                chat_id=SUPPORT_GROUP_ID,
                message_id=card_msg.message_id
            )
        except Exception:
            pass

    except Exception as e:
        print(f"❌ 创建客户话题失败：{e}")
        return None
    
    return CUSTOMER_TOPICS[customer_id]


# ==================================================
# 专用函数：将客户点击按钮的动作通知到对应话题
# ==================================================
async def notify_customer_action(context: ContextTypes.DEFAULT_TYPE, user, action_name):
    if not user or user.is_bot:
        return
    topic_id = await ensure_customer_topic(context, user)
    if topic_id:
        try:
            text = f"👆 客户点击了按钮：【 {action_name} 】"
            await context.bot.send_message(
                chat_id=SUPPORT_GROUP_ID,
                message_thread_id=topic_id,
                text=text
            )
        except Exception as e:
            print(f"❌ 同步客户按钮点击到群组失败：{e}")


# ==================================================
# 发送独立海报图文的通用函数
# ==================================================
async def send_feature_content(update_or_query, image_filename, text_content):
    if hasattr(update_or_query, "message") and update_or_query.message:
        target_message = update_or_query.message
    else:
        target_message = update_or_query

    image_path = os.path.join(BASE_DIR, image_filename)

    if os.path.exists(image_path):
        with open(image_path, "rb") as photo:
            try:
                await target_message.reply_photo(
                    photo=photo,
                    caption=text_content,
                    reply_markup=get_inline_keyboard()
                )
                return
            except Exception:
                pass
    
    await target_message.reply_text(
        text=text_content,
        reply_markup=get_inline_keyboard()
    )


# ==================================================
# /start
# ==================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "👋 欢迎来到平台！\n\n"
        "🔥 请直接在对话框发送消息向客服咨询，或点击下方按钮选择您需要体验的服务："
    )
    
    start_image = os.path.join(BASE_DIR, "start.png")
    if os.path.exists(start_image):
        with open(start_image, "rb") as photo:
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
# 按钮点击处理（包含客服接入/释放的内联按钮动作）
# ==================================================
async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    user = query.from_user
    data = query.data

    # 处理客服在群里点击“接入”或“释放”按钮
    if data.startswith("take_agent_") or data.startswith("release_agent_"):
        # 验证是否为群管理员
        try:
            member = await context.bot.get_chat_member(chat_id=SUPPORT_GROUP_ID, user_id=user.id)
            if member.status not in ("administrator", "creator"):
                await query.answer("❌ 只有群管理员才可以操作！", show_alert=True)
                return
        except Exception:
            await query.answer("❌ 权限校验失败", show_alert=True)
            return

        parts = data.split("_")
        action = parts[0]
        customer_id = int(parts[2])

        if action == "take":
            current_agent = CUSTOMER_AGENTS.get(customer_id)
            if current_agent and current_agent != user.id:
                await query.answer(f"❌ 该客户已被 【{CUSTOMER_AGENT_NAMES.get(customer_id, '其他客服')}】 抢先接入！", show_alert=True)
                return
            
            # 成功接入
            CUSTOMER_AGENTS[customer_id] = user.id
            CUSTOMER_AGENT_NAMES[customer_id] = user.full_name
            await query.answer(f"✅ 成功接入客户 【{user.full_name}】！现在您可以回复他了。", show_alert=True)
            
            # 更新按钮状态
            try:
                await query.edit_message_reply_markup(
                    reply_markup=get_support_control_keyboard(customer_id, user.full_name)
                )
            except Exception:
                pass
            
            # 在话题里发个提示
            await context.bot.send_message(
                chat_id=SUPPORT_GROUP_ID,
                message_thread_id=query.message.message_thread_id,
                text=f"🔒 客服 **{user.full_name}** 已成功接入该对话。"
            )

        elif action == "release":
            current_agent = CUSTOMER_AGENTS.get(customer_id)
            if current_agent != user.id:
                try:
                    member = await context.bot.get_chat_member(chat_id=SUPPORT_GROUP_ID, user_id=user.id)
                    if member.status not in ("administrator", "creator"):
                        await query.answer("❌ 只有当前接待该客服或超级管理员才能释放！", show_alert=True)
                        return
                except Exception:
                    await query.answer("❌ 无权操作", show_alert=True)
                    return

            CUSTOMER_AGENTS.pop(customer_id, None)
            CUSTOMER_AGENT_NAMES.pop(customer_id, None)
            await query.answer("🔓 已成功释放该客户，其他管理员可重新接入。", show_alert=True)
            
            # 还原按钮为“点击接入接待”
            try:
                await query.edit_message_reply_markup(
                    reply_markup=get_support_control_keyboard(customer_id)
                )
            except Exception:
                pass

            await context.bot.send_message(
                chat_id=SUPPORT_GROUP_ID,
                message_thread_id=query.message.message_thread_id,
                text="🔓 该客户已被释放，其他管理员现在可以点击上方按钮接入了。"
            )
        return

    if data == "none":
        await query.answer("ℹ️ 此客户已有管理员正在接待中", show_alert=True)
        return

    await query.answer()

    button_mapping = {
        "register": ("📝 注册平台", "register.png", (
            "【1. 注册平台】🎉 福利已上线，早注册早领取！\n"
            "现在加入T1体育，即可享受：\n\n"
            "💰 首存彩金加码\n"
            "🛡 专属包赔活动\n"
            "⚽️ 热门赛事推荐\n"
            "🎯 竞猜互动奖励\n"
            "🎁 隐藏活动福利\n\n"
            "注册时务必填写邀请码：\n"
            "🔑 20001136\n\n"
            "🌐 注册地址：\n"
            "https://www.t1ty.top?agentId=20001136\n\n"
            "永久防失联地址：\n"
            "https://jully.pw\n\n"
            "注册完成后私讯我，即可领取专属福利礼包🎁"
        )),
        "newbie": ("🎁 新人彩金", "newbie.png", (
            "【2. 新人彩金】🔥 新人专属福利已开启！\n\n"
            "首存立享彩金加码 + 包赔护航，更有内部群精选推荐、竞猜互动活动等你参与！\n"
            "超多隐藏福利持续解锁中"
        )),
        "checkin": ("📅 签到彩金", "checkin.png", (
            "【3. 签到彩金】🚀 签到就能领，错过就是少拿！\n\n"
            "每日打卡签到，连续签到天数越多，签到彩金越丰厚！🎁\n\n"
            "⏰ 每月1日重新累计，越早参与越划算！\n\n"
            "回复：签到\n"
            "即可马上为你申请福利"
        )),
        "deposit": ("💰 日存彩金", "deposit.png", (
            "【4. 日存彩金】🚀 今天的福利别漏领！\n\n"
            "每日首笔存款满300元即可参与【复存有礼】活动，额外礼金直接安排！\n"
            "每天仅限领取一次，越早参与越划算！\n\n"
            "回复：每日首存\n"
            "马上为你申请，无需额外操作🎁"
        )),
        "invite": ("👥 推荐好礼", "invite.png", (
            "【5. 推荐好礼】🎉 输赢是比赛的一部分，福利才是真正不能错过的惊喜！\n\n"
            "分享您的专属邀请链接给好友，共同享受丰厚推荐返利与好礼！\n\n"
            "想了解活动详情或领取专属福利，欢迎随时私讯我，在线为你解答～ 🚀❤️"
        )),
        "explore": ("🗺 探索秘境", "explore.png", (
            "【6. 探索秘境】欢迎来到秘境探索频道，点击开启您的奇妙旅程：\n"
            "https://t.me/Avior96Bot\n\n"
            "@Avior96Bot"
        )),
    }

    if query.data in button_mapping:
        name, img, text = button_mapping[query.data]
        await notify_customer_action(context, user, name)
        await send_feature_content(query, img, text)


# ============================================================
# 客服系统：私聊统一消息分发
# ============================================================
async def handle_private_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    message = update.effective_message
    user = update.effective_user

    if not message or not user or user.is_bot:
        return

    if update.effective_chat.type in ["group", "supergroup"]:
        ACTIVE_GROUPS.add(update.effective_chat.id)
        return

    if update.effective_chat.type != "private":
        return

    text = message.text or ""

    keyboard_mapping = {
        "📝 注册平台": ("📝 注册平台", "register.png", (
            "【1. 注册平台】🎉 福利已上线，早注册早领取！\n"
            "现在加入T1体育，即可享受：\n\n"
            "💰 首存彩金加码\n"
            "🛡 专属包赔活动\n"
            "⚽️ 热门赛事推荐\n"
            "🎯 竞猜互动奖励\n"
            "🎁 隐藏活动福利\n\n"
            "注册时务必填写邀请码：\n"
            "🔑 20001136\n\n"
            "🌐 注册地址：\n"
            "https://www.t1ty.top?agentId=20001136\n\n"
            "永久防失联地址：\n"
            "https://jully.pw\n\n"
            "注册完成后私讯我，即可领取专属福利礼包🎁"
        )),
        "🎁 新人彩金": ("🎁 新人彩金", "newbie.png", (
            "【2. 新人彩金】🔥 新人专属福利已开启！\n\n"
            "首存立享彩金加码 + 包赔护航，更有内部群精选推荐、竞猜互动活动等你参与！\n"
            "超多隐藏福利持续解锁中"
        )),
        "📅 签到彩金": ("📅 签到彩金", "checkin.png", (
            "【3. 签到彩金】🚀 签到就能领，错过就是少拿！\n\n"
            "每日打卡签到，连续签到天数越多，签到彩金越丰厚！🎁\n\n"
            "⏰ 每月1日重新累计，越早参与越划算！\n\n"
            "回复：签到\n"
            "即可马上为你申请福利"
        )),
        "💰 日存彩金": ("💰 日存彩金", "deposit.png", (
            "【4. 日存彩金】🚀 今天的福利别漏领！\n\n"
            "每日首笔存款满300元即可参与【复存有礼】活动，额外礼金直接安排！\n"
            "每天仅限领取一次，越早参与越划算！\n\n"
            "回复：每日首存\n"
            "马上为你申请，无需额外操作🎁"
        )),
        "👥 推荐好礼": ("👥 推荐好礼", "invite.png", (
            "【5. 推荐好礼】🎉 输赢是比赛的一部分，福利才是真正不能错过的惊喜！\n\n"
            "分享您的专属邀请链接给好友，共同享受丰厚推荐返利与好礼！\n\n"
            "想了解活动详情或领取专属福利，欢迎随时私讯我，在线为你解答～ 🚀❤️"
        )),
        "🗺 探索秘境": ("🗺 探索秘境", "explore.png", (
            "【6. 探索秘境】欢迎来到秘境探索频道，点击开启您的奇妙旅程：\n"
            "https://t.me/Avior96Bot\n\n"
            "@Avior96Bot"
        )),
    }

    if text in keyboard_mapping:
        name, img, content = keyboard_mapping[text]
        await notify_customer_action(context, user, name)
        await send_feature_content(message, img, content)
        return

    topic_id = await ensure_customer_topic(context, user)
    if not topic_id:
        return

    try:
        if message.text:
            await context.bot.send_message(
                chat_id=SUPPORT_GROUP_ID,
                message_thread_id=topic_id,
                text=message.text
            )
        elif message.photo:
            await context.bot.send_photo(
                chat_id=SUPPORT_GROUP_ID,
                message_thread_id=topic_id,
                photo=message.photo[-1].file_id,
                caption=message.caption or ""
            )
        else:
            await context.bot.send_message(
                chat_id=SUPPORT_GROUP_ID,
                message_thread_id=topic_id,
                text="[客户发送了一条其他类型的消息]"
            )
    except Exception as e:
        print(f"❌ 转发客户消息到群组失败：{e}")


# ==================================================
# 10秒后自动删除提示消息的内部函数
# ==================================================
async def delete_notification_callback(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    chat_id = job_data["chat_id"]
    message_id = job_data["message_id"]
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass


# ==================================================
# 客服系统：管理员解除当前专属绑定命令 (/release)
# ==================================================
async def release_customer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if not message or not user or not chat or chat.id != SUPPORT_GROUP_ID:
        return

    thread_id = message.message_thread_id
    if not thread_id or thread_id not in TOPIC_CUSTOMERS:
        await message.reply_text("❌ 请在具体的客户话题中使用此命令。")
        return

    customer_id = TOPIC_CUSTOMERS[thread_id]
    current_agent = CUSTOMER_AGENTS.get(customer_id)

    if current_agent is None:
        await message.reply_text("ℹ️ 当前客户暂无绑定客服，所有人均可接入。")
        return

    if current_agent != user.id:
        try:
            member = await context.bot.get_chat_member(chat_id=SUPPORT_GROUP_ID, user_id=user.id)
            if member.status not in ("administrator", "creator"):
                await message.reply_text("❌ 只有当前接待该客户的管理员或群管理员才能释放此话题。")
                return
        except Exception:
            return

    CUSTOMER_AGENTS.pop(customer_id, None)
    CUSTOMER_AGENT_NAMES.pop(customer_id, None)
    
    sent_msg = await message.reply_text("🔓 已成功释放该客户！其他管理员现在可以点击按钮重新接入了。")
    if context.job_queue:
        context.job_queue.run_once(
            delete_notification_callback,
            when=10,
            data={"chat_id": chat.id, "message_id": sent_msg.message_id}
        )


# ==================================================
# 客服系统：管理员回复群内话题 → 严格限制必须先点击接入按钮
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

    # 获取当前话题对应的客户 ID
    customer_id = None
    thread_id = message.message_thread_id
    if thread_id and thread_id in TOPIC_CUSTOMERS:
        customer_id = TOPIC_CUSTOMERS[thread_id]

    if customer_id is None:
        return

    # 检查该客户当前由谁接待
    assigned_agent = CUSTOMER_AGENTS.get(customer_id)

    # 如果没有人点击接入，拦截并提示
    if assigned_agent is None:
        sent_err = await message.reply_text(
            "⚠️ 您尚未接入该客户！\n"
            "💡 请先在上方名片消息中点击【 📥 点击接入接待 】按钮，才能与客户对话。"
        )
        if context.job_queue:
            context.job_queue.run_once(
                delete_notification_callback,
                when=10,
                data={"chat_id": chat.id, "message_id": sent_err.message_id}
            )
        return

    # 如果是其他人正在接待，拦截并提示
    if assigned_agent != user.id:
        agent_name = CUSTOMER_AGENT_NAMES.get(customer_id, "其他客服")
        sent_err = await message.reply_text(
            f"❌ 该客户当前正由管理员【 {agent_name} 】接待中，您无法回复。\n"
            "💡 如需接管，请让原管理员在话题内发送 /release 或点击释放按钮解除绑定。"
        )
        if context.job_queue:
            context.job_queue.run_once(
                delete_notification_callback,
                when=10,
                data={"chat_id": chat.id, "message_id": sent_err.message_id}
            )
        return

    try:
        if message.text:
            await context.bot.send_message(chat_id=customer_id, text=message.text)
        elif message.photo:
            await context.bot.send_photo(chat_id=customer_id, photo=message.photo[-1].file_id, caption=message.caption)
        
        sent_msg = await message.reply_text("✅ 已发送给客户。")
        
        if context.job_queue:
            context.job_queue.run_once(
                delete_notification_callback,
                when=10,
                data={"chat_id": chat.id, "message_id": sent_msg.message_id}
            )

    except Exception as e:
        print(f"❌ 客服回复失败：{e}")
        await message.reply_text("❌ 发送失败，用户可能屏蔽了机器人。")


# ============================================================
# 定时群发广告任务（多文案适配版）
# ============================================================
async def send_scheduled_ads(context: ContextTypes.DEFAULT_TYPE):
    for chat_id, ad_text in GROUP_ADS.items():
        try:
            ad_image = os.path.join(BASE_DIR, "ad.png")
            if os.path.exists(ad_image):
                with open(ad_image, "rb") as photo:
                    await context.bot.send_photo(
                        chat_id=chat_id, 
                        photo=photo, 
                        caption=ad_text, 
                        reply_markup=get_inline_keyboard()
                    )
            else:
                await context.bot.send_message(
                    chat_id=chat_id, 
                    text=ad_text, 
                    reply_markup=get_inline_keyboard()
                )
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

    if app.job_queue:
        app.job_queue.run_repeating(send_scheduled_ads, interval=3600, first=60)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("admin", admin_test))
    app.add_handler(CommandHandler("groupid", groupid))
    app.add_handler(CommandHandler("release", release_customer))
    
    # 按钮点击监听
    app.add_handler(CallbackQueryHandler(button_handler))

    # 私聊消息监听
    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & ~filters.COMMAND,
            handle_private_message
        )
    )

    # 客服群回复监听
    app.add_handler(
        MessageHandler(
            filters.Chat(SUPPORT_GROUP_ID) & ~filters.COMMAND,
            admin_reply_customer
        )
    )

    print("🤖 AvGood Bot 已启动... (已实现【抢单接入按钮】专属客服工单制)")
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
