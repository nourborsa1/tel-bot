import sqlite3
import os

def update_database():
    """تحديث قاعدة البيانات وإضافة الأعمدة الجديدة"""
    
    # تأكد من وجود المجلد
    if not os.path.exists('data'):
        os.makedirs('data')
    
    # الاتصال بقاعدة البيانات
    conn = sqlite3.connect('data/subscriptions.db')
    cursor = conn.cursor()
    
    print("🔄 تحديث قاعدة البيانات...")
    
    # 1. جدول المستخدمين
    try:
        # إضافة الأعمدة الجديدة إذا لم تكن موجودة
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'last_renewal_date' not in columns:
            cursor.execute('ALTER TABLE users ADD COLUMN last_renewal_date DATE')
            print("✅ تم إضافة last_renewal_date")
        
        if 'renewal_count' not in columns:
            cursor.execute('ALTER TABLE users ADD COLUMN renewal_count INTEGER DEFAULT 0')
            print("✅ تم إضافة renewal_count")
        
    except sqlite3.OperationalError:
        # إذا الجدول غير موجود، قم بإنشائه
        cursor.execute('''
            CREATE TABLE users (
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
        print("✅ تم إنشاء جدول users جديد")
    
    # 2. جدول المدفوعات
    try:
        cursor.execute("PRAGMA table_info(payments)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'payment_type' not in columns:
            cursor.execute('ALTER TABLE payments ADD COLUMN payment_type TEXT DEFAULT "new"')
            print("✅ تم إضافة payment_type")
        
        if 'amount' not in columns:
            cursor.execute('ALTER TABLE payments ADD COLUMN amount REAL DEFAULT 0')
            print("✅ تم إضافة amount")
        
    except sqlite3.OperationalError:
        cursor.execute('''
            CREATE TABLE payments (
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
        print("✅ تم إنشاء جدول payments جديد")
    
    # 3. جدول الروابط الفردية
    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='invite_links'")
        if not cursor.fetchone():
            cursor.execute('''
                CREATE TABLE invite_links (
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
            print("✅ تم إنشاء جدول invite_links")
    except:
        pass
    
    # 4. جدول التذكيرات
    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='reminders'")
        if not cursor.fetchone():
            cursor.execute('''
                CREATE TABLE reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    reminder_type TEXT,
                    sent_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    message TEXT
                )
            ''')
            print("✅ تم إنشاء جدول reminders")
    except:
        pass
    
    conn.commit()
    conn.close()
    
    print("🎉 تم تحديث قاعدة البيانات بنجاح!")
    print("📊 يمكنك الآن تشغيل البوت.")

if __name__ == '__main__':
    update_database()