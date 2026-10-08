# SignalX — معماری جاری و پایهٔ مشترک

این سند ترکیب اجرایی اسکلت موجود با برنامهٔ پنج‌روزهٔ جدید است. مرجع جدید:
[PDF برنامهٔ پنج‌روزه](sources/SignalX_Architecture_and_5Day_Plan_FA.pdf).
[سند هفت‌روزهٔ قبلی](sources/architecture-7day.md) برای سابقه و جزئیات فنی نگهداری شده است.
نام نمایشی فعلی در کد `singnalX` مطابق درخواست اولیهٔ کاربر است؛ عنوان سند جدید SignalX است.
پوشهٔ ریپازیتوری `SignalX` است و پروژه در ریشهٔ آن قرار دارد.

## تصمیم معماری

Monorepo + Modular Monolith را حفظ می‌کنیم: Next.js/TypeScript/Tailwind در frontend؛
FastAPI/Pydantic و SQLAlchemy/Alembic در backend؛ PostgreSQL و صف analysis_runs؛
API و یک worker مستقل از همان کدبیس و image. Redis/Celery، vector DB مستقل و
چارچوب چندعامل برای این مقیاس اضافه نمی‌شوند. SQLite فقط مسیر محلی و تست است.

مسیر MVP نهایی: Register/Login → Product → CSV → Run → Worker →
Screen/Context/Qualify/Score → Lead/Evidence/Cost → Reply on demand.
Routeهای Auth، session و scope کاربر در Backend به‌صورت محلی پیاده شده‌اند؛
اتصال UI/client احراز هویت هنوز با فاطیماست. Adapter واقعی Agent پیاده شده؛
اجرای live در هر محیط به تنظیم provider و credential نیاز دارد.

## مالکیت

| عضو | مالکیت |
| --- | --- |
| رهام | API، DB، Auth، user ownership، schema، migration، import، worker، persistence، deployment/release |
| ستایش | Agent contracts، providerها، screening، context selection، qualification، guards، scoring، reply logic، cost، evaluation و AI docs |
| فاطیما | تمام Frontend/UI/UX، Auth UI، client API، صفحات و states، responsive، demo و pitch visuals |

Agent نباید FastAPI/SQLAlchemy را import کند یا DB بنویسد. Query با رهام و انتخاب
context با ستایش است. تولید متن پاسخ با ستایش، ذخیره/endpoint با رهام و کنترل انسانی
با فاطیما است. مالک OpenAPI رهام است؛ تغییر قرارداد با هر سه نفر هماهنگ می‌شود.

## قراردادها و رفتار حفظ‌شده

- `/api/v1`، UUID string، UTC، snake_case، enum lowercase؛ خطای مشترک error/code/message/details.
- فهرست items/total/limit/offset؛ قرارداد واقعی در contracts/openapi.json و typeهای تولیدشده.
- CSV: UTF-8/BOM، timezone، 5 MB، 500 ردیف، content تا 4000 کاراکتر؛ اعتبارسنجی کامل قبل از insert.
- Import dedup بر اساس user/community/checksum؛ run با Idempotency-Key در محدودهٔ کاربر و پاسخ 202؛ payload متفاوت با همان key برابر 409.
- Snapshot محصول/config برای run؛ صف و claim کوتاه؛ هیچ transaction هنگام provider call باز نیست.
- Run: queued/running/completed/partial/failed/interrupted؛ خطای یک پیام بقیه را متوقف نمی‌کند.
- Context فقط از همان batch/conversation؛ parent اولویت دارد؛ حداکثر 3 قبل و 2 بعد، 5 پیام و 8000 کاراکتر.
- حالت offline پیام آینده دارد؛ live باید آن را حذف کند. این تفاوت در UI/مستندات شفاف است.
- غربال‌شده‌ها signals/score/intent برابر null دارند؛ failedها decision=null دارند.
- Provider خروجی qualification و usage هر attempt را می‌دهد؛ score/decision در کد محاسبه می‌شوند.
- evidence باید quote واقعی و ID موجود در target/context داشته باشد؛ دستور داخل پیام دادهٔ نامطمئن است.
- Mock صریح است؛ mode واقعی پیکربندی‌نشده خطا می‌دهد و به Mock تبدیل نمی‌شود.

## Scoring و هزینه

`30×purchase_intent + 30×product_fit + 15×need_strength + 10×urgency + 10×confidence + 5×response_opportunity`

وزن‌ها و مرزهای 40/70 در دو سند یکسان‌اند. سند جدید `round` را دقیق تعریف نکرده؛
رفتار مشخص قبلی `floor(raw_score + 0.5)` و نسخه score_v1 حفظ می‌شود تا اختلاف
rounding زبان‌ها در مرزها ایجاد نشود. Confidence<0.60، fit<0.50، evidence نامعتبر یا
نیاز به بازبینی، تصمیم respond را به review تنزل می‌دهد.

Rate با واحد **USD به ازای یک میلیون توکن** به تابع داده می‌شود؛ تقسیم بر 1,000,000
ضروری است. نرخ واقعی اختراع نمی‌شود. usage/rate نامعلوم cost=null؛ Mock صفر با badge
و cost_status=mock است. هزینه/پیام یا Lead با مخرج صفر یا هزینهٔ ناقص null می‌شود.
منطق Agent cost و ذخیره Usage آماده‌اند؛ Backend analytics هزینهٔ ثبت‌شده را تجمیع می‌کند.
Budget enforcement و تنظیم معتبر نرخ‌ها هنوز انجام نشده‌اند.

## کارهای باقی‌مانده برای نسخه آنلاین

Routeهای Auth، password hashing، نشست قابل ابطال و scope محصول، import، پیام، run،
lead، draft پاسخ و feedback در Backend پیاده شده‌اند. Migration 0002 داده‌های قبل از Auth
را بدون مالک می‌گذارد تا API احراز‌شده آن‌ها را نشان ندهد. فاطیما باید UI احراز هویت
را به API وصل کند و درخواست‌ها را با credentials بفرستد. بررسی PostgreSQL/Compose
و deployment آنلاین باقی است.

Deploy تا پایان روز 2، provider واقعی تا پایان روز 3، Cost/Reply/Feedback/Evaluation
و freeze کامل تا پایان روز 4، release روز 5. Adapter واقعی آماده است؛ Smoke واقعی
Worker در Docker فعلی اجرا نشده و Docker در حال حاضر روی Mock است. Deployment آنلاین،
اتصال Auth UI و تنظیم rates/secrets همچنان باقی‌اند.

## اسکلت انتخاب‌شده

ساختار تفصیلی فعلی را حفظ می‌کنیم؛ schema، models، migrations، contracts/generated types
و tests واقعی از درخت خلاصهٔ PDF حذف نمی‌شوند. بخش Agent اکنون qualification validation،
provider factory، cost، evaluation و تولید draft پاسخ on-demand دارد. Backend draft و
feedback را ذخیره می‌کند و analytics را از Usage ذخیره‌شده می‌سازد؛ پاسخ اجتماعی
به‌صورت خودکار ارسال نمی‌شود. UI همچنان مالکیت فاطیماست.
[راهنمای فایل‌ها](file-skeleton.md) وضعیت هر بخش را مشخص می‌کند.

[مقایسه و تصمیم‌ها](architecture-comparison.md) · [برنامه تیم](team-plan.md) ·
[برنامه ستایش](setayesh-plan.md) · [مرز AI](ai-engine.md)
