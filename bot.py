import os
import re
import sqlite3
import logging
import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from http.server import BaseHTTPRequestHandler, HTTPServer
import json

import httpx

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
# 客服群 ID
# ==================================================
SUPPORT_GROUP_ID = -1003749620184

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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS basketball_cache (
                cache_key TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                updated_at TEXT NOT NULL
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


def get_db_cache(cache_key: str):
    """从数据库账本里查缓存"""
    with db_connect() as conn:
        row = conn.execute(
            "SELECT data, updated_at FROM basketball_cache WHERE cache_key = ?",
            (cache_key,)
        ).fetchone()
        
        if not row:
            return None
        
        try:
            cached_at = datetime.fromisoformat(row["updated_at"])
            if cached_at.tzinfo is None:
                cached_at = cached_at.replace(tzinfo=timezone.utc)
            
            cache_age = (china_now() - cached_at).total_seconds()
            if cache_age < BASKETBALL_CACHE_TTL:
                return json.loads(row["data"])
        except Exception:
            pass
            
    return None

def set_db_cache(cache_key: str, data: list):
    """把数据保存到数据库账本里"""
    try:
        now_str = china_now().isoformat()
        data_str = json.dumps(data, ensure_ascii=False, default=str)
        with db_connect() as conn:
            conn.execute("""
                INSERT INTO basketball_cache(cache_key, data, updated_at)
                VALUES(?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    data = excluded.data,
                    updated_at = excluded.updated_at
            """, (cache_key, data_str, now_str))
            conn.commit()
    except Exception as e:
        logger.error(f"写入篮球数据库缓存失败 | key={cache_key} | error={e}")

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
    print("🚨 【测试日志】定时广告任务被触发了！")
    
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
    bot_username = "Flyoo6bot" 
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📝 注册平台", url=f"https://t.me/{bot_username}?start=register"),
            InlineKeyboardButton("🎁 新人彩金", url=f"https://t.me/{bot_username}?start=newbie")
        ],
        [
            InlineKeyboardButton("📅 签到彩金", url=f"https://t.me/{bot_username}?start=checkin"),
            InlineKeyboardButton("💰 日存彩金", url=f"https://t.me/{bot_username}?start=deposit")
        ],
        [
            InlineKeyboardButton("👥 推荐好礼", url=f"https://t.me/{bot_username}?start=invite"),
            InlineKeyboardButton("🗺 探索秘境", url=f"https://t.me/{bot_username}?start=explore")
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
    user = update.effective_user
    chat = update.effective_chat
    args = context.args  

    if chat.type == "private" and args:
        param = args[0]
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

        if param in button_mapping:
            name, img, text = button_mapping[param]
            await notify_customer_action(context, user, name)
            await send_feature_content(update, img, text)
            return

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
    
    if chat.type == "private":
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

    if data in button_mapping:
        name, img, text = button_mapping[data]
        await notify_customer_action(context, user, name)
        bot_username = "Flyoo6bot"
        
        try:
            image_path = os.path.join(BASE_DIR, img)
            if os.path.exists(image_path):
                with open(image_path, "rb") as photo:
                    await context.bot.send_photo(
                        chat_id=user.id,
                        photo=photo,
                        caption=text,
                        reply_markup=get_inline_keyboard()
                    )
            else:
                await context.bot.send_message(
                    chat_id=user.id,
                    text=text,
                    reply_markup=get_inline_keyboard()
                )
            await query.answer("✅ 已成功私发给您，请注意查收！", show_alert=True)
        except (Forbidden, TelegramError):
            await query.answer(
                f"❌ 发送失败！请先点击 @{bot_username} 给机器人发送一条消息，然后再来群里点按钮。",
                show_alert=True
            )

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

    # 1. 检查用户点击的是不是底部固定菜单按钮的文本
    text_to_feature = {
        "📝 注册平台": ("register", "register.png", (
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
        "🎁 新人彩金": ("newbie", "newbie.png", "🔥 新人专属福利已开启！首存立享彩金加码 + 包赔护航。"),
        "📅 签到彩金": ("checkin", "checkin.png", "🚀 每日打卡签到，连续签到天数越多，签到彩金越丰厚！"),
        "💰 日存彩金": ("deposit", "deposit.png", "🚀 每日首笔存款满300元即可参与【复存有礼】活动。"),
        "👥 推荐好礼": ("invite", "invite.png", "🎉 分享您的专属邀请链接给好友，共同享受丰厚推荐返利！"),
        "🗺 探索秘境": ("explore", "explore.png", "https://t.me/Avior96Bot\n\n@Avior96Bot"),
    }

    if message.text in text_to_feature:
        name, img, text = text_to_feature[message.text]
        await notify_customer_action(context, user, name)
        await send_feature_content(update, img, text)
        return

    # 2. 如果不是菜单按钮，则是普通咨询，转发给客服群
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
        # 如果报错是因为话题找不到（被手动删了）
        if "Message thread not found" in str(e):
            # 从数据库中删掉这个失效的旧话题记录
            with db_connect() as conn:
                conn.execute("DELETE FROM customer_topics WHERE customer_id = ?", (user.id,))
                conn.commit()
            
            # 重新获取/创建一个新话题并发送
            new_topic_id = await ensure_customer_topic(context, user)
            if new_topic_id:
                try:
                    await context.bot.copy_message(
                        chat_id=SUPPORT_GROUP_ID,
                        from_chat_id=user.id,
                        message_id=message.message_id,
                        message_thread_id=new_topic_id
                    )
                    return
                except Exception as inner_e:
                    log_exception("重试转发客户消息失败", inner_e, chat_id=SUPPORT_GROUP_ID, user_id=user.id)
        else:
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

# 1. 如果该客户还没有任何管理员接单
    if assigned_agent is None:
        try:
            sent_err = await chat.send_message(
                "⚠️ 您尚未接入该客户！请先点击上方名片中的【点击接入接待】按钮。",
                message_thread_id=thread_id
            )
            if context.job_queue:
                context.job_queue.run_once(delete_notification_callback, when=10, data={"chat_id": chat.id, "message_id": sent_err.message_id})
        except Exception:
            pass
        return

    # 2. 如果已被其他管理员接单，而当前说话的人不是接单人 -> 拦截并提示
    if assigned_agent != user.id:
        try:
            await message.delete()  # 删掉越权发送的消息
        except Exception:
            pass
            
        try:
            sent_err = await chat.send_message(
                f"⚠️ 提示：当前客户正由【{assigned_agent_name}】接待中，如需强行接单或转交请先点击上方【释放/转交客户】按钮！",
                message_thread_id=thread_id
            )
            if context.job_queue:
                context.job_queue.run_once(delete_notification_callback, when=10, data={"chat_id": chat.id, "message_id": sent_err.message_id})
        except Exception:
            pass
        return

    try:
        await context.bot.copy_message(
            chat_id=customer_id,
            from_chat_id=SUPPORT_GROUP_ID,
            message_id=message.message_id,
        )
        sent_msg = await chat.send_message("✅ 已发送给客户。", message_thread_id=thread_id)
        if context.job_queue:
            context.job_queue.run_once(delete_notification_callback, when=10, data={"chat_id": chat.id, "message_id": sent_msg.message_id})
    except Exception as e:
        print(f"转发消息出错: {e}")
    
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

# ==================================================
# 超全球队中英文对照字典（含 NBA、欧洲欧冠豪门、国际国家队）
# ==================================================
TEAM_NAME_ZH = {
    # --- 常见测试与东南亚队伍 ---
    "Binan Tatak Gel": "比南塔塔克",
    "San Juan Knights": "圣胡安骑士",
    "Nhatrang Dolphins": "芽庄海豚",
    "Da Nang Dragons": "岘港龙",

    # --- NBA 东部联盟 (15支) ---
    "Boston Celtics": "波士顿凯尔特人",
    "Brooklyn Nets": "布鲁克林篮网",
    "New York Knicks": "纽约尼克斯",
    "Philadelphia 76ers": "费城76人",
    "Toronto Raptors": "多伦多猛龙",
    "Chicago Bulls": "芝加哥公牛",
    "Cleveland Cavaliers": "克利夫兰骑士",
    "Detroit Pistons": "底特律活塞",
    "Indiana Pacers": "印第安纳步行者",
    "Milwaukee Bucks": "密尔沃基雄鹿",
    "Atlanta Hawks": "亚特兰大老鹰",
    "Charlotte Hornets": "夏洛特黄蜂",
    "Miami Heat": "迈阿密热火",
    "Orlando Magic": "奥兰多魔术",
    "Washington Wizards": "华盛顿奇才",

    # --- NBA 西部联盟 (15支) ---
    "Denver Nuggets": "丹佛掘金",
    "Minnesota Timberwolves": "明尼苏达森林狼",
    "Oklahoma City Thunder": "俄克拉荷马城雷霆",
    "Portland Trail Blazers": "波特兰开拓者",
    "Utah Jazz": "犹他爵士",
    "Golden State Warriors": "金州勇士",
    "Los Angeles Clippers": "洛杉矶快船",
    "Los Angeles Lakers": "洛杉矶湖人",
    "Phoenix Suns": "菲尼克斯太阳",
    "Sacramento Kings": "萨克拉门托国王",
    "Dallas Mavericks": "达拉斯独行侠",
    "Houston Rockets": "休斯顿火箭",
    "Memphis Grizzlies": "孟菲斯灰熊",
    "New Orleans Pelicans": "新奥尔良鹈鹕",
    "San Antonio Spurs": "圣安东尼奥马刺",

    # --- 欧洲篮球联赛 (EuroLeague 常见豪门) ---
    "Real Madrid": "皇家马德里",
    "FC Barcelona": "巴塞罗那",
    "Anadolu Efes": "安纳托利亚艾菲斯",
    "Anadolu Efes Istanbul": "伊斯坦布尔艾菲斯",
    "Fenerbahce": "费内巴切",
    "Fenerbahce Beko Istanbul": "费内巴切",
    "Olympiacos": "奥林匹亚科斯",
    "Olympiacos Piraeus": "奥林匹亚科斯",
    "Panathinaikos": "帕纳辛纳科斯",
    "Panathinaikos AKTOR Athens": "帕纳辛纳科斯",
    "Monaco": "摩纳哥",
    "AS Monaco": "摩纳哥",
    "FC Bayern Munich": "拜仁慕尼黑",
    "Armani Olimpia Milan": "米兰阿玛尼",
    "Virtus Bologna": "博洛尼亚维图斯",
    "Crvena Zvezda": "贝尔格莱德红星",
    "Crvena Zvezda Meridianbet Belgrade": "贝尔格莱德红星",
    "Partizan": "贝尔格莱德游击",
    "Partizan Mozzart Bet Belgrade": "贝尔格莱德游击",
    "Maccabi Tel Aviv": "特拉维夫马卡比",
    "Baskonia": "巴斯克尼亚",
    "Kosner Baskonia Vitoria-Gasteiz": "巴斯克尼亚",
    "Zalgiris Kaunas": "考纳斯扎尔吉里斯",
    "ALBA Berlin": "柏林阿尔巴",
    "Paris Basketball": "巴黎篮球",

    # --- 常见国家队 ---
    "China": "中国",
    "USA": "美国",
    "Spain": "西班牙",
    "France": "法国",
    "Serbia": "塞尔维亚",
    "Australia": "澳大利亚",
    "Canada": "加拿大",
    "Germany": "德国",
    "Turkey": "土耳其",
    "Czech Republic": "捷克",
    "Greece": "希腊",
    "Italy": "意大利",
    "Lithuania": "立陶宛",
    "Argentina": "阿根廷",
    "Brazil": "巴西",
    "Japan": "日本",
    "South Korea": "韩国",
    "Philippines": "菲律宾",
}

def translate_team(english_name):
    if not english_name:
        return "未知球队"
    return TEAM_NAME_ZH.get(english_name.strip(), english_name)

# ============================================================
# 篮球赛事配置与抓取
# ============================================================
BASKETBALL_API_URL = "https://v1.basketball.api-sports.io"
BASKETBALL_API_KEY = os.environ.get("BASKETBALL_API_KEY", "").strip()
CHINA_TZ = ZoneInfo("Asia/Shanghai")

BASKETBALL_TOP_N = 2
BASKETBALL_HTTP_TIMEOUT = 15.0
BASKETBALL_MIN_RECENT_GAMES = 3
BASKETBALL_CACHE_TTL = 6 * 60 * 60

BASKETBALL_TEAM_CACHE = {}
BASKETBALL_H2H_CACHE = {}

BASKETBALL_FINISHED_STATUSES = {
    "FT", "AOT", "CANC", "ABD", "AWD", "WO", "POST", "PST", "LIVE", "Q1",
    "Q2", "Q3", "Q4", "OT", "HT", "INT", "BT", "SUSP"
}

def china_now():
    return datetime.now(CHINA_TZ)

def parse_api_datetime(value):
    if not value:
        return None
    raw = str(value).strip()
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = datetime.strptime(raw[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(CHINA_TZ)

def normalize_game_status(game):
    status = game.get("status") or {}
    return str(status.get("short") or status.get("long") or "").upper().strip()

def is_future_game(game, now=None):
    now = now or china_now()
    game_dt = parse_api_datetime(game.get("date"))
    if not game_dt:
        return False
    status = normalize_game_status(game)
    if status in BASKETBALL_FINISHED_STATUSES:
        return False
    return game_dt > now

def get_team_info(game, side):
    teams = game.get("teams") or {}
    team = teams.get(side) or {}
    return team.get("id"), team.get("name") or "未知球队"

async def basketball_api_get(client, endpoint, params):
    if not BASKETBALL_API_KEY:
        raise RuntimeError("未配置 BASKETBALL_API_KEY 环境变量")
    url = f"{BASKETBALL_API_URL}{endpoint}"
    headers = {"x-apisports-key": BASKETBALL_API_KEY}
    response = await client.get(url, headers=headers, params=params)
    if response.status_code == 429:
        raise RuntimeError("篮球 API 请求过于频繁（429）")
    response.raise_for_status()
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("篮球 API 返回内容不是有效 JSON") from exc
    errors = payload.get("errors")
    if errors:
        raise RuntimeError(f"篮球 API 返回错误：{errors}")
    return payload.get("response") or []

async def fetch_today_games(client):
    today = china_now().date().isoformat()
    games = await basketball_api_get(client, "/games", {"date": today})
    now = china_now()
    selected = []
    seen = set()

    for game in games:
        game_id = game.get("id")
        home_id, home_name = get_team_info(game, "home")
        away_id, away_name = get_team_info(game, "away")

        if not home_id or not away_id:
            continue
        if not is_future_game(game, now):
            continue

        key = game_id or (home_id, away_id, game.get("date"))
        if key in seen:
            continue
        seen.add(key)

        game["_home_id"] = home_id
        game["_away_id"] = away_id
        game["_home_name"] = home_name
        game["_away_name"] = away_name
        game["_china_datetime"] = parse_api_datetime(game.get("date"))
        selected.append(game)

    selected.sort(key=lambda item: item["_china_datetime"])
    return selected

def extract_game_result(game, team_id):
    teams = game.get("teams") or {}
    scores = game.get("scores") or {}
    home = teams.get("home") or {}
    away = teams.get("away") or {}
    home_score = (scores.get("home") or {}).get("total")
    away_score = (scores.get("away") or {}).get("total")

    if home_score is None or away_score is None:
        return None
    try:
        home_score = float(home_score)
        away_score = float(away_score)
    except (TypeError, ValueError):
        return None

    if team_id == home.get("id"):
        points_for, points_against = home_score, away_score
    elif team_id == away.get("id"):
        points_for, points_against = away_score, home_score
    else:
        return None

    result = "W" if points_for > points_against else ("L" if points_for < points_against else "D")
    return {
        "result": result,
        "points_for": points_for,
        "points_against": points_against,
        "home_id": home.get("id"),
        "away_id": away.get("id"),
    }

async def fetch_team_recent_games(client, team_id):
    cache_key = f"team_recent_{team_id}"
    cached_data = get_db_cache(cache_key)
    if cached_data:
        for item in cached_data:
            if isinstance(item.get("date"), str):
                item["date"] = datetime.fromisoformat(item["date"])
        return cached_data

    try:
        games = await basketball_api_get(client, "/games", {"team": team_id})
    except Exception as exc:
        logger.warning("获取球队近期比赛失败 | team_id=%s | %s", team_id, exc)
        return []

    completed = []
    now = china_now()
    for game in games:
        game_dt = parse_api_datetime(game.get("date"))
        if not game_dt or game_dt >= now:
            continue
        result = extract_game_result(game, team_id)
        if not result:
            continue
        result["date"] = game_dt
        completed.append(result)

    completed.sort(key=lambda item: item["date"], reverse=True)
    completed = completed[:5]
    set_db_cache(cache_key, completed)
    return completed

async def fetch_head_to_head(client, home_id, away_id):
    cache_key = tuple(sorted((home_id, away_id)))
    db_key = f"h2h_{home_id}_{away_id}"
    cached_data = get_db_cache(db_key)
    if cached_data:
        for item in cached_data:
            if isinstance(item.get("date"), str):
                item["date"] = datetime.fromisoformat(item["date"])
        return cached_data

    try:
        games = await basketball_api_get(client, "/games", {"h2h": f"{home_id}-{away_id}"})
    except Exception as exc:
        logger.warning("获取 H2H 失败 | home=%s | away=%s | %s", home_id, away_id, exc)
        return []

    completed = []
    now = china_now()
    for game in games:
        game_dt = parse_api_datetime(game.get("date"))
        if not game_dt or game_dt >= now:
            continue
        home = (game.get("teams") or {}).get("home") or {}
        scores = game.get("scores") or {}
        home_score = (scores.get("home") or {}).get("total")
        away_score = (scores.get("away") or {}).get("total")
        if home_score is None or away_score is None:
            continue
        try:
            home_score, away_score = float(home_score), float(away_score)
        except (TypeError, ValueError):
            continue
        if home_score == away_score:
            continue
        winner = home.get("id") if home_score > away_score else away.get("id")
        completed.append({"date": game_dt, "winner": winner})

    completed.sort(key=lambda item: item["date"], reverse=True)
    completed = completed[:5]
    set_db_cache(db_key, completed)
    return completed

def summarize_recent(games):
    if not games:
        return {"wins": 0, "losses": 0, "win_rate": 0.0, "avg_points": 0.0, "avg_allowed": 0.0}
    wins = sum(1 for item in games if item["result"] == "W")
    total = len(games)
    avg_points = sum(item["points_for"] for item in games) / total
    avg_allowed = sum(item["points_against"] for item in games) / total
    return {
        "wins": wins,
        "losses": total - wins,
        "win_rate": wins / total * 100,
        "avg_points": avg_points,
        "avg_allowed": avg_allowed,
    }

def home_away_summary(games, team_id, want_home):
    filtered = [item for item in games if (item.get("home_id") == team_id) == want_home]
    return summarize_recent(filtered[:5])

def calculate_recommendation(home, away, home_recent, away_recent, h2h):
    home_sum = summarize_recent(home_recent)
    away_sum = summarize_recent(away_recent)
    home_score, away_score = 0.0, 0.0

    home_score += home_sum["win_rate"] * 0.45
    away_score += away_sum["win_rate"] * 0.45

    max_points = max(home_sum["avg_points"], away_sum["avg_points"], 1.0)
    home_score += home_sum["avg_points"] / max_points * 100 * 0.35
    away_score += away_sum["avg_points"] / max_points * 100 * 0.35

    home_ha = home_away_summary(home_recent, home["id"], True)
    away_ha = home_away_summary(away_recent, away["id"], False)
    home_score += home_ha["win_rate"] * 0.10
    away_score += away_ha["win_rate"] * 0.10

    if h2h:
        home_h2h_wins = sum(1 for item in h2h if item["winner"] == home["id"])
        away_h2h_wins = sum(1 for item in h2h if item["winner"] == away["id"])
        total_h2h = home_h2h_wins + away_h2h_wins
        if total_h2h:
            home_score += home_h2h_wins / total_h2h * 100 * 0.10
            away_score += away_h2h_wins / total_h2h * 100 * 0.10

    if home_score >= away_score:
        return home["name"], home_score, away_score
    return away["name"], home_score, away_score

def format_percent(value):
    return f"{value:.0f}"

def format_points(value):
    return f"{value:.1f}"

async def analyze_game(client, game):
    home_id, away_id = game["_home_id"], game["_away_id"]
    home = {"id": home_id, "name": translate_team(game["_home_name"])}
    away = {"id": away_id, "name": translate_team(game["_away_name"])}

    home_recent, away_recent, h2h = await asyncio.gather(
        fetch_team_recent_games(client, home_id),
        fetch_team_recent_games(client, away_id),
        fetch_head_to_head(client, home_id, away_id)
    )

    if len(home_recent) < BASKETBALL_MIN_RECENT_GAMES or len(away_recent) < BASKETBALL_MIN_RECENT_GAMES:
        return None

    recommendation, home_score, away_score = calculate_recommendation(home, away, home_recent, away_recent, h2h)
    if not recommendation:
        return None

    home_summary = summarize_recent(home_recent)
    away_summary = summarize_recent(away_recent)
    home_ha = home_away_summary(home_recent, home["id"], True)
    away_ha = home_away_summary(away_recent, away["id"], False)

    return {
        "time": game["_china_datetime"].strftime("%H:%M"),
        "home": home["name"],
        "away": away["name"],
        "recommendation": recommendation,
        "home_recent_count": len(home_recent),
        "away_recent_count": len(away_recent),
        "home_wins": home_summary["wins"],
        "home_losses": home_summary["losses"],
        "away_wins": away_summary["wins"],
        "away_losses": away_summary["losses"],
        "home_win_rate": home_summary["win_rate"],
        "away_win_rate": away_summary["win_rate"],
        "home_avg_points": home_summary["avg_points"],
        "away_avg_points": away_summary["avg_points"],
        "home_ha_win_rate": home_ha["win_rate"],
        "away_ha_win_rate": away_ha["win_rate"],
        "h2h_count": len(h2h),
        "home_score": home_score,
        "away_score": away_score,
    }

def format_basketball_message(analyses):
    if not analyses:
        return "🏀 今日篮球赛事精选\n\n暂无符合数据条件赛事。"

    blocks = ["🏀 今日篮球赛事精选"]
    for item in analyses[:BASKETBALL_TOP_N]:
        home_form = f"{item['home_wins']}胜{item['home_losses']}负"
        away_form = f"{item['away_wins']}胜{item['away_losses']}负"

        if item["home_avg_points"] > item["away_avg_points"]:
            attack_text = f"{item['home']}场均得分 {format_points(item['home_avg_points'])}，进攻略占优势。"
        elif item["away_avg_points"] > item["home_avg_points"]:
            attack_text = f"{item['away']}场均得分 {format_points(item['away_avg_points'])}，进攻略占优势。"
        else:
            attack_text = "双方场均得分接近，进攻差距较小。"

        blocks.append(
            f"⏰ 比赛时间：{item['time']}\n"
            f"🔹 比赛队伍：{item['home']} vs {item['away']}\n"
            f"🎯 球队推荐：{item['recommendation']}\n"
            f"📊 近况参考：\n"
            f"🔥 {item['home']}：近{item['home_recent_count']}场 {home_form}，胜率 {format_percent(item['home_win_rate'])}%\n"
            f"🔥 {item['away']}：近{item['away_recent_count']}场 {away_form}，胜率 {format_percent(item['away_win_rate'])}%\n"
            f"🔥 进攻表现：{attack_text}\n"
            "💡 综合参考：近期战绩、进攻表现为主，主客场与交手为辅。\n"
            "⚠️ 以上为赛事数据参考，不代表比赛结果。"
        )
    return "\n\n".join(blocks)

async def test_basketball_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or user.id != ADMIN_ID:
        await update.message.reply_text("❌ 你没有权限执行此操作。")
        return

    await update.message.reply_text("🔄 正在手动获取篮球赛事并生成测试消息，请稍候...")
    if not BASKETBALL_API_KEY:
        await update.message.reply_text("❌ 错误：未配置 BASKETBALL_API_KEY 环境变量。")
        return

    try:
        async with httpx.AsyncClient(timeout=BASKETBALL_HTTP_TIMEOUT) as client:
            games = await fetch_today_games(client)
            if not games:
                message_text = "🏀 今日篮球赛事数据分析\n\n今日暂无符合条件的未开赛篮球比赛。"
            else:
                games = games[:3]
                tasks = [analyze_game(client, game) for game in games]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                analyses = [res for res in results if isinstance(res, dict)]
                message_text = format_basketball_message(analyses)

        await update.message.reply_text(text=message_text, reply_markup=get_inline_keyboard())
    except Exception as exc:
        logger.exception("手动触发篮球测试异常：%s", exc)
        await update.message.reply_text(f"❌ 测试发送失败，发生异常：{exc}")


# ============================================================
# 时间段精准控制逻辑
# ============================================================
def is_allowed_time():
    """判断当前时间是否在发送窗口：08:00 以及 14:00 到次日 04:00 的每 2 小时"""
    now = china_now()
    hour = now.hour
    minute = now.minute
    allowed_hours = [8, 14, 16, 18, 20, 22, 0, 2, 4]
    return hour in allowed_hours and 0 <= minute <= 5

async def basketball_scheduler_task(context: ContextTypes.DEFAULT_TYPE):
    """每小时被唤醒一次，检查时间是否符合，符合则执行"""
    if is_allowed_time():
        logger.info("达到预定发送时间，开始执行篮球推荐任务...")
        await send_basketball_recommendations(context)
    else:
        logger.info("当前时间不在发送窗口，跳过篮球推荐任务。")


async def send_basketball_recommendations(context: ContextTypes.DEFAULT_TYPE):
    if not BASKETBALL_API_KEY:
        logger.error("篮球任务未执行：缺少 BASKETBALL_API_KEY 环境变量")
        return

    try:
        async with httpx.AsyncClient(timeout=BASKETBALL_HTTP_TIMEOUT) as client:
            games = await fetch_today_games(client)

            if not games:
                message_text = "🏀 今日篮球赛事数据分析\n\n今日暂无符合条件的未开赛篮球比赛。"
            else:
                games = games[:3]
                tasks = [analyze_game(client, game) for game in games]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                analyses = [res for res in results if isinstance(res, dict)]
                message_text = format_basketball_message(analyses)

        for row in get_registered_groups():
            chat_id = row["chat_id"]
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=message_text,
                    reply_markup=get_inline_keyboard(),
                )
                logger.info("篮球赛事数据分析发送成功 | chat_id=%s", chat_id)
            except Forbidden:
                disable_registered_group(chat_id)
            except TelegramError as exc:
                log_exception("篮球赛事数据分析发送失败", exc, chat_id=chat_id)
            except Exception as exc:
                log_exception("篮球赛事数据分析未知异常", exc, chat_id=chat_id)

    except Exception as exc:
        logger.exception("篮球赛事任务异常：%s", exc)


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
        # 1. 广告任务（每小时一次）
        app.job_queue.run_repeating(
            send_scheduled_ads,
            interval=3600,
            first=3600
        )
        
        # 2. 篮球推荐调度任务（每小时检查一次时间段）
        app.job_queue.run_repeating(
            basketball_scheduler_task,
            interval=3600,
            first=30
        )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("admin", admin_test))
    app.add_handler(CommandHandler("groupid", groupid))
    app.add_handler(CommandHandler("test_basketball", test_basketball_manual))
    app.add_handler(CommandHandler("release", release_customer))

    app.add_handler(CommandHandler("register", start))
    app.add_handler(CommandHandler("newbie", start))
    app.add_handler(CommandHandler("checkin", start))
    app.add_handler(CommandHandler("deposit", start))
    app.add_handler(CommandHandler("invite", start))
    app.add_handler(CommandHandler("explore", start))
    
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
