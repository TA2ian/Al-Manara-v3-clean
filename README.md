# Al-Manara v3 — Clean Rebuild

## متطلبات التشغيل

```env
TELEGRAM_BOT_TOKEN=...
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
```

## التشغيل

```bash
python main.py
```

أو عبر Docker:

```bash
docker build -t al-manara-v3 .
docker run -e TELEGRAM_BOT_TOKEN=... -e SUPABASE_URL=... -e SUPABASE_SERVICE_ROLE_KEY=... al-manara-v3
```

## الأوامر المتاحة للعميل

| الأمر | الوظيفة |
|-------|---------|
| `/start` | فتح لوحة المنارة |
| `/verify` | التحقق من الهوية |
| `/wallets` | إدارة محافظ USDT |
| `/buy` | إنشاء طلب شراء |
| `/orders` | عرض طلباتك |

## الأوامر المتاحة للمدير

| الأمر | الوظيفة |
|-------|---------|
| `/admin` | فتح لوحة الإدارة |
| `/identity_pending` | قائمة طلبات التحقق المعلقة |

## هيكل المشروع

```
app/
├── domain/           ← قواعد العمل (بدون أي تبعيات خارجية)
├── application/      ← خدمات التطبيق والـ ports
├── infrastructure/   ← تنفيذ Supabase
│   └── persistence/
├── runtime/
│   └── telegram/
│       ├── shared/   ← actor, guards, messages
│       ├── customer/ ← dashboard, identity, wallets, purchase_order, receipt, orders
│       ├── admin/    ← dashboard, order_review, order_closure, order_listing, fulfillment, identity_review
│       ├── bot_runtime.py  ← polling runtime (cross-platform)
│       ├── router.py       ← تجميع الـ routers
│       └── contracts.py    ← transport DTOs
└── composition_root.py     ← Dependency Injection

supabase/migrations/  ← 40+ SQL migrations
tests/unit/           ← اختبارات وحدة
```

## ما تغيّر عن v2

| المشكلة | الحل |
|--------|------|
| `fcntl` لا يعمل على Windows | cross-platform: `fcntl` (Linux) + `msvcrt` (Windows) |
| رسائل عربية مشتتة | ملف `shared/messages.py` مركزي |
| تكرار كود التحقق | `shared/guards.py` — decorators |
| handlers غير مربوطة | كل handler مربوط بـ router |
| تدفق الشراء غير مكتمل | FSM كامل مع quote preview |
| تدفق الإيصال غير مربوط | `customer/receipt.py` مربوط |
| admin handlers مشتتة | منظمة في `admin/` subpackage |
