Place your chatbot knowledge file here:

- File name: `blood_donation_kb.xlsx`
- Sheet: first sheet only
- Required columns:
  - `question`
  - `answer`

Example:

| question | answer |
|---|---|
| Who can donate blood? | Healthy people typically aged 18-60 with minimum weight criteria can donate, based on screening. |
| What is the minimum gap between donations? | The system uses a 56-day minimum interval for eligibility checks. |

Optional:
- Set custom path using environment variable `CHATBOT_KB_PATH`.
