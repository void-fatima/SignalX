# ساختار فایل تکمیل‌شده

این مرحله ساختار فایل‌ها و مرزهای توسعه را کامل می‌کند، نه تمام قابلیت‌های MVP را.

| محدوده | فایل/پوشه | وضعیت |
| --- | --- | --- |
| Backend پایه | api/routes/main.py، core، db، models، schemas/api.py، services، worker، migrations | مسیر Mock قابل اجرا |
| Auth | app/auth/contracts.py، security.py، service.py، dependencies.py، api/routes/auth.py | register/login/logout/me، scrypt hash، نشست قابل ابطال و HttpOnly cookie پیاده شده؛ UI و deployment هنوز باقی |
| Draft/Feedback | schemas/response.py، services/response_service.py | typed contracts؛ persistence/endpoint هنوز آماده نیست |
| Analytics | schemas/analytics.py، services/analytics_service.py | typed contracts؛ query/aggregation هنوز آماده نیست |
| Agent | contracts/screening/context/qualification/scoring/pipeline/cost/evaluation | منطق پایه و تست‌ها آماده |
| Real provider | agents/providers/real.py | slot صریح fail-closed؛ factory هنوز فقط Mock |
| Prompt | agents/prompts/qualification.py، reply.py | builder مستقل؛ به provider واقعی متصل نشده |
| Reply | agents/reply.py | ورودی/خروجی و protocol؛ تولید واقعی هنوز آماده نیست |
| UI | products/imports/runs/leads و details | مسیر Mock موجود |
| Auth UI | app/login، app/register، components/AuthFormShell.tsx | shell غیرفعال؛ هیچ ورود یا guard صوری ندارد |
| Dashboard | app/dashboard/page.tsx | shell و لینک مسیر واقعی؛ analytics ساختگی ندارد |
| Evaluation data | data/evaluation/README.md | محل و قالب artifact؛ dataset/report واقعی بعداً ساخته می‌شود |
| قرارداد عمومی | contracts/openapi.json، examples، frontend/lib/generated | فقط endpointهای واقعاً موجود |
| CI | .github/workflows/ci.yml | تست backend، قراردادها، typecheck/build فرانت؛ اجرای GitHub هنوز انجام نشده |
| مستندات | architecture/api-contract/team-plan/setayesh-plan/ai-engine/evaluation/deployment/delivery/demo/verification | راهنمای توسعه و محدودیت‌ها |

Auth routes و migration واقعی 0002 به API متصل شده‌اند. Routeهای Response/Feedback/
Analytics و persistence آن‌ها هنوز پیاده نشده‌اند. AuthGuard و ارسال credentialed request
در UI با فاطیماست. سه عضو تیم از این فایل‌ها برای توسعه استفاده می‌کنند؛
docs/team-plan.md مالکیت را دارد.
