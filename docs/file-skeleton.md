# ساختار فایل تکمیل‌شده

این مرحله ساختار فایل‌ها و مرزهای توسعه را کامل می‌کند، نه تمام قابلیت‌های MVP را.

| محدوده | فایل/پوشه | وضعیت |
| --- | --- | --- |
| Backend پایه | api/routes/main.py، core، db، models، schemas/api.py، services، worker، migrations | مسیر Mock قابل اجرا |
| Auth | app/auth/contracts.py، security.py، service.py، dependencies.py، api/routes/auth.py | register/login/logout/me، scrypt hash، نشست قابل ابطال و HttpOnly cookie پیاده شده؛ UI و deployment هنوز باقی |
| Draft/Feedback | schemas/response.py، services/response_service.py | تولید on-demand از Agent، ویرایش/تأیید بدون ارسال، upsert بازخورد و ذخیره Usage آماده |
| Analytics | schemas/analytics.py، services/analytics_service.py | شمارش run، بازخورد و تجمیع Usage/هزینه با حفظ unknown/null آماده |
| Agent | contracts/screening/context/qualification/scoring/pipeline/cost/evaluation | منطق پایه و تست‌ها آماده |
| Real provider | agents/providers/real.py، gemini.py، factory.py | انتخاب صریح AvalAI/Gemini، validation و usage؛ Docker/Hosting برای real mode به متغیرهای server-side و Secret نیاز دارد |
| Prompt | agents/prompts/qualification.py، reply.py | builderهای qualification و reply به provider وصل‌اند |
| Reply | agents/reply.py | تولید draft on-demand و validation؛ ذخیره و endpoint سمت Backend |
| UI | products/imports/runs/leads و details | مسیر Mock موجود |
| Auth UI | app/login، app/register، components/AuthFormShell.tsx | shell غیرفعال؛ هیچ ورود یا guard صوری ندارد |
| Dashboard | app/dashboard/page.tsx | shell و لینک مسیر واقعی؛ analytics ساختگی ندارد |
| Evaluation data | data/evaluation/README.md | محل و قالب artifact؛ dataset/report واقعی بعداً ساخته می‌شود |
| قرارداد عمومی | contracts/openapi.json، examples، frontend/lib/generated | فقط endpointهای واقعاً موجود |
| CI | .github/workflows/ci.yml | تست backend، قراردادها، typecheck/build فرانت؛ اجرای GitHub هنوز انجام نشده |
| مستندات | architecture/api-contract/team-plan/setayesh-plan/ai-engine/evaluation/deployment/delivery/demo/verification | راهنمای توسعه و محدودیت‌ها |

Auth routes و migration واقعی 0002 به API متصل شده‌اند. Routeهای Response/Feedback/
Analytics و persistence آن‌ها اکنون پیاده شده‌اند. AuthGuard و ارسال credentialed request
در UI با فاطیماست. سه عضو تیم از این فایل‌ها برای توسعه استفاده می‌کنند؛
docs/team-plan.md مالکیت را دارد.
