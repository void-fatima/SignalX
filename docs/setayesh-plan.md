# ستایش — مسیر کار AI/Agent

این لیست فقط مسئولیت‌های ستایش را از برنامهٔ پنج‌روزه استخراج می‌کند.
در این مرحله اسکلت اصلاح شده؛ موارد آینده به‌معنای انجام‌شدن نیستند.

## وضعیت موجود

- آماده: typed contracts، MockProvider بدون key، pipeline، normalized text، screening اولیهٔ وابسته به محصول/context.
- آماده: context selection با parent/حد طول و conversation isolation؛ query/persistence همچنان با رهام است.
- آماده: score_v1 با half-up، مرزها و guards؛ evidence validation مستقل و revalidation خروجی.
- آماده: 20 پیام synthetic از جمله noise، درخواست روشن، اعتراض قیمت، نقل‌قول و injection.
- پایهٔ آماده: منطق Decimal هزینه و CLI evaluation با کنترل completeness و split؛ هنوز به provider واقعی متصل نیستند.
- باقی: provider واقعی، prompt واقعی، timeout/retry/budget orchestration، grounded reply، dataset labels/dev/test و گزارش واقعی.

## روز 1 — مرزها و نمونهٔ قابل اجرا

مرور contracts/Mock/scoring و سه نمونهٔ قوی، نامرتبط و context-dependent.
تست‌ها و مسیر محلی Mock آماده‌اند؛ با رهام دربارهٔ provider_mode/usage/prompt_version
قرارداد مشترک را هماهنگ می‌کنیم. پایان این بخش: رهام pipeline را بدون key اجرا کند.
گیت کلی تیم هنوز به Auth رهام و Auth UI فاطیما وابسته است.

## روز 2 — adapter واقعی

Provider/model را انتخاب می‌کنیم و endpoint/SDK واقعی را به protocol فعلی وصل می‌کنیم.
خروجی Qualification و usage هر attempt باید typed و قابل اعتبارسنجی باشد؛ خطا usage
را حفظ کند و Mock fallback نداشته باشد. screening/context را روی نمونه‌های توسعه
بررسی می‌کنیم. هنوز بدون اندازه‌گیری ادعای recall یا صرفه‌جویی نداریم.
وابستگی: credential/rate/config و schema واقعی با رهام؛ deploy مالک رهام است.

## روز 3 — qualification واقعی و گیت اصلی

Prompt با دادهٔ نامطمئن جدا، guard نقل‌قول/هویت، evidence واقعی و signals محدود.
budget preflight، timeout و transient retry را با orchestration رهام یکپارچه می‌کنیم؛
هر attempt usage دارد. 20–30 پیام با provider واقعی اجرا و نسخهٔ prompt/model/score
ثبت می‌شود. فاطیما badge واقعی و detail را نمایش می‌دهد.
تا این گیت پاس نشده، feature جانبی شروع نمی‌کنیم.

## روز 4 — reply، cost و evaluation

منطق grounded SuggestedReply فقط با درخواست کاربر؛ snapshot محصول و context معتبر.
رهام endpoint/draft را ذخیره می‌کند و فاطیما کنترل‌های انسانی را می‌سازد.
نرخ‌های واقعی versioned و accounting provider در cost ثبت؛ missing usage صفر نمی‌شود.
Development ~50–60 پیام، test مستقل حداقل 100 پیام با conversationهای جدا و labels
جدا از ورودی Agent. روی dev تنظیم و روی test confusion matrix/precision/recall/
screening recall گزارش می‌شود. پایان روز 4 freeze کامل.

## روز 5 — گزارش و تحویل

مرور ادعاهای AI، گزارش واقعی هزینه/کیفیت، 3 مثال explainable و موارد خطا، محدودیت‌ها
و technical AI docs. فقط bugfix؛ تغییر معماری/API جدید اضافه نمی‌شود. نسخهٔ آنلاین
را مستقل smoke می‌کنیم؛ ارائهٔ تصویری و video با فاطیما و release با رهام است.

قدم بعدی مشخص ما: انتخاب provider/model و ساخت adapter واقعی؛ قبل از آن بررسی
اسکلت و تست‌های این مرحله کافی است. هیچ API پولی در این مرحله فراخوانی نشده است.
