import os
import re
import sqlite3
import logging
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
# Render 如果要在重启/重新部署后保留客服数据，请配置 Persistent Disk，并把 DB_PATH
# 指向 Render Persistent Disk，例如 /var/data/bot_data.db。
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
        "image": "ad1.png"  # 👈 确保这行和上面的 "text" 缩进对齐
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
        "image": "ad2.png"  # 👈 这行同样需要和上面的 "text" 缩进对齐
    },
}

ACTIVE_GROUPS = set(GROUP_ADS.keys())

# ============================================================
# 定时群发广告任务（图文完全独立版）
# ============================================================
async def send_scheduled_ads(context: ContextTypes.DEFAULT_TYPE):
    """每小时向已通过 /groupid 登记的群发送广告。"""
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
# 客服话题健康检查
# ==================================================
async def topic_exists(context: ContextTypes.DEFAULT_TYPE, topic_id):
    return True


# ==================================================
# 核心公共函数：确保客户私聊时在群里有专属话题
# ==================================================
async def ensure_customer_topic(context: ContextTypes.DEFAULT_TYPE, user):
    customer_id = user.id
    username = f"@{user.username}" if user.username else "未设置"

    existing_topic_id = get_customer_topic(customer_id)
    if existing_topic_id:
        if await topic_exists(context, existing_topic_id):
            return existing_topic_id

        logger.info(
            "检测到旧客服话题已删除，自动重建 | customer_id=%s | old_topic_id=%s",
            customer_id, existing_topic_id
        )
        with db_connect() as conn:
            conn.execute(
                "DELETE FROM customer_topics WHERE customer_id = ?",
                (customer_id,)
            )
            conn.commit()

    try:
        topic_name = f"👤 {user.full_name}"
        topic = await context.bot.create_forum_topic(
            chat_id=SUPPORT_GROUP_ID,
            name=topic_name
        )

        save_customer_topic(customer_id, topic.message_thread_id)
        
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
        log_exception("创建客户话题失败", e, chat_id=SUPPORT_GROUP_ID, user_id=customer_id)
        return None
    
    return get_customer_topic(customer_id)


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
            log_exception("同步客户按钮点击到群组失败", e, chat_id=SUPPORT_GROUP_ID, user_id=user.id)


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

# ==================================================
# 获取当前群组 ID
# ==================================================
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
        logger.info("群组登记成功 | chat_id=%s | title=%s | registered_by=%s",
                    chat.id, chat.title, user.id)

    except TelegramError as e:
        log_exception("群组登记失败", e, chat_id=chat.id, user_id=user.id)
        await message.reply_text("❌ 群组登记失败，请确认机器人是群管理员并重试。")
    except Exception as e:
        log_exception("群组登记未知异常", e, chat_id=chat.id, user_id=user.id)
        await message.reply_text("❌ 群组登记出现异常，请稍后重试。")


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
            current_agent, current_agent_name = get_customer_agent(customer_id)
            if current_agent and current_agent != user.id:
                await query.answer(f"❌ 该客户已被 【{current_agent_name or '其他客服'}】 抢先接入！", show_alert=True)
                return
            
            # 成功接入
            save_customer_agent(customer_id, user.id, user.full_name)
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
            current_agent, _ = get_customer_agent(customer_id)
            if current_agent != user.id:
                try:
                    member = await context.bot.get_chat_member(chat_id=SUPPORT_GROUP_ID, user_id=user.id)
                    if member.status not in ("administrator", "creator"):
                        await query.answer("❌ 只有当前接待该客服或超级管理员才能释放！", show_alert=True)
                        return
                except Exception:
                    await query.answer("❌ 无权操作", show_alert=True)
                    return

            release_customer_agent_db(customer_id)
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
            "https://jully.pw\n\n"
            "注册完成后私讯我，即可领取专属福利礼包🎁"
        )),
        "newbie": ("🎁 新人彩金", "newbie.png", (
            "🔥 新人专属福利已开启！\n\n"
            "首存立享彩金加码 + 包赔护航，更有内部群精选推荐、竞猜互动活动等你参与！\n"
            "超多隐藏福利持续解锁中"
        )),
        "checkin": ("📅 签到彩金", "checkin.png", (
            "🚀 签到就能领，错过就是少拿！\n\n"
            "每日打卡签到，连续签到天数越多，签到彩金越丰厚！🎁\n\n"
            "⏰ 每月1日重新累计，越早参与越划算！\n\n"
            "回复：签到\n"
            "即可马上为你申请福利"
        )),
        "deposit": ("💰 日存彩金", "deposit.png", (
            "🚀 今天的福利别漏领！\n\n"
            "每日首笔存款满300元即可参与【复存有礼】活动，额外礼金直接安排！\n"
            "每天仅限领取一次，越早参与越划算！\n\n"
            "回复：每日首存\n"
            "马上为你申请，无需额外操作🎁"
        )),
        "invite": ("👥 推荐好礼", "invite.png", (
            "🎉 输赢是比赛的一部分，福利才是真正不能错过的惊喜！\n\n"
            "分享您的专属邀请链接给好友，共同享受丰厚推荐返利与好礼！\n\n"
            "想了解活动详情或领取专属福利，欢迎随时私讯我，在线为你解答～ 🚀❤️"
        )),
        "explore": ("🗺 探索秘境", "explore.png", (
            "欢迎来到秘境探索频道，点击开启您的奇妙旅程：\n"
              "（这个功能尚未完善，将在本月底优化完成并上架）\n"          
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
        # 使用 copy_message，统一支持文字、图片、语音、视频、文件、音频、
        # 位置、联系人、GIF/动画、贴纸、视频消息等 Telegram 消息类型。
        await context.bot.copy_message(
            chat_id=SUPPORT_GROUP_ID,
            from_chat_id=user.id,
            message_id=message.message_id,
            message_thread_id=topic_id
        )
        logger.info(
            "客户消息已转入客服话题 | customer_id=%s | topic_id=%s | message_id=%s",
            user.id, topic_id, message.message_id
        )
    except TelegramError as e:
        log_exception("转发客户消息到客服群失败", e,
                      chat_id=SUPPORT_GROUP_ID, user_id=user.id)
        try:
            await message.reply_text("⚠️ 当前客服系统暂时无法接收这条消息，请稍后重试。")
        except Exception as notify_error:
            log_exception("发送客户错误提示失败", notify_error, chat_id=user.id, user_id=user.id)
    except Exception as e:
        log_exception("转发客户消息未知异常", e,
                      chat_id=SUPPORT_GROUP_ID, user_id=user.id)
        try:
            await message.reply_text("⚠️ 客服系统出现临时异常，请稍后重试。")
        except Exception as notify_error:
            log_exception("发送客户错误提示失败", notify_error, chat_id=user.id, user_id=user.id)


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
    if not thread_id:
        await message.reply_text("❌ 请在具体的客户话题中使用此命令。")
        return

    customer_id = get_customer_by_topic(thread_id)
    if customer_id is None:
        await message.reply_text("❌ 找不到该客户话题的记录，可能是旧话题或数据库数据异常。")
        return

    current_agent, _ = get_customer_agent(customer_id)

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

    release_customer_agent_db(customer_id)
    
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
    thread_id = message.message_thread_id
    if not thread_id:
        return

    customer_id = get_customer_by_topic(thread_id)
    if customer_id is None:
        return

    # 检查该客户当前由谁接待
    assigned_agent, assigned_agent_name = get_customer_agent(customer_id)

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
        agent_name = assigned_agent_name or "其他客服"
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
        await context.bot.copy_message(
            chat_id=customer_id,
            from_chat_id=SUPPORT_GROUP_ID,
            message_id=message.message_id,
        )

        sent_msg = await message.reply_text("✅ 已发送给客户。")
        if context.job_queue:
            context.job_queue.run_once(
                delete_notification_callback,
                when=10,
                data={"chat_id": chat.id, "message_id": sent_msg.message_id}
            )

        logger.info(
            "客服消息发送成功 | customer_id=%s | agent_id=%s | message_id=%s",
            customer_id, user.id, message.message_id
        )

    except Forbidden as e:
        log_exception("客服发送失败：客户可能已屏蔽机器人", e,
                      chat_id=customer_id, user_id=user.id)
        await message.reply_text("❌ 发送失败：客户可能已拉黑或屏蔽机器人。")
    except BadRequest as e:
        log_exception("Telegram 拒绝客服消息", e,
                      chat_id=customer_id, user_id=user.id)
        await message.reply_text("❌ 发送失败：该消息类型可能不支持复制，或客户账号状态异常。")
    except TelegramError as e:
        log_exception("客服回复 Telegram 异常", e,
                      chat_id=customer_id, user_id=user.id)
        await message.reply_text("❌ 客服消息发送失败，请稍后重试。")
    except Exception as e:
        log_exception("客服回复未知异常", e,
                      chat_id=customer_id, user_id=user.id)
        await message.reply_text("❌ 客服消息发送失败，请稍后重试。")


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
    # 启动时再次确保数据库表存在。
    init_db()

    app = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .post_init(setup_bot_commands)
        .build()
    )

    if app.job_queue:
        # 启动约 60 秒后发送第一轮，之后严格每 3600 秒（1 小时）发送一轮。
        app.job_queue.run_repeating(
            send_scheduled_ads,
            interval=3600,
            first=60
        )

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

    # 客服群回复监听：不限制消息类型，文字/图片/语音/视频/文件/音频/
    # 位置/联系人/GIF/动画/贴纸等都会进入 admin_reply_customer。
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
