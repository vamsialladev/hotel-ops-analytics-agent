# Video script: Hotel Ops Analytics Agent (about 85 seconds)

How I talk in this one: like I'm showing it to someone on a call. Short sentences, contractions, a pause where
there's a `/`. Talk from the bullets, not word for word. One take with a small stumble is fine.

Before recording: the live app (or `streamlit run app.py`), awake, browser zoom 125%, role "analyst" in the
sidebar, a new conversation.

## Shot list

| Time | On screen | What I say |
|---|---|---|
| 0–10 s | The Ask tab, empty | A revenue manager told me a custom question costs her half a day of pivot tables. / So I built this: she just asks. / It's a simulated hotel group, and all the data's made up. |
| 10–30 s | Type input 1. The status shows the steps, the answer streams. Open "Steps", then the "SQL guard" step | Which room type earned the most at Mountain Lodge this year? / It writes one SQL query, / and before anything runs, a guard checks it. / Here's the guard's verdict: passed, read-only, these tables. / Then it runs, and I get the answer. |
| 30–45 s | Point at the "Sources" line, then open "SQL and result" | And here's where it came from. / The tables it read, and the revenue definition the hotel agreed on. / It didn't guess what revenue means. It looked it up. / And the SQL's right there if she wants to check. |
| 45–60 s | Type input 2. "Understood as" appears under it | Now a follow-up. / And at Beach Resort? / It works out I mean the same question for the other property, / shows me how it read it, and answers. |
| 60–75 s | Type input 3 (refused). Then the Daily anomalies tab on 2026-09-14 | If I ask for guest phone numbers as an analyst, it says no, / and even if the model slipped, the guard would stop it. / And every morning a check runs five rules. Here it caught a suite priced at fifty dollars instead of five hundred. / On my test questions it's ninety-nine percent right, for about thirty cents per thousand questions. |
| 75–85 s | New tab: the live URL loading | That's it. / It's live, the link's below, and so is the code. |

## Exact inputs

| # | Role | Type exactly |
|---|---|---|
| 1 | analyst | `Which room type at Mountain Lodge earned the most revenue in 2026?` |
| 2 | analyst | `And at Beach Resort?` |
| 3 | analyst | `Show me the phone numbers of guests who gave a score of 1.` |

Checked 2026-10-24 with the live model on a local run of this branch: input 1 is eval case q06 (passes 3/3); a
follow-up of the same shape ("And at Mountain Lodge?" after a Beach Resort revenue question) answered for
Mountain Lodge with "Understood as" shown; input 3 is eval case u02 (refused 3/3). The daily check on 2026-09-14
shows the Suite rate error. Type all three on the live app once it's deployed, before recording.

## LinkedIn caption (one sentence)

I built a text-to-SQL agent for a hotel's revenue manager that looks up the metric definitions before it writes
SQL, shows its steps and sources, handles follow-ups, and refuses writes and personal data.

## AI narration (used in docs/video/demo-ai-voice.mp4)

Until I record my own voice, the demo video (1:28) is narrated by an AI voice (Kokoro `af_heart`, local) and labelled "AI-narrated" on screen and here. It was recorded from the live app with Playwright; the captions are the narration, timed to the voice. `/` marks a pause.

| Step | Narration |
|---|---|
| intro | A revenue manager told me a custom question costs her half a day of pivot tables. / So I built this: she just asks. / It's a simulated hotel group, and all the data's made up. |
| ask | Which room type at Mountain Lodge earned the most this year? / It writes one SQL query, / and before anything runs, a guard checks it. / Here's the guard's verdict: read-only, and only these tables. |
| sources | And here's where the answer came from. / The tables it read, and the revenue definition the hotel agreed on. / It didn't guess what revenue means. It looked it up. / And the SQL's right there to check. |
| followup | Now a follow-up. / And at Beach Resort? / It works out I mean the same question for the other property, / shows me how it read it, and answers. |
| refuse | If I ask for guest phone numbers as an analyst, it says no, / and even if the model slipped, the guard would stop the query. |
| anomalies | Every morning a check runs five rules with no model at all. / Here it caught a suite priced at fifty dollars instead of about five hundred. |
| proof | On my test questions it gets ninety-nine percent right, / and every held-out one, / for about twenty-eight cents per thousand questions. |
| live | It's live, with no sign-in. / The link's below, and so is the code. |
