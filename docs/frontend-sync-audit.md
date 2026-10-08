# گزارش هماهنگی فرانت‌اند و API

تاریخ بررسی: ۸ اکتبر ۲۰۲۶. پایهٔ UI:
`main@3078adfae2d1b299ec49d8b7015d1b274bf63485`.
قرارداد بازیابی:
`feat/failure-handling@96b7fa01da8dbadc1ba1af406938a218d7d351d2`.

شاخه‌های محلی و remote مربوط به auth، product profile، overview، import،
progress، inbox، dialog، business setup و Telegram بررسی شدند. کار قبلی UI
در main ادغام شده است. frontend سادهٔ شاخهٔ بک‌اند جایگزین UI فعلی نشد.
شاخهٔ failure-handling و main پس از `bea8e58` تاریخچه و migration متفاوت دارند؛
هیچ فایل بک‌اند، migration یا قرارداد اصلی تغییر نکرد.

## چک‌لیست نهایی

Complete در این جدول یعنی پیاده‌سازی فرانت‌اند و تست کنترل‌شده تکمیل شده است؛
اتصال واقعی به بک‌اند منتخب جداگانه Needs runtime verification است.

| Area | Requirement | Status | Branch/file evidence | Required action |
|---|---|---|---|---|
| Auth UI/API | Login/Register/Me/Logout با cookie | Complete | `ui-contract-sync`: `frontend/lib/api.ts`؛ فرم‌های auth موجود | بررسی cookie و Origin در محیط واقعی |
| Session | حفاظت صفحات خصوصی، انقضا، تغییر حساب و پاک‌سازی انتخاب‌ها | Complete | `ui-business-flow-sync` و اصلاح نهایی: `WorkspaceShell.tsx`، `workspace-session.ts`، `business-sync.spec.ts` | ندارد در UI |
| Product | ایجاد/ویرایش، فیلدهای ضروری، فرم خالی و حفظ optional fields | Complete | `product-profile.ts`، `useProductEditor.ts`، `products.spec.ts` | ندارد در UI |
| Product | همهٔ صفحات متعلق به حساب، انتخاب ذخیره‌شده و View | Complete | `allProducts` در `lib/api.ts`، `ProductDetails.tsx`، `business-sync.spec.ts` | بررسی ownership واقعی سرور |
| Workflow | Overview → Import → Select → Start → Progress → Leads | Complete | صفحات قبلی حفظ شدند؛ `imports.spec.ts`، `analysis.spec.ts` | بررسی worker واقعی جداگانه |
| Run UI/API | شش وضعیت، توقف polling در terminal، نمایش attempt | Complete | `useRunProgress.ts`، `RunRecovery.tsx` | attempt در بک‌اند قدیمی ناموجود می‌ماند |
| Failure UI/API | failed filter بدون decision/min_score، علت امن بدون score/decision | Complete | `ui-failure-recovery`: `useInbox.ts`، `AnalysisFailure.tsx`، `failure-recovery.spec.ts` | ندارد در UI |
| Retry UI/API | retry صریح با header و بدون body؛ حفظ کلید در نتیجه نامعلوم | Complete | `RunRecovery.tsx`، `recovery-intent.ts`، `failure-recovery.spec.ts` | اتصال به endpoint شاخهٔ تحویل |
| Telegram UI/API | منبع، chat/message/topic، evidence، generation، Save/Cancel و ارسال صریح | Complete | اجزای `components/telegram` حفظ شدند؛ تست‌های reply/delivery | هیچ ارسال واقعی در این بررسی انجام نشده |
| Delivery recovery | کلید اولیه و replay، کلید تازه برای retry عمدی، cooldown، قفل uncertain | Complete | `ui-telegram-reply-sync`: `useTelegramReview.ts`، `telegram-recovery.spec.ts` | نتیجه نامعلوم نیازمند تطبیق اپراتور است |
| CSV response | generation صریح، ذخیرهٔ متن، approval/rejection بدون ارسال | Complete | `ui-response-feedback-sync`: `PersistedReply.tsx`، `ReplyComposer.tsx`، `response-sync.spec.ts` | endpointهای main باید در بک‌اند منتخب موجود باشند |
| Feedback API | relevance boolean و comment با تأیید پاسخ سرور | Complete | `PersistedFeedback.tsx`، `ReplyFeedback.tsx`، `response-sync.spec.ts` | ندارد در UI |
| Feedback categories | نگاشت Useful/Needs context/Off-topic به relevance | Needs specification | قرارداد `FeedbackInput` فقط boolean دارد | تعریف نگاشت توسط محصول/قرارداد؛ فعلاً دسته‌های demo محلی‌اند |
| Overview analytics | نرخ relevance/coverage و هزینهٔ معلوم/ناقص | Complete | `useOverview.ts`، `dashboard/page.tsx`، `response-sync.spec.ts` | آمار approval و آخرین feedback در قرارداد analytics وجود ندارد |
| Settings | theme/density/direction در مرورگر | Complete | `PreferencesProvider.tsx`، `settings.spec.ts` | محلی باقی می‌ماند |
| Settings server | ذخیره تنظیمات حساب روی سرور | Needs specification | endpoint مستندی وجود ندارد | تعریف قرارداد؛ هیچ موفقیت سروری ساختگی نمایش داده نمی‌شود |
| Backend runtime | یک بک‌اند یکپارچه برای قراردادهای هر دو تاریخچه | Needs runtime verification | [منابع قرارداد فرانت‌اند](../frontend/contracts/README.md) | هماهنگی migration/auth/ownership توسط Roham و سپس smoke test محیط واقعی |

## رفتار حفظ‌شده و تغییرات

لوگو، shell، sidebar، رنگ‌ها، فونت، آیکون‌ها، dialog و responsive layout موجود
حفظ شدند. هیچ dependency یا طراحی موازی اضافه نشد. ورود به demo همچنان صریح
است و demo هیچ درخواست واقعی AI/Telegram ایجاد نمی‌کند. import validation و
شناسهٔ product انتخابی در شروع run حفظ شدند. تغییر product snapshot تحلیل‌های
قبلی را دست‌کاری نمی‌کند.

فهرست پروفایل‌ها تا آخر pagination بارگذاری می‌شود. پروفایل ناموجود ذخیره‌شده
پاک می‌شود؛ فرم جدید واقعی فیلدهای ضروری خالی دارد. View جزئیات از GET پروفایل
دریافت می‌کند و focus بعد از Escape به دکمهٔ آغازکننده برمی‌گردد.

کلید و متن دقیق ارسال تأییدشده قبل از POST در sessionStorage با scope حساب و
lead نگه داشته می‌شوند. نتیجه نامعلوم هرگز کلید تازه نمی‌گیرد. replay فقط با
کنترل صریح کاربر و metadata قرارداد جدید مجاز است؛ sending/sent/uncertain
قفل می‌مانند. پایان cooldown فقط کنترل را فعال می‌کند و هیچ POST خودکاری ندارد.
Save/Cancel متن Telegram محلی است؛ POST draft صرفاً با generation صریح و POST
reply صرفاً با approval/recovery صریح انجام می‌شود. تطبیق uncertain endpoint
خودکاری ندارد و به اپراتور نیاز دارد. guardهای قدیمی نتیجه نامعلوم نیز حفظ شدند.

برای CSV، متن و وضعیت در endpointهای response موجود روی main ذخیره می‌شوند.
ذخیرهٔ review هیچ پیام بیرونی ارسال نمی‌کند. بازخورد واقعی فقط دو گزینهٔ دقیق
Relevant/Not relevant و comment دارد؛ دسته‌های demo به boolean نگاشت نشده‌اند.
هزینهٔ دارای usage نامعلوم با «known portion» مشخص می‌شود؛ هزینهٔ ناموجود صفر
فرض نمی‌شود. تعداد approvalهای کل run، تاریخچهٔ کامل runها و آخرین feedback
endpoint مستند ندارند و برای حساب واقعی ساخته نمی‌شوند.

## شاخه‌ها و ترتیب ادغام پیشنهادی

همهٔ شاخه‌ها محلی‌اند و push نشده‌اند. main و origin/main روی `3078adf` باقی‌اند.

| شاخه | پایه | commitهای اصلی |
|---|---|---|
| `feat/ui-contract-sync` | `main@3078adf` | `4a0bd66` — snapshot و generated types، کلاینت cookie |
| `feat/ui-business-flow-sync` | `ui-contract-sync@4a0bd66` | `4f1768f` حفاظت نشست؛ `e1f230a` View و pagination؛ `472f07c` فرم خالی |
| `feat/ui-failure-recovery` | `ui-business-flow-sync@472f07c` | `75263c8` failed filter و retry؛ `0d34373` تست replay |
| `feat/ui-telegram-reply-sync` | `ui-failure-recovery@0d34373` | `472691f` intent/cooldown/recovery؛ `42b5a1e` تست‌های ایمنی |
| `feat/ui-response-feedback-sync` | `ui-telegram-reply-sync@42b5a1e` | `a7449a2` persistence/analytics؛ `56dde06` failed scoring؛ `ebd9f79` نشست و guard قدیمی؛ `30c25d2` اصلاح UI؛ `ae702d2` هزینه و پاسخ ناخوانا؛ `c2601c8` تست قراردادها؛ `8fcea5c` کارت هزینهٔ موبایل؛ commit گزارش در همین شاخه |

ترتیب جدول ترتیب وابستگی است. آخرین شاخه شامل کل stack است. برای فهرست دقیق
و کامل commitها: `git log --reverse --oneline main..feat/ui-response-feedback-sync`.
هیچ commit قبلی amend/squash یا تاریخچه‌ای بازنویسی نشد. `.vscode/` کاربر حفظ شد.

## تأیید

- `npm.cmd run typecheck` و `npm.cmd run build`: موفق.
- `npm.cmd test`: اجرای کامل ۱۱۵ تست موفق.
- تست‌های متمرکز auth/business/failure: ۱۶ تست موفق پس از اصلاح حفاظت نشست.
- `npm.cmd test -- telegram-recovery.spec.ts telegram-proxy.spec.ts failure-recovery.spec.ts`:
  ۸ تست موفق پس از اصلاح هزینهٔ حذف‌شده و حفظ کلید در پاسخ ناخوانا.
- `npm.cmd test -- failure-recovery.spec.ts`: ۳ تست موفق؛ شامل replay همان کلید
  بعد از پاسخ JSON ناخوانا با HTTP 422 و بعد از HTTP 502.
- `npm.cmd test -- response-sync.spec.ts overview.spec.ts`: ۶ تست موفق در build
  نهایی؛ شامل کارت هزینهٔ ناقص در موبایل. تصویر آن نیز بررسی شد.
- `npm.cmd run generate:api` و `npm.cmd run generate:handoff`: موفق، بدون diff
  در generated types. JSON snapshot با commit شاخهٔ تحویل برابر است.
- `backend/.venv/Scripts/python.exe -X utf8 scripts/export_openapi.py`: موفق؛
  قرارداد اصلی بدون diff ماند.
- `git diff --check`: موفق.
- `npm.cmd run lint`: اجرا شد و با `Missing script: "lint"` قابل اجرا نبود؛
  اسکریپت یا تنظیم ESLint در ریپو وجود ندارد.
- تصاویر desktop/mobile برای پروفایل، failed leads، Telegram recovery و
  پاسخ/بازخورد بررسی شدند. تست‌های keyboard، focus و عدم overflow موفق‌اند.
- تست backend در این کار دوباره اجرا نشد؛ منطق backend تغییر نکرده است.
  تست‌های UI از پاسخ‌های HTTP کنترل‌شده و fake server محلی استفاده می‌کنند.

هیچ پیام Telegram، درخواست provider پولی، deployment، push یا merge به main
انجام نشد. cookie/CORS واقعی، worker/DB، ارسال واقعی و هماهنگی دو تاریخچهٔ
بک‌اند در این بررسی تأیید نشده‌اند و همچنان Needs runtime verification هستند.
