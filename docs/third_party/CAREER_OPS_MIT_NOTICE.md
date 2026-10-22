# Source notice — career-ops follow-up cadence

SmartPloy SP23 adapts selected **MIT-licensed** constants and scheduling branches
from the existing career-ops project. It does not import career-ops' Next.js,
Node runtime, application tracker, CLI or mailbox access.

- Upstream repository: https://github.com/career-ops-hq/career-ops
- Pinned source revision: `dff9703a092e2872245aef09b096edcee054ac69`
- Adapted file: `followup-cadence.mjs`, notably `DEFAULT_CADENCE` and
  `computeNextFollowupDate`
- Target: `smartploy/application_followups.py`
- Additional original SmartPloy logic: owner-scoped Postgres lifecycle binding,
  source-of-truth workspace submission gate, in-app-only candidate reminders,
  bounded maximum recorded follow-ups, outcome closure, action auditing and API.
- Adaptation constraint: measured source fit only. An upstream `follow-up` does
  **not** mean SmartPloy emailed anyone. In SmartPloy, any logged send is an
  explicitly user-reported event without independent delivery verification.

## MIT license and attribution

MIT License

Copyright (c) 2026 Santiago Fernández de Valderrama

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
