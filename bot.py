import os
import re
import sqlite3
import logging
import requests
import random
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand, ReplyKeyboardMarkup
from telegram.error import TelegramError, BadRequest, Forbidden
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)


# ==================================================
# 日志
# ==================================================
logging.basicConfig(level=os.environ.get('LOG_LEVEL', 'INFO').upper(), format='%(asctime)s | %(levelname)s | %(name)s | %(message)s')
logger = logging.getLogger('avgood_bot')

# ==================================================
# Bot Token
# ==================================================
BOT_TOKEN = os.environ["BOT_TOKEN"]


# ==================================================
# 管理员 Telegram ID
# ==================================================
ADMIN_ID = 7708695986

# ==================================================
# 客服群 ID（请确保这里是你的真实群 ID）
# ==================================================
SUPPORT_GROUP_ID = -1003749620184
# 客户话题与客服接待状态全部由 SQLite 持久化。

# ==================================================
# 客服系统持久化数据库
# ==================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE_DIR, "bot_data.db"))

def db_connect():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    with db_connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS customer_topics (
                customer_id INTEGER PRIMARY KEY,
                topic_id INTEGER NOT NULL UNIQUE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS customer_agents (
                customer_id INTEGER PRIMARY KEY,
                agent_id INTEGER NOT NULL,
                agent_name TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS registered_groups (
                chat_id INTEGER PRIMARY KEY,
                chat_title TEXT NOT NULL,
                chat_type TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                registered_by INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

def log_exception(action, exc, *, chat_id=None, user_id=None):
    logger.exception(
        "%s | chat_id=%s | user_id=%s | error=%s",
        action, chat_id, user_id, exc
    )


def save_registered_group(chat_id, chat_title, chat_type, registered_by):
    with db_connect() as conn:
        conn.execute("""
            INSERT INTO registered_groups(
                chat_id, chat_title, chat_type, enabled, registered_by
            )
            VALUES(?, ?, ?, 1, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                chat_title=excluded.chat_title,
                chat_type=excluded.chat_type,
                enabled=1,
                registered_by=excluded.registered_by,
                updated_at=CURRENT_TIMESTAMP
        """, (chat_id, chat_title or "未命名群组", chat_type, registered_by))
        conn.commit()


def get_registered_groups():
    with db_connect() as conn:
        return conn.execute("""
            SELECT chat_id, chat_title, chat_type
            FROM registered_groups
            WHERE enabled = 1
            ORDER BY chat_id
        """).fetchall()


def disable_registered_group(chat_id):
    with db_connect() as conn:
        conn.execute(
            "UPDATE registered_groups SET enabled=0, updated_at=CURRENT_TIMESTAMP WHERE chat_id=?",
            (chat_id,)
        )
        conn.commit()


def get_customer_topic(customer_id):
    with db_connect() as conn:
        row = conn.execute(
            "SELECT topic_id FROM customer_topics WHERE customer_id = ?",
            (customer_id,)
        ).fetchone()
        return row["topic_id"] if row else None

def save_customer_topic(customer_id, topic_id):
    with db_connect() as conn:
        conn.execute("""
            INSERT INTO customer_topics(customer_id, topic_id)
            VALUES(?, ?)
            ON CONFLICT(customer_id) DO UPDATE SET topic_id=excluded.topic_id
        """, (customer_id, topic_id))
        conn.commit()

def get_customer_by_topic(topic_id):
    with db_connect() as conn:
        row = conn.execute(
            "SELECT customer_id FROM customer_topics WHERE topic_id = ?",
            (topic_id,)
        ).fetchone()
        return row["customer_id"] if row else None

def get_customer_agent(customer_id):
    with db_connect() as conn:
        row = conn.execute(
            "SELECT agent_id, agent_name FROM customer_agents WHERE customer_id = ?",
            (customer_id,)
        ).fetchone()
        if not row:
            return None, None
        return row["agent_id"], row["agent_name"]

def save_customer_agent(customer_id, agent_id, agent_name):
    with db_connect() as conn:
        conn.execute("""
            INSERT INTO customer_agents(customer_id, agent_id, agent_name)
            VALUES(?, ?, ?)
            ON CONFLICT(customer_id) DO UPDATE SET
                agent_id=excluded.agent_id,
                agent_name=excluded.agent_name
        """, (customer_id, agent_id, agent_name))
        conn.commit()

def release_customer_agent_db(customer_id):
    with db_connect() as conn:
        conn.execute(
            "DELETE FROM customer_agents WHERE customer_id = ?",
            (customer_id,)
        )
        conn.commit()

init_db()

# ==================================================
# 定时群发广告配置
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
        "image": "ad1.png"
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
        "image": "ad2.png"
    },
}

ACTIVE_GROUPS = set(GROUP_ADS.keys())

# ============================================================
# 定时群发广告任务
# ============================================================
async def send_scheduled_ads(context: ContextTypes.DEFAULT_TYPE):
    default_ad = next(iter(GROUP_ADS.values()), None)
    if not default_ad:
        logger.warning("没有可用的默认广告配置，跳过本轮群发")
        return

    for row in get_registered_groups():
        chat_id = row["chat_id"]
        data = GROUP_ADS.get(chat_id, default_ad)
        ad_text = data["text"]
        ad_image_name = data.get("image")

        try:
            ad_image_path = os.path.join(BASE_DIR, ad_image_name) if ad_image_name else ""
            if ad_image_path and os.path.exists(ad_image_path):
                with open(ad_image_path, "rb") as photo:
                    await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=photo,
                        caption=ad_text,
                        reply_markup=get_inline_keyboard(),
                    )
            else:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=ad_text,
                    reply_markup=get_inline_keyboard(),
                )
            logger.info("定时广告发送成功 | chat_id=%s", chat_id)
        except Forbidden as e:
            logger.error("机器人已无权访问群组，自动停用 | chat_id=%s | %s", chat_id, e)
            disable_registered_group(chat_id)
        except BadRequest as e:
            logger.error("Telegram 拒绝广告消息 | chat_id=%s | %s", chat_id, e)
        except TelegramError as e:
            log_exception("定时广告发送失败", e, chat_id=chat_id)
        except Exception as e:
            log_exception("定时广告未知异常", e, chat_id=chat_id)


# ============================================================
# Telegram 菜单及按钮
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

async def topic_exists(context: ContextTypes.DEFAULT_TYPE, topic_id):
    return True

async def ensure_customer_topic(context: ContextTypes.DEFAULT_TYPE, user):
    customer_id = user.id
    username = f"@{user.username}" if user.username else "未设置"

    existing_topic_id = get_customer_topic(customer_id)
    if existing_topic_id:
        if await topic_exists(context, existing_topic_id):
            return existing_topic_id

        with db_connect() as conn:
            conn.execute("DELETE FROM customer_topics WHERE customer_id = ?", (customer_id,))
            conn.commit()

    try:
        topic_name = f"👤 {user.full_name}"
        topic = await context.bot.create_forum_topic(
            chat_id=SUPPORT_GROUP_ID,
            name=topic_name
        )

        save_customer_topic(customer_id, topic.message_thread_id)
        
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
        try:
            await context.bot.pin_chat_message(
                chat_id=SUPPORT_GROUP_ID,
                message_id=card_msg.message_id
            )
        except Exception:
            pass
    except Exception as e:
        log_exception("创建客户话题失败", e, chat_id=SUPPORT_GROUP_ID, user_id=customer_id)
        return None
    
    return get_customer_topic(customer_id)


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
            log_exception("同步客户按钮点击到群组失败", e, chat_id=SUPPORT_GROUP_ID, user_id=user.id)


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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "👋 欢迎来到T1体育平台！\n\n"
        "🔥 请直接在对话框发送消息咨询，或点击下方按钮选择您需要体验的服务："
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


async def groupid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.effective_message
    chat = update.effective_chat

    if not user or not message or user.id != ADMIN_ID:
        if message:
            await message.reply_text("❌ 你没有权限使用 /groupid。")
        return

    if not chat or chat.type not in ("group", "supergroup"):
        await message.reply_text("❌ /groupid 只能在群组或超级群组中使用。")
        return

    try:
        bot_member = await context.bot.get_chat_member(
            chat_id=chat.id,
            user_id=context.bot.id
        )
        if bot_member.status not in ("administrator", "creator"):
            await message.reply_text("❌ 机器人必须是本群管理员，才能登记并发送定时广告。")
            return

        save_registered_group(
            chat_id=chat.id,
            chat_title=chat.title or "未命名群组",
            chat_type=chat.type,
            registered_by=user.id,
        )
        ACTIVE_GROUPS.add(chat.id)

        await message.reply_text(
            "✅ 群组登记成功！\n\n"
            f"📌 群组名称：{chat.title or '未命名'}\n"
            f"🆔 Chat ID：{chat.id}\n"
            f"📂 类型：{chat.type}\n\n"
            "⏰ 已加入每小时定时广告任务。"
        )
    except TelegramError as e:
        log_exception("群组登记失败", e, chat_id=chat.id, user_id=user.id)
        await message.reply_text("❌ 群组登记失败，请确认机器人是群管理员并重试。")


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"👤 你的 Telegram 信息\n\n"
        f"姓名：{user.full_name}\n"
        f"用户名：@{user.username if user.username else '未设置'}\n"
        f"Telegram ID：{user.id}"
    )


async def admin_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ 你没有管理员权限。")
        return

    await update.message.reply_text(
        "👑 管理员权限验证成功！\n\n"
        "你现在是这个机器人的管理员。"
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    data = query.data

    if data.startswith("take_agent_") or data.startswith("release_agent_"):
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
            current_agent, current_agent_name = get_customer_agent(customer_id)
            if current_agent and current_agent != user.id:
                await query.answer(f"❌ 该客户已被 【{current_agent_name or '其他客服'}】 抢先接入！", show_alert=True)
                return
            
            save_customer_agent(customer_id, user.id, user.full_name)
            await query.answer(f"✅ 成功接入客户 【{user.full_name}】！", show_alert=True)
            try:
                await query.edit_message_reply_markup(
                    reply_markup=get_support_control_keyboard(customer_id, user.full_name)
                )
            except Exception:
                pass
            
            await context.bot.send_message(
                chat_id=SUPPORT_GROUP_ID,
                message_thread_id=query.message.message_thread_id,
                text=f"🔒 客服 **{user.full_name}** 已成功接入该对话。"
            )

        elif action == "release":
            release_customer_agent_db(customer_id)
            await query.answer("🔓 已成功释放该客户。", show_alert=True)
            try:
                await query.edit_message_reply_markup(
                    reply_markup=get_support_control_keyboard(customer_id)
                )
            except Exception:
                pass

            await context.bot.send_message(
                chat_id=SUPPORT_GROUP_ID,
                message_thread_id=query.message.message_thread_id,
                text="🔓 该客户已被释放。"
            )
        return

    if data == "none":
        await query.answer("ℹ️ 此客户已有管理员正在接待中", show_alert=True)
        return

    await query.answer()

    button_mapping = {
        "register": ("📝 注册平台", "register.png", (
            "🎉 福利已上线，早注册早领取！\n"
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
            "https://jully.pw"
        )),
        "newbie": ("🎁 新人彩金", "newbie.png", "🔥 新人专属福利已开启！首存立享彩金加码 + 包赔护航。"),
        "checkin": ("📅 签到彩金", "checkin.png", "🚀 每日打卡签到，连续签到天数越多，签到彩金越丰厚！"),
        "deposit": ("💰 日存彩金", "deposit.png", "🚀 每日首笔存款满300元即可参与【复存有礼】活动。"),
        "invite": ("👥 推荐好礼", "invite.png", "🎉 分享您的专属邀请链接给好友，共同享受丰厚推荐返利！"),
        "explore": ("🗺 探索秘境", "explore.png", "https://t.me/Avior96Bot\n\n@Avior96Bot"),
    }

    if query.data in button_mapping:
        name, img, text = button_mapping[query.data]
        await notify_customer_action(context, user, name)
        await send_feature_content(query, img, text)


async def handle_private_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    topic_id = await ensure_customer_topic(context, user)
    if not topic_id:
        return

    try:
        await context.bot.copy_message(
            chat_id=SUPPORT_GROUP_ID,
            from_chat_id=user.id,
            message_id=message.message_id,
            message_thread_id=topic_id
        )
    except Exception as e:
        log_exception("转发客户消息失败", e, chat_id=SUPPORT_GROUP_ID, user_id=user.id)


async def delete_notification_callback(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    try:
        await context.bot.delete_message(chat_id=job_data["chat_id"], message_id=job_data["message_id"])
    except Exception:
        pass


async def release_customer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if not message or not user or not chat or chat.id != SUPPORT_GROUP_ID:
        return

    thread_id = message.message_thread_id
    if not thread_id:
        return

    customer_id = get_customer_by_topic(thread_id)
    if customer_id is None:
        return

    release_customer_agent_db(customer_id)
    sent_msg = await message.reply_text("🔓 已成功释放该客户！")
    if context.job_queue:
        context.job_queue.run_once(delete_notification_callback, when=10, data={"chat_id": chat.id, "message_id": sent_msg.message_id})


async def admin_reply_customer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if not message or not user or not chat or chat.id != SUPPORT_GROUP_ID:
        return

    try:
        member = await context.bot.get_chat_member(chat_id=SUPPORT_GROUP_ID, user_id=user.id)
        if member.status not in ("administrator", "creator"):
            return
    except Exception:
        return

    thread_id = message.message_thread_id
    if not thread_id:
        return

    customer_id = get_customer_by_topic(thread_id)
    if customer_id is None:
        return

    assigned_agent, assigned_agent_name = get_customer_agent(customer_id)

    if assigned_agent is None:
        sent_err = await message.reply_text("⚠️ 您尚未接入该客户！请先点击上方名片中的【点击接入接待】按钮。")
        if context.job_queue:
            context.job_queue.run_once(delete_notification_callback, when=10, data={"chat_id": chat.id, "message_id": sent_err.message_id})
        return

    if assigned_agent != user.id:
        return

    try:
        await context.bot.copy_message(
            chat_id=customer_id,
            from_chat_id=SUPPORT_GROUP_ID,
            message_id=message.message_id,
        )
        sent_msg = await message.reply_text("✅ 已发送给客户。")
        if context.job_queue:
            context.job_queue.run_once(delete_notification_callback, when=10, data={"chat_id": chat.id, "message_id": sent_msg.message_id})
    except Exception as e:
        log_exception("客服回复异常", e, chat_id=customer_id, user_id=user.id)


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
    server.serve_forever()


# ============================================================
# 自动抓取篮球赛事与推荐任务（已去重、已固定推荐队伍）
# ============================================================
async def send_basketball_recommendations(context: ContextTypes.DEFAULT_TYPE):
    """自动抓取今日篮球赛程，固定推荐队伍，并自动去除重复赛事"""
    api_key = "285aff303f99ed1463eac87da1e8bad9" 
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    url = "https://v1.basketball.api-sports.io/games"
    headers = {
        "x-apisports-key": api_key
    }
    params = {
        "date": today_str
    }

    match_lines = []
    seen_matches = set()  # 👈 用于记录已经添加过的赛事，防止重复

    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        data = response.json()
        
        matches = data.get("response", [])
        
        if matches:
            for match in matches:
                home_team = match['teams']['home']['name']
                away_team = match['teams']['away']['name']
                league_name = match['league']['name']
                
                # 唯一标识这场比赛（比如：湖人 vs 勇士）
                match_key = f"{home_team}-{away_team}"
                if match_key in seen_matches:
                    continue  # 如果已经有了，直接跳过（去重）
                
                seen_matches.add(match_key)
                
                game_time_utc = match['date']
                time_str = game_time_utc[11:16] if len(game_time_utc) >= 16 else "待定"
                
                # 🛑 核心修改：利用比赛名字的哈希值固定推荐队伍，不再随机乱变！
                # 这样只要是对阵这两支球队，每次推出来的固定是同一边
                team_choice_seed = sum(ord(c) for c in match_key)
                recommended_team = home_team if team_choice_seed % 2 == 0 else away_team
                
                match_block = (
                    f"⏰ {time_str} | 🏀 {league_name}\n"
                    f"🔹 {home_team} vs {away_team}\n"
                    f"推荐：{recommended_team}"
                )
                match_lines.append(match_block)
                
                # 限制最多显示 3 场不重复的赛事
                if len(match_lines) >= 3:
                    break
                    
        if not match_lines:
            match_lines.append("今日暂无安排热门篮球赛事。")
            
    except Exception as e:
        logger.error(f"抓取篮球数据失败: {e}")
        match_lines.append("获取今日篮球赛程异常，请稍后查看。")

    recommendation_text = (
        "🏀 【今日篮球赛事自动播报】 🏀\n"
        "----------------------------------\n" +
        "\n\n".join(match_lines) +
        "\n----------------------------------\n"
        "📊 更多精彩盘口与实时比分，请点击下方按钮进入平台查看！"
    )

    for row in get_registered_groups():
        chat_id = row["chat_id"]
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=recommendation_text,
                reply_markup=get_inline_keyboard()
            )
            logger.info("篮球赛事自动推荐发送成功 | chat_id=%s", chat_id)
        except Exception as e:
            logger.error("篮球赛事自动推荐发送失败 | chat_id=%s | error=%s", chat_id, e)


# ==================================================
# 主程序
# ==================================================
def main():
    init_db()

    app = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .post_init(setup_bot_commands)
        .build()
    )

    if app.job_queue:
        from apscheduler.triggers.cron import CronTrigger
        
        # 1. 每小时发送一次的广告任务
        app.job_queue.run_repeating(
            send_scheduled_ads,
            interval=3600,
            first=60
        )
        
        # 2. 修改后：每天从 12:00 开始，每隔 2 小时自动推送一次篮球赛事（12点、14点、16点……）
        app.job_queue.run_repeating(
            send_basketball_recommendations,
            interval=CronTrigger(hour="12-22/2", minute=0),
            first=30
        )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("admin", admin_test))
    app.add_handler(CommandHandler("groupid", groupid))
    app.add_handler(CommandHandler("release", release_customer))
    
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, handle_private_message))
    app.add_handler(MessageHandler(filters.Chat(SUPPORT_GROUP_ID) & ~filters.COMMAND, admin_reply_customer))

    print("🤖 AvGood Bot 已启动...")

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
