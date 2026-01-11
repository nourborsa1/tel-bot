import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, CallbackContext
from telegram.ext import filters
import sqlite3
from datetime import datetime, timedelta
import os
import secrets
import string
from datetime import date

# ============================
# إعدادات البوت
# ============================
TOKEN = "8374206168:AAHTZooee4O10OZd3AXGoL6vO9IPe2MoEuQ"
ADMIN_ID = 8559242290
GROUP_CHAT_ID = -1003194187194

# أسعار الاشتراكات
PRICES = {
    'monthly': 320,
    '3months': 820
}

# معلومات الدفع
PAYMENT_INFO = """
** طرق الدفع المتاحة:**

- **أورنج كاش**: 01204862933 🟠  
- **فودافون كاش**: 01015058614 🔴  
- **إنستا باي**: [Instapay](https://ipn.eg/S/sendo1/instapay/0Ilr40) 🌐  

**تعليمات مهمة:**
1. أرسل المبلغ المحدد حسب نوع الاشتراك
2. احفظ صورة الإيصال
3. أعد إرسالها للبوت
4. انتظر موافقة الأدمن
"""

# إعداد التسجيل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============================
# وظائف قاعدة البيانات
# ============================
def get_db_connection():
    """إنشاء اتصال بقاعدة البيانات"""
    return sqlite3.connect('data/subscriptions.db')


def init_db():
    """تهيئة قاعدة البيانات والجداول"""
    if not os.path.exists('data'):
        os.makedirs('data')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # جدول المستخدمين
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            username TEXT,
            full_name TEXT,
            subscription_type TEXT,
            subscription_start DATE,
            subscription_end DATE,
            status TEXT DEFAULT 'inactive',
            payment_verified BOOLEAN DEFAULT FALSE,
            group_member BOOLEAN DEFAULT FALSE,
            invited_by INTEGER DEFAULT NULL,
            join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_renewal_date DATE,
            renewal_count INTEGER DEFAULT 0
        )
    ''')
    
    # جدول المدفوعات
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            receipt_photo TEXT,
            admin_approved BOOLEAN DEFAULT FALSE,
            admin_rejected BOOLEAN DEFAULT FALSE,
            submission_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            approval_date TIMESTAMP,
            admin_id INTEGER,
            payment_type TEXT DEFAULT 'new',
            amount REAL DEFAULT 0
        )
    ''')
    
    # جدول الروابط الفردية
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS invite_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            link_code TEXT UNIQUE,
            created_by INTEGER,
            used_by INTEGER DEFAULT NULL,
            used_at TIMESTAMP DEFAULT NULL,
            is_used BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP
        )
    ''')
    
    # جدول التذكيرات
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            reminder_type TEXT,
            sent_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            message TEXT
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ تم تهيئة قاعدة البيانات")

def generate_invite_code(length=10):
    """إنشاء كود رابط فريد"""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def create_invite_link(created_by, expires_hours=24):
    """إنشاء رابط دعوة جديد"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    link_code = generate_invite_code()
    expires_at = datetime.now() + timedelta(hours=expires_hours)
    
    cursor.execute('''
        INSERT INTO invite_links (link_code, created_by, expires_at)
        VALUES (?, ?, ?)
    ''', (link_code, created_by, expires_at))
    
    conn.commit()
    conn.close()
    return link_code

def use_invite_link(link_code, user_id):
    """استخدام رابط الدعوة"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, expires_at FROM invite_links 
        WHERE link_code = ? AND is_used = FALSE AND expires_at > datetime('now')
    ''', (link_code,))
    
    result = cursor.fetchone()
    
    if result:
        link_id, expires_at = result
        cursor.execute('''
            UPDATE invite_links 
            SET used_by = ?, used_at = CURRENT_TIMESTAMP, is_used = TRUE
            WHERE id = ?
        ''', (user_id, link_id))
        
        conn.commit()
        conn.close()
        return True
    
    conn.close()
    return False

def add_user(user_id, username, full_name, invited_by=None):
    """إضافة مستخدم جديد"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT OR IGNORE INTO users (user_id, username, full_name, invited_by)
        VALUES (?, ?, ?, ?)
    ''', (user_id, username, full_name, invited_by))
    
    conn.commit()
    conn.close()

def save_payment(user_id, photo_id, payment_type='new', amount=0):
    """حفظ معلومات الدفع"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO payments (user_id, receipt_photo, payment_type, amount)
        VALUES (?, ?, ?, ?)
    ''', (user_id, photo_id, payment_type, amount))
    
    conn.commit()
    conn.close()

def update_subscription(user_id, sub_type, approved_by=None, is_renewal=False):
    """تحديث بيانات الاشتراك"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # الحصول على تاريخ انتهاء الاشتراك الحالي
    cursor.execute('SELECT subscription_end FROM users WHERE user_id = ?', (user_id,))
    current_end = cursor.fetchone()
    
    if current_end and current_end[0] and is_renewal:
        # تجديد: إضافة المدة إلى تاريخ الانتهاء الحالي
        try:
            current_end_date = datetime.strptime(current_end[0], '%Y-%m-%d')
        except:
            current_end_date = datetime.now()
        
        if sub_type == 'monthly':
            new_end_date = current_end_date + timedelta(days=30)
        else:  # 3months
            new_end_date = current_end_date + timedelta(days=90)
        
        start_date = current_end_date
    else:
        # اشتراك جديد: البدء من اليوم
        start_date = datetime.now()
        if sub_type == 'monthly':
            new_end_date = start_date + timedelta(days=30)
        else:  # 3months
            new_end_date = start_date + timedelta(days=90)
    
    # تحديث بيانات المستخدم
    cursor.execute('''
        UPDATE users 
        SET subscription_type = ?, 
            subscription_start = ?, 
            subscription_end = ?, 
            status = 'active', 
            payment_verified = TRUE,
            last_renewal_date = CURRENT_DATE,
            renewal_count = renewal_count + 1
        WHERE user_id = ?
    ''', (sub_type, start_date.date(), new_end_date.date(), user_id))
    
    # تحديث حالة الدفع
    if approved_by:
        cursor.execute('''
            UPDATE payments 
            SET admin_approved = TRUE, approval_date = CURRENT_TIMESTAMP, admin_id = ?
            WHERE user_id = ? AND admin_approved = FALSE AND admin_rejected = FALSE
        ''', (approved_by, user_id))
    
    conn.commit()
    conn.close()
    
    return new_end_date

def get_user_info(user_id):
    """الحصول على معلومات المستخدم"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT user_id, username, full_name, subscription_type, 
               subscription_start, subscription_end, status, renewal_count
        FROM users 
        WHERE user_id = ?
    ''', (user_id,))
    
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return {
            'user_id': result[0],
            'username': result[1],
            'full_name': result[2],
            'subscription_type': result[3],
            'subscription_start': result[4],
            'subscription_end': result[5],
            'status': result[6],
            'renewal_count': result[7]
        }
    return None

def get_expiring_subscriptions(days_before=3):
    """الحصول على الاشتراكات التي تنتهي قريباً"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    target_date = date.today() + timedelta(days=days_before)
    
    cursor.execute('''
        SELECT user_id, username, subscription_end
        FROM users
        WHERE status = 'active' 
          AND subscription_end <= ? 
          AND subscription_end > date('now')
          AND (last_renewal_date IS NULL OR last_renewal_date < date('now', '-20 days'))
    ''', (target_date,))
    
    results = cursor.fetchall()
    conn.close()
    return results

def get_expired_subscriptions():
    """الحصول على الاشتراكات المنتهية"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT user_id, username
        FROM users
        WHERE status = 'active' AND subscription_end <= date('now')
    ''')
    
    results = cursor.fetchall()
    conn.close()
    return results

def get_users_needing_renewal():
    """الحصول على المستخدمين الذين يحتاجون تجديد"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # المستخدمين الذين انتهت اشتراكاتهم خلال الأسبوع الماضي
    week_ago = date.today() - timedelta(days=7)
    
    cursor.execute('''
        SELECT user_id, username, subscription_end
        FROM users
        WHERE subscription_end <= date('now') 
          AND subscription_end >= ?
          AND status = 'expired'
    ''', (week_ago,))
    
    results = cursor.fetchall()
    conn.close()
    return results

def save_reminder(user_id, reminder_type, message):
    """حفظ التذكير المرسل"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO reminders (user_id, reminder_type, message)
        VALUES (?, ?, ?)
    ''', (user_id, reminder_type, message))
    
    conn.commit()
    conn.close()

# ============================
# وظائف البوت الأساسية
# ============================
async def start(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = user.id
    
    # التحقق من رابط الدعوة
    if context.args:
        invite_code = context.args[0]
        if not use_invite_link(invite_code, user_id):
            await update.message.reply_text("⚠️ رابط الدعوة غير صالح أو منتهي الصلاحية.")
            return
    
    # إضافة المستخدم إذا لم يكن موجوداً
    add_user(user_id, user.username, user.full_name)
    
    # الحصول على معلومات المستخدم
    user_info = get_user_info(user_id)
    
    # إنشاء واجهة المستخدم
    keyboard = []
    
    if user_info and user_info['status'] == 'active':
        # للمستخدمين الحاليين: عرض خيارات التجديد
        days_left = (datetime.strptime(user_info['subscription_end'], '%Y-%m-%d') - datetime.now()).days
        
        message_text = f"""
👋 مرحباً مرة أخرى {user.full_name}!

📊 **حالة اشتراكك الحالية:**
• نوع الاشتراك: {user_info['subscription_type']}
• تاريخ البدء: {user_info['subscription_start']}
• تاريخ الانتهاء: {user_info['subscription_end']}
• الأيام المتبقية: {days_left} يوم
• عدد مرات التجديد: {user_info['renewal_count']}

💰 **أسعار التجديد:**
• تجديد شهر: {PRICES['monthly']} جنيه
• تجديد 3 شهور: {PRICES['3months']} جنيه

📝 **لتجديد اشتراكك:**
1. اختر نوع التجديد
2. ادفع المبلغ
3. أرسل صورة الإيصال
"""
        
        keyboard = [
            [InlineKeyboardButton("🔄 تجديد شهر", callback_data='renew_monthly')],
            [InlineKeyboardButton("🔄 تجديد 3 شهور", callback_data='renew_3months')],
            [InlineKeyboardButton("ℹ️ طرق الدفع", callback_data='payment_info')]
        ]
    else:
        # للمستخدمين الجدد أو المنتهية اشتراكاتهم
        status_text = ""
        if user_info and user_info['status'] == 'expired':
            status_text = f"\n⚠️ اشتراكك الحالي منتهي منذ {user_info.get('days_since_expired', '?')} يوم"
        
        message_text = f"""
👋 مرحباً {user.full_name}!{status_text}

🎯 **تفاصيل الاشتراكات:**
• اشتراك شهر: {PRICES['monthly']} جنيه
• اشتراك 3 شهور: {PRICES['3months']} جنيه

📝 **لبدء الاشتراك:**
1. اختر نوع الاشتراك
2. ادفع المبلغ
3. أرسل صورة الإيصال
"""
        
        keyboard = [
            [InlineKeyboardButton("🆕 اشتراك شهر", callback_data='subscribe_monthly')],
            [InlineKeyboardButton("🆕 اشتراك 3 شهور", callback_data='subscribe_3months')],
            [InlineKeyboardButton("ℹ️ طرق الدفع", callback_data='payment_info')]
        ]
    
    # إضافة أزرار الأدمن
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("🛠 إدارة الروابط", callback_data='admin_links')])
        keyboard.append([InlineKeyboardButton("📊 الإحصائيات", callback_data='admin_stats')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')

async def button_handler(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_info = get_user_info(user_id)
    
    if query.data == 'subscribe_monthly':
        amount = PRICES['monthly']
        await query.edit_message_text(
            text=f"📅 **اشتراك جديد - شهر واحد**\n\n"
                 f"💰 المبلغ: {amount} جنيه\n\n"
                 f"{PAYMENT_INFO}\n\n"
                 f"✅ بعد الدفع، أرسل صورة الإيصال هنا.",
            parse_mode='Markdown'
        )
        
    elif query.data == 'subscribe_3months':
        amount = PRICES['3months']
        await query.edit_message_text(
            text=f"📅 **اشتراك جديد - 3 شهور**\n\n"
                 f"💰 المبلغ: {amount} جنيه\n\n"
                 f"{PAYMENT_INFO}\n\n"
                 f"✅ بعد الدفع، أرسل صورة الإيصال هنا.",
            parse_mode='Markdown'
        )
        
    elif query.data == 'renew_monthly':
        amount = PRICES['monthly']
        if user_info and user_info['status'] == 'active':
            days_left = (datetime.strptime(user_info['subscription_end'], '%Y-%m-%d') - datetime.now()).days
            await query.edit_message_text(
                text=f"🔄 **تجديد اشتراك - شهر إضافي**\n\n"
                     f"💰 المبلغ: {amount} جنيه\n"
                     f"⏰ المتبقي من اشتراكك الحالي: {days_left} يوم\n\n"
                     f"{PAYMENT_INFO}\n\n"
                     f"✅ بعد الدفع، أرسل صورة الإيصال هنا.",
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text("⚠️ ليس لديك اشتراك نشط للتجديد.")
            
    elif query.data == 'renew_3months':
        amount = PRICES['3months']
        if user_info and user_info['status'] == 'active':
            days_left = (datetime.strptime(user_info['subscription_end'], '%Y-%m-%d') - datetime.now()).days
            await query.edit_message_text(
                text=f"🔄 **تجديد اشتراك - 3 شهور إضافية**\n\n"
                     f"💰 المبلغ: {amount} جنيه\n"
                     f"⏰ المتبقي من اشتراكك الحالي: {days_left} يوم\n\n"
                     f"{PAYMENT_INFO}\n\n"
                     f"✅ بعد الدفع، أرسل صورة الإيصال هنا.",
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text("⚠️ ليس لديك اشتراك نشط للتجديد.")
            
    elif query.data == 'payment_info':
        await query.edit_message_text(
            text=f"💳 **معلومات الدفع**\n\n{PAYMENT_INFO}",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("↩️ رجوع", callback_data='back_to_main')]
            ])
        )
        
    elif query.data == 'admin_links':
        await admin_links(update, context)
    elif query.data == 'admin_stats':
        await admin_stats(update, context)
    elif query.data == 'create_link':
        await create_invite_link_handler(update, context)
    elif query.data == 'show_links':
        await show_links_handler(update, context)
    elif query.data == 'back_to_main':
        await start_from_callback(update, context)

async def start_from_callback(update: Update, context: CallbackContext):
    """نسخة start للاستخدام من callback"""
    query = update.callback_query
    user = query.from_user
    user_id = user.id
    user_info = get_user_info(user_id)
    
    keyboard = []
    
    if user_info and user_info['status'] == 'active':
        keyboard = [
            [InlineKeyboardButton("🔄 تجديد شهر", callback_data='renew_monthly')],
            [InlineKeyboardButton("🔄 تجديد 3 شهور", callback_data='renew_3months')],
            [InlineKeyboardButton("ℹ️ طرق الدفع", callback_data='payment_info')]
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("🆕 اشتراك شهر", callback_data='subscribe_monthly')],
            [InlineKeyboardButton("🆕 اشتراك 3 شهور", callback_data='subscribe_3months')],
            [InlineKeyboardButton("ℹ️ طرق الدفع", callback_data='payment_info')]
        ]
    
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("🛠 إدارة الروابط", callback_data='admin_links')])
        keyboard.append([InlineKeyboardButton("📊 الإحصائيات", callback_data='admin_stats')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = f"👋 مرحباً {user.full_name}!\n\nاختر الخيار المناسب:"
    await query.edit_message_text(message_text, reply_markup=reply_markup)

async def admin_links(update: Update, context: CallbackContext) -> None:
    """إدارة روابط الأدمن"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        await query.edit_message_text("ليس لديك صلاحية للوصول إلى هذه الصفحة.")
        return
    
    keyboard = [
        [InlineKeyboardButton("➕ إنشاء رابط جديد", callback_data='create_link')],
        [InlineKeyboardButton("📋 عرض الروابط", callback_data='show_links')],
        [InlineKeyboardButton("↩️ رجوع", callback_data='back_to_main')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🛠 لوحة إدارة الروابط\n\nاختر الإجراء المطلوب:",
        reply_markup=reply_markup
    )

async def admin_stats(update: Update, context: CallbackContext) -> None:
    """إحصائيات النظام"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        await query.edit_message_text("ليس لديك صلاحية للوصول إلى هذه الصفحة.")
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # إحصائيات المستخدمين
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM users WHERE status = "active"')
    active_users = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM users WHERE status = "expired"')
    expired_users = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM users WHERE subscription_end <= date("now") AND status = "active"')
    expired_but_active = cursor.fetchone()[0]
    
    # إحصائيات المدفوعات
    cursor.execute('SELECT COUNT(*) FROM payments WHERE admin_approved = 1')
    approved_payments = cursor.fetchone()[0]
    
    cursor.execute('SELECT SUM(amount) FROM payments WHERE admin_approved = 1')
    total_revenue = cursor.fetchone()[0] or 0
    
    # إحصائيات التجديدات
    cursor.execute('SELECT SUM(renewal_count) FROM users')
    total_renewals = cursor.fetchone()[0] or 0
    
    conn.close()
    
    stats_text = f"""
📊 **إحصائيات النظام**

👥 **المستخدمين:**
• إجمالي المستخدمين: {total_users}
• المشتركين النشطين: {active_users}
• المشتركين المنتهية اشتراكاتهم: {expired_users}
• يحتاجون تحديث الحالة: {expired_but_active}

💰 **المالية:**
• المدفوعات الموافق عليها: {approved_payments}
• إجمالي الإيرادات: {total_revenue:.2f} جنيه

🔄 **التجديدات:**
• إجمالي مرات التجديد: {total_renewals}
    """
    
    keyboard = [[InlineKeyboardButton("↩️ رجوع", callback_data='admin_links')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(stats_text, reply_markup=reply_markup, parse_mode='Markdown')

async def create_invite_link_handler(update: Update, context: CallbackContext) -> None:
    """معالج إنشاء روابط جديدة"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    link_code = create_invite_link(ADMIN_ID)
    bot_username = context.bot.username
    invite_link = f"https://t.me/{bot_username}?start={link_code}"
    
    await query.edit_message_text(
        f"✅ تم إنشاء رابط الدعوة بنجاح!\n\n"
        f"📎 الرابط:\n`{invite_link}`\n\n"
        f"⏰ صلاحية الرابط: 24 ساعة\n"
        f"👤 عدد المستخدمين: 1 فقط\n\n"
        f"يمكنك مشاركة هذا الرابط مع العملاء.",
        parse_mode='Markdown'
    )

async def show_links_handler(update: Update, context: CallbackContext) -> None:
    """عرض الروابط الحالية"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT link_code, created_at, expires_at, is_used, used_by
        FROM invite_links 
        WHERE created_by = ?
        ORDER BY created_at DESC
        LIMIT 10
    ''', (ADMIN_ID,))
    
    links = cursor.fetchall()
    conn.close()
    
    bot_username = context.bot.username
    
    if not links:
        await query.edit_message_text("لا توجد روابط حالياً.")
        return
    
    message_text = "📋 آخر 10 روابط:\n\n"
    
    for link_code, created_at, expires_at, is_used, used_by in links:
        status = "🟢 مستخدم" if is_used else "🟢 نشط"
        used_text = f"بواسطة {used_by}" if used_by else ""
        full_link = f"https://t.me/{bot_username}?start={link_code}"
        
        message_text += f"• **{link_code}**\n"
        message_text += f"  الحالة: {status} {used_text}\n"
        message_text += f"  الإنشاء: {created_at[:16]}\n"
        message_text += f"  الانتهاء: {expires_at[:16]}\n"
        message_text += f"  الرابط: `{full_link}`\n\n"
    
    keyboard = [[InlineKeyboardButton("↩️ رجوع", callback_data='admin_links')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')

async def handle_receipt_photo(update: Update, context: CallbackContext) -> None:
    if update.message.chat.type != 'private':
        return
    """معالجة صورة الإيصال"""
    user = update.effective_user
    user_id = user.id
    user_info = get_user_info(user_id)
    
    photo_file = await update.message.photo[-1].get_file()
    photo_id = photo_file.file_id
    
    # تحديد نوع الدفع تلقائياً بناءً على وجود المستخدم
    if user_info and user_info['status'] == 'active':
        payment_type = 'renewal'
        payment_type_text = "تجديد"
        amount = PRICES['monthly']  # قيمة افتراضية للتجديد
    else:
        payment_type = 'new'
        payment_type_text = "جديد"
        amount = PRICES['monthly']  # قيمة افتراضية للاشتراك الجديد
    
    # حفظ الدفع
    save_payment(user_id, photo_id, payment_type, amount)
    
    # إرسال إشعار للأدمن
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"📩 طلب {payment_type_text} اشتراك من {user.full_name} (@{user.username})"
    )
    
    # الحصول على معلومات المستخدم الحالية لعرضها للأدمن
    user_status = "غير مشترك"
    expiry_date = "-"
    
    if user_info:
        if user_info['status'] == 'active':
            user_status = f"نشط (ينتهي: {user_info['subscription_end']})"
            expiry_date = user_info['subscription_end']
        else:
            user_status = "منتهي"
    
    keyboard = [
        [
            InlineKeyboardButton("✅ موافقة - شهر", callback_data=f'approve_monthly_{user_id}'),
            InlineKeyboardButton("✅ موافقة - 3 شهور", callback_data=f'approve_3months_{user_id}')
        ],
        [InlineKeyboardButton("❌ رفض", callback_data=f'reject_{user_id}')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=photo_id,
        caption=f"إيصال دفع من {user.full_name} (@{user.username})\n"
                f"🆔 ID: {user_id}\n"
                f"📋 النوع: {payment_type_text}\n"
                f"💰 المبلغ: {amount} جنيه\n"
                f"📊 حالة المستخدم: {user_status}\n"
                f"📅 تاريخ الانتهاء الحالي: {expiry_date}",
        reply_markup=reply_markup
    )
    
    await update.message.reply_text(
        f"✅ تم استلام صورة الإيصال بنجاح.\n"
        f"💰 المبلغ: {amount} جنيه\n"
        f"📋 النوع: {payment_type_text}\n\n"
        f"سيتم مراجعته من قبل الأدمن وتفعيل اشتراكك قريباً."
    )

async def admin_button_handler(update: Update, context: CallbackContext) -> None:
    """معالج أزرار الأدمن"""
    query = update.callback_query
    await query.answer()
    
    admin_id = query.from_user.id
    if admin_id != ADMIN_ID:
        await query.edit_message_text("ليس لديك صلاحية للقيام بهذا الإجراء.")
        return
    
    data = query.data
    
    if data.startswith('approve_'):
        parts = data.split('_')
        sub_type = parts[1]
        user_id = int(parts[2])
        
        user_info = get_user_info(user_id)
        
        # ✅ التحديد التلقائي إذا كان تجديد أو اشتراك جديد
        is_renewal = user_info and user_info['status'] == 'active'
        
        # ✅ تحديث الاشتراك في قاعدة البيانات
        new_end_date = update_subscription(user_id, sub_type, admin_id, is_renewal)
        
        # ✅ إنشاء رابط دعوة للمستخدم
        try:
            invite_link = await context.bot.create_chat_invite_link(
                chat_id=GROUP_CHAT_ID,
                member_limit=1,
                expire_date=datetime.now() + timedelta(hours=24)
            )
            
            # ✅ إرسال الرابط للمستخدم
            renewal_text = "تم تجديد" if is_renewal else "تم تفعيل"
            
            # رسالة مختلفة للمستخدمين الجدد عن القدامى
            if is_renewal:
                # رسالة التجديد
                old_end_date = user_info['subscription_end'] if user_info else "-"
                message_text = f"""🎉 {renewal_text} اشتراكك بنجاح!

📅 نوع الاشتراك: {sub_type}
⏰ المدة: {'شهر واحد' if sub_type == 'monthly' else '3 شهور'}
📅 تاريخ الانتهاء السابق: {old_end_date}
📅 تاريخ الانتهاء الجديد: {new_end_date.date()}

📎 رابط الانضمام للجروب:
{invite_link.invite_link}

⚠️ ملاحظة:
• الرابط صالح لاستخدام واحد فقط
• الرابط ينتهي بعد 24 ساعة
• في حالة انتهاء الرابط، راسل الأدمن"""
            else:
                # رسالة الاشتراك الجديد
                message_text = f"""🎉 {renewal_text} اشتراكك بنجاح!

📅 نوع الاشتراك: {sub_type}
⏰ المدة: {'شهر واحد' if sub_type == 'monthly' else '3 شهور'}
📅 تاريخ البدء: {datetime.now().date()}
📅 تاريخ الانتهاء: {new_end_date.date()}

📎 رابط الانضمام للجروب:
{invite_link.invite_link}

📝 تعليمات:
• الرابط صالح لاستخدام واحد فقط
• الرابط ينتهي بعد 24 ساعة
• بعد الانضمام، يمكنك الوصول لكامل المحتوى

مرحباً بك في عائلتنا! 🎊"""
            
            await context.bot.send_message(
                chat_id=user_id,
                text=message_text
            )
            
            # ✅ تحديث حالة المستخدم في قاعدة البيانات
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET group_member = TRUE WHERE user_id = ?', (user_id,))
            conn.commit()
            conn.close()
            
            # رسالة تأكيد للأدمن
            renewal_msg = "تجديد" if is_renewal else "تفعيل"
            user_info = get_user_info(user_id)
            username_display = f"@{user_info['username']}" if user_info and user_info['username'] else user_info['full_name']
            
            confirmation_text = f"""✅ تم {renewal_msg} الاشتراك بنجاح!

👤 المستخدم: {username_display}
🆔 ID: {user_id}
📅 النوع: {sub_type} ({'شهر واحد' if sub_type == 'monthly' else '3 شهور'})
📊 العملية: {'تجديد' if is_renewal else 'اشتراك جديد'}
📅 تاريخ الانتهاء: {new_end_date.date()}

✅ تم إرسال رابط الدعوة للمستخدم."""
            
            await query.edit_message_text(confirmation_text)
            
        except Exception as e:
            logger.error(f"فشل في إنشاء رابط الدعوة: {e}")
            # إذا فشل إنشاء الرابط، نوفر على الأقل معلومات للمستخدم
            await context.bot.send_message(
                chat_id=user_id,
                text=f"✅ تم تفعيل اشتراكك بنجاح!\n\n"
                     f"يرجى مراسلة الأدمن للحصول على رابط الانضمام للجروب."
            )
            await query.edit_message_text(f"✅ تم {renewal_msg} الاشتراك للمستخدم {user_id}\n\n"
                                        f"⚠️ فشل إنشاء رابط الجروب تلقائياً. يرجى إرسال الرابط يدوياً للمستخدم.")
        
    elif data.startswith('reject_'):
        user_id = int(data.split('_')[1])
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE payments 
            SET admin_rejected = TRUE, approval_date = CURRENT_TIMESTAMP, admin_id = ?
            WHERE user_id = ? AND admin_approved = FALSE AND admin_rejected = FALSE
        ''', (admin_id, user_id))
        conn.commit()
        conn.close()
        
        await context.bot.send_message(
            chat_id=user_id,
            text="❌ تم رفض إيصال الدفع الخاص بك. يرجى التحقق من:\n\n• صورة الإيصال واضحة\n• المبلغ صحيح\n• البيانات مكتوبة بوضوح\n\nإذا كنت تعتقد أن هناك خطأ، راسل الأدمن."
        )
        
        await query.edit_message_text("✅ تم رفض الدفع وإعلام المستخدم.")

async def send_expiring_reminders(context: CallbackContext):
    """إرسال تذكيرات للمستخدمين الذين اشتراكاتهم على وشك الانتهاء"""
    expiring_users = get_expiring_subscriptions(3)  # قبل 3 أيام
    
    for user_id, username, end_date in expiring_users:
        try:
            user_info = get_user_info(user_id)
            if user_info:
                days_left = (datetime.strptime(end_date, '%Y-%m-%d') - datetime.now()).days
                
                message = f"""
⏰ **تذكير بانتهاء الاشتراك**

عزيزي {user_info['full_name']},
اشتراكك سينتهي بعد {days_left} أيام ({end_date}).

🔄 **خيارات التجديد:**
• تجديد شهر: {PRICES['monthly']} جنيه
• تجديد 3 شهور: {PRICES['3months']} جنيه

{PAYMENT_INFO}

للتجديد، اضغط على /start واختر "تجديد اشتراك"
                """
                
                await context.bot.send_message(
                    chat_id=user_id,
                    text=message,
                    parse_mode='Markdown'
                )
                
                save_reminder(user_id, 'expiring', f"تذكير بانتهاء الاشتراك بعد {days_left} أيام")
                
        except Exception as e:
            logger.error(f"فشل في إرسال تذكير لـ {user_id}: {e}")

async def send_expired_reminders(context: CallbackContext):
    """إرسال تذكيرات للمستخدمين الذين انتهت اشتراكاتهم"""
    expired_users = get_expired_subscriptions()
    
    for user_id, username in expired_users:
        try:
            user_info = get_user_info(user_id)
            if user_info:
                message = f"""
⚠️ **انتهاء الاشتراك**

عزيزي {user_info['full_name']},
لقد انتهت مدة اشتراكك.

❌ **سيتم إزالتك من الجروب قريباً.**

🔄 **للاستمرار في الخدمة:**
• تجديد شهر: {PRICES['monthly']} جنيه
• تجديد 3 شهور: {PRICES['3months']} جنيه

{PAYMENT_INFO}

للتجديد، اضغط على /start واختر "تجديد اشتراك"
                """
                
                await context.bot.send_message(
                    chat_id=user_id,
                    text=message,
                    parse_mode='Markdown'
                )
                
                save_reminder(user_id, 'expired', "تذكير بانتهاء الاشتراك")
                
        except Exception as e:
            logger.error(f"فشل في إرسال تذكير انتهاء لـ {user_id}: {e}")

async def check_expired_subscriptions_and_remove(context: CallbackContext):
    """فحص وإزالة المستخدمين المنتهية اشتراكاتهم"""
    expired_users = get_expired_subscriptions()
    
    for user_id, username in expired_users:
        try:
            # إزالة المستخدم من الجروب
            await context.bot.ban_chat_member(chat_id=GROUP_CHAT_ID, user_id=user_id)
            
            # فك الحظر بعد ثانية ليتمكن من الانضمام مرة أخرى
            async def unban_user(ctx):
                try:
                    await ctx.bot.unban_chat_member(
                        chat_id=GROUP_CHAT_ID, 
                        user_id=user_id, 
                        only_if_banned=True
                    )
                except Exception as e:
                    logger.error(f"فشل في فك حظر المستخدم {user_id}: {e}")
            
            context.job_queue.run_once(unban_user, 1)
            
            # تحديث حالة المستخدم في قاعدة البيانات
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users 
                SET status = 'expired', group_member = FALSE
                WHERE user_id = ?
            ''', (user_id,))
            conn.commit()
            conn.close()
            
            await context.bot.send_message(
                chat_id=user_id,
                text="❌ تم إزالتك من الجروب بسبب انتهاء اشتراكك.\n\nللاستمرار، يرجى تجديد الاشتراك عن طريق /start"
            )
            
        except Exception as e:
            logger.error(f"فشل في معالجة انتهاء الاشتراك لـ {user_id}: {e}")

async def send_renewal_reminders(context: CallbackContext):
    """إرسال تذكيرات تجديد للمستخدمين المنتهية اشتراكاتهم"""
    users_needing_renewal = get_users_needing_renewal()
    
    for user_id, username, end_date in users_needing_renewal:
        try:
            user_info = get_user_info(user_id)
            if user_info:
                days_since_expired = (datetime.now() - datetime.strptime(end_date, '%Y-%m-%d')).days
                
                message = f"""
🔄 **تذكير بالتجديد**

عزيزي {user_info['full_name']},
لقد انتهى اشتراكك منذ {days_since_expired} أيام.

💎 **عروض التجديد:**
• تجديد شهر: {PRICES['monthly']} جنيه
• تجديد 3 شهور: {PRICES['3months']} جنيه

{PAYMENT_INFO}

للتجديد، اضغط على /start
                """
                
                await context.bot.send_message(
                    chat_id=user_id,
                    text=message,
                    parse_mode='Markdown'
                )
                
                save_reminder(user_id, 'renewal', f"تذكير تجديد بعد {days_since_expired} أيام من الانتهاء")
                
        except Exception as e:
            logger.error(f"فشل في إرسال تذكير تجديد لـ {user_id}: {e}")

def main():
    """الدالة الرئيسية"""
    print("🚀 بدء تشغيل البوت...")
    
    # تهيئة قاعدة البيانات
    init_db()
    
    # إنشاء البوت مع Application
    application = Application.builder().token(TOKEN).build()
    
    # إضافة handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler, pattern='^(subscribe_monthly|subscribe_3months|renew_monthly|renew_3months|payment_info|admin_links|admin_stats|create_link|show_links|back_to_main)$'))
    application.add_handler(CallbackQueryHandler(admin_button_handler, pattern='^(approve_|reject_)'))
    application.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, handle_receipt_photo))
    
    # الجدولة للتذكيرات والفحوصات
    job_queue = application.job_queue
    
    # تذكيرات قبل الانتهاء (كل يوم)
    job_queue.run_repeating(send_expiring_reminders, interval=86400, first=0)
    
    # تذكيرات بعد الانتهاء (كل يوم)
    job_queue.run_repeating(send_expired_reminders, interval=86400, first=0)
    
    # إزالة المنتهية اشتراكاتهم (كل ساعة)
    job_queue.run_repeating(check_expired_subscriptions_and_remove, interval=3600, first=0)
    
    # تذكيرات التجديد (كل 3 أيام)
    job_queue.run_repeating(send_renewal_reminders, interval=259200, first=0)
    
    # بدء البوت
    print("✅ البوت يعمل بنجاح!")
    application.run_polling()

if __name__ == '__main__':
    main()