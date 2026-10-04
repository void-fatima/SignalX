# برنامهٔ مشترک پنج‌روزه و مالکیت

برنامهٔ پنج‌روزهٔ PDF جدید مرجع جاری است؛ برنامهٔ قبلی در docs/sources نگهداری شده.
روزها نسبی‌اند؛ این سند تاریخ/ساعت رسمی مسابقه را تأیید نمی‌کند.

| عضو | مالکیت اصلی | قدم بعدی |
| --- | --- | --- |
| رهام | API/DB/Auth/user ownership، schema/migration، services/worker، persistence، Docker/CI/Deploy/Release | Auth و جداسازی دادهٔ دو کاربر، تست PostgreSQL/Compose و deploy اولیه |
| ستایش | تمام Agent/provider/prompt/scoring/cost/evaluation/reply logic و AI docs | انتخاب provider/model، adapter واقعی با structured output و usage attempts |
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

وضعیت امروز: مسیر محلی Product→CSV→Mock worker→Lead/detail آماده است؛ Auth، آنلاین
شدن و provider واقعی آماده نیستند. این وضعیت گیت نهایی روز اولِ برنامهٔ جدید را کامل
نمی‌کند، چون Auth هنوز وجود ندارد. Cost/evaluation utility آماده است اما حسابداری و
ارزیابی واقعی انجام نشده‌اند. [وضعیت و کارهای ستایش](setayesh-plan.md)
