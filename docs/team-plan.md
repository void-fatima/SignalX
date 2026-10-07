# برنامهٔ مشترک پنج‌روزه و مالکیت

برنامهٔ پنج‌روزهٔ PDF جدید مرجع جاری است؛ برنامهٔ قبلی در docs/sources نگهداری شده.
روزها نسبی‌اند؛ این سند تاریخ/ساعت رسمی مسابقه را تأیید نمی‌کند.

| عضو | مالکیت اصلی | قدم بعدی |
| --- | --- | --- |
| رهام | API/DB/Auth/user ownership، schema/migration، services/worker، persistence، Docker/CI/Deploy/Release | response/feedback/analytics، PostgreSQL verification و آماده‌سازی release candidate |
| ستایش | تمام Agent/provider/prompt/scoring/cost/evaluation/reply logic و AI docs | ارزیابی Agent و هماهنگی rate/provider تنظیم‌شده برای اجرای live |
| فاطیما | تمام Frontend/UI/UX، Auth UI، client API، demo/pitch/screenshots | Auth UI و guard، smoke مرورگر مسیر Mock و حالات خطا/empty/loading |

فاطیما مالک تمام UI است؛ رهام و ستایش UI جدید نمی‌سازند. ستایش انتخاب context و
منطق هزینه را می‌نویسد؛ رهام query، ذخیره usage و aggregation را انجام می‌دهد.
رهام مالک OpenAPI است؛ تغییر schema با هر سه نفر و regenerate types/fixtures هماهنگ می‌شود.

| روز | رهام | ستایش | فاطیما | گیت مشترک |
| --- | --- | --- | --- | --- |
| 1 | Auth/User + product/API/schema | contracts/Mock/scoring/fixture | layout/Auth/Product/Dashboard shell | ثبت‌نام → ورود → محصول → Mock → نتیجه |
| 2 | CSV/run/worker/context query + deploy | context-aware screening/context + real adapter/validation | import/progress/list/states | نسخهٔ آنلاین مسیر Mock |
| 3 | real persistence/usage، timeout/partial/idempotency/ownership | prompt/guards/qualification/evidence + usage/budget | detail/context/evidence/Mock-Real/partial | 20–30 پیام با provider واقعی، نتیجه قابل مشاهده |
| 4 | response/feedback/analytics/cost persistence/restart + release candidate | grounded reply/cost/dev tuning/test evaluation | reply/feedback/cost cards/responsive/demo | freeze کامل پایان روز 4 |
| 5 | blocker/clean checkout/production/release | AI claims + metrics/cost/limitations/examples/docs | مرورگر QA/screenshots/pitch/video | اجرای مستقل مسیر داوری و تحویل |

وضعیت checkout فعلی: مسیر Product→CSV→Worker→Agent→PostgreSQL در Mock با smoke بیست
پیامی تأیید شد؛ response draft، feedback و analytics هم در Backend پیاده شده‌اند.
Auth/session و user scope در Backend هستند. UI/auth integration با فاطیماست. Adapter
واقعی سمت Agent موجود است اما Docker فعلی روی Mock است و live Worker smoke هنوز تأیید
نشده. Deployment آنلاین و انتخاب نرخ/budget policy باقی‌اند.
[وضعیت و کارهای ستایش](setayesh-plan.md)
