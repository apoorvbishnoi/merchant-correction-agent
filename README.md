# Merchant Correction Agent

An AI agent that fixes wrong merchant names on corporate-card transactions, with safety rules around every decision.
Course project for AI & GenAI Based Business, based on the public ZenML write-up of Ramp's
"AI Agent for Automated Merchant Classification Correction". The company, merchants and requests are
**fictional and synthetic**. None of Ramp's data or code is used.

Every decision in the app is a live call to a model (Google Gemini, Anthropic Claude or OpenAI), so the app needs your own API key.
The key is entered in the sidebar, lives only in that browser session and is never stored.

## What is in the app

| Tab | What it shows |
|---|---|
| Overview | The problem, the solution, headline numbers, the recommendation and how far to trust the numbers |
| Try a request | One of 40 prepared requests, or your own: the candidate merchants, the live decision, the safety checks and the message to the customer |
| Evaluation | The 40 hard test requests in ten situations, a rules-only baseline, a live test you can run, and the test results |
| Business case | Cost per request by hand, with rules, with the agent and with both; break-evens; editable assumptions |
| Rollout & success | Problem framing (TOSCAR), success criteria, a 12-week pilot plan with go/no-go gates, risks |
| How it works | The pipeline, every safety rule, the instructions given to the model, and what is real, synthetic or assumed |

## How it works

1. **Find candidates:** three searches (card-text similarity, name match, merchant names mentioned in the receipt, memos or note).
2. **Decide:** the live model picks one of four actions (create a merchant, update a record, move the transaction to another merchant, decline the correction) with a reason and a message for the customer.
3. **Safety rules** (plain code): the action and target must be valid, protected merchants cannot be edited, an update must change something, a new name must be on the card text or the receipt, a move to another city needs the receipt to name the merchant, a website must come from the request or the evidence, and more.
4. **Retry or hand over:** a failed rule sends the model back with the rule that broke; after three attempts a person takes over.

Declining a correction refuses the change to the merchant record. It never blocks the payment.

## Run it on your computer

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    streamlit run app.py

## Put it online (Streamlit Community Cloud)

1. Create a GitHub repository and upload everything in this folder, keeping the folder structure.
2. Go to share.streamlit.io, sign in with GitHub and choose **Create app**.
3. Pick the repository, branch `main` and main file `app.py`, then **Deploy**.

No secrets are needed. Do not save an API key in GitHub or in Streamlit Secrets; each visitor pastes their own key in the sidebar.

## Models

| Provider | Cost | Default model | Key from |
|---|---|---|---|
| Google Gemini | free tier, no card | `gemini-3.5-flash-lite` | aistudio.google.com/apikey |
| Anthropic Claude | paid (a Claude Pro subscription does not include API access) | `claude-haiku-5-5` | console.anthropic.com |
| OpenAI | paid | none: type a current model name from developers.openai.com/docs/models | platform.openai.com/api-keys |

The model name is under **Advanced** in the sidebar because providers add and remove models without notice.
Free tiers are rate-limited, so calls are spaced a few seconds apart, and a daily-allowance error stops a run with a clear message.
A provider outage is never counted as a wrong answer.

## Test results

Live test with Google Gemini `gemini-3.5-flash-lite` on its free tier, one run of each set:

| Test | Fully correct | Wrong change applied | Wrongly declined (safe) |
|---|---|---|---|
| 40 hard requests | 37 of 40 | 1 | 2 |
| 5 extra checks | 5 of 5 | 0 | 0 |
| 40 hard requests, rules only (no AI) | 0 of 40 | 29 | 11 |

How to read this: the 40 requests are deliberately hard, so the score is not a forecast for real traffic. Repeat runs differ by a request or two.
The safety rules and the instructions to the model were refined after reviewing test failures, so a rerun of the same 40 is a check, not a clean test.
The 5 extra checks were written afterwards by the same author. The test requests and the answer key are synthetic and hand-written.
Claude and OpenAI are supported but have not been tested. Larger paid models are expected to make fewer wrong decisions; that is an expectation, not a measurement.
Every money figure in the Business case is an assumption you can change.

## Synthetic data

- `data_gen.py` builds the 242 fictional merchants (`data/merchants.csv`).
- `data_gen_ai.py` writes the 40 test requests and their answer key (`data/requests.json`, `data/answer_key.json`).
- `data_gen_extra.py` writes the 5 extra checks (`data/extra_requests.json`, `data/extra_key.json`).

Running the generators again reproduces the data files exactly.

## What is not here

Real Ramp data, a real review queue, a response time measured at scale, measured repeat-correction rates, and live tests of the Anthropic or OpenAI paths.
