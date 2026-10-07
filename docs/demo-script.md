# Mock demo

1. Open http://localhost:3000, create an account or log in, and choose Business setup.
2. Enter a demo backend-course profile explicitly; the form has no demo defaults.
3. Select it, upload data/demo_messages.csv with a community name.
4. Start Mock analysis; observe queue/running/processed counts from the worker.
5. Open results, inspect the explicit Persian course request (score 84), then
   the price objection that uses the same conversation. Open the ignore filter
   to inspect screening and technical/no-purchase examples.
6. Open a result's original message, signals, evidence, limitations and offline
   context. Check Persian and English text direction.
7. Reimport the same bytes and community: the existing batch is reused.

All output is deterministic Mock data. Cost is zero Mock cost, not measured AI
savings. Replies, feedback, real AI and performance metrics are not in this demo.
