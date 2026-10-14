"""Merchant Correction Agent - course project demo (Streamlit).

Fictional Indian corporate-card company, synthetic data. Based on the public ZenML write-up of Ramp's
"AI Agent for Automated Merchant Classification Correction". Not Ramp's data or code.
Every decision shown in this app is a live call to a model API (Gemini, Claude or OpenAI) that needs the user's own key.
"""
import hashlib
import json

import pandas as pd
import streamlit as st

from agent import decide, guardrails
from agent.config import ACTIONS, CASE_LABELS, CATEGORIES, FAMILIES, PROVIDERS, RESULTS
from agent.custom import MCC_OPTIONS, make_item
from agent.decide import LiveCallError, run_agent, run_baseline
from agent.evaluate import OUTCOMES, evaluate, evaluate_baseline, load_extra, load_items, load_key, score
from agent.impact import DEFAULTS, compute, inr, sensitivity, vs_rules, wilson_low
from agent.retrieval import Retriever, evidence_text, load_merchants

st.set_page_config(page_title="Merchant Correction Agent", page_icon="💳", layout="wide",
                   menu_items={"Get help": None, "Report a bug": None,
                               "About": "Merchant Correction Agent. A course project on a fictional card company, with synthetic data."})
st.markdown(
    "<style>.block-container{padding-top:2rem;max-width:1180px}"
    "h1{font-size:1.85rem!important;font-weight:650!important;letter-spacing:-.01em}"
    "h2,h3{font-weight:620!important}"
    "[data-testid=stMetric]{border:1px solid #e3e7ee;border-radius:10px;padding:10px 14px;background:#fafbfd}"
    "[data-testid=stMetricValue]{font-size:1.55rem}"
    ".stAppDeployButton,[data-testid=stAppDeployButton],[data-testid=stMainMenu],#MainMenu,footer{display:none!important}</style>", unsafe_allow_html=True)

ACTION_COLOR = {"create": "green", "update": "blue", "reassign": "orange", "reject": "red"}
ACTION_TEXT = {"create": "Create a new merchant", "update": "Update the merchant record",
               "reassign": "Move the transaction to another merchant", "reject": "Decline the correction"}
OK, NO = "✓ ", "✗ "


def esc(x) -> str:
    """Escape text so Streamlit's markdown shows it literally."""
    out = str(x)
    for ch in ("\\", "*", "_", "~", "$", "[", "]", "#", "|", "`"):
        out = out.replace(ch, "\\" + ch)
    return out


@st.cache_resource
def load_all():
    merchants = load_merchants()
    retriever = Retriever(merchants)
    items, key = load_items(), load_key()
    f_items, f_key = load_extra()
    return merchants, retriever, items, key, f_items, f_key, evaluate_baseline(retriever, merchants, items, key)


merchants, retriever, items, key, extra_items, extra_key, base = load_all()
by_id = merchants.set_index("id")
key_all = {**key, **extra_key}
item_by_id = {it["request"]["request_id"]: it for it in items + extra_items}
B, bm = base["baseline"], base["baseline_metrics"]
N_REQ = len(items)
imp = compute(DEFAULTS)
RM, RE = RESULTS["main"], RESULTS["extra"]


def first_of(family, action):
    return next(r_ for r_, k_ in key.items() if k_["scenario"] == family and k_["action"] == action)


FEATURED = [("Note says what it is NOT", first_of("negated_claim", "reassign")),
            ("Announced for later, not true yet", first_of("future_or_rumour", "reject")),
            ("Instruction hidden in a receipt", first_of("hidden_instruction", "reassign"))]
QUICK_IDS = [next(r_ for r_, k_ in key.items() if k_["scenario"] == f_) for f_ in FAMILIES]

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("Live model")
    provider = st.selectbox("Provider", list(PROVIDERS), format_func=lambda p_: PROVIDERS[p_]["label"])
    cfg = PROVIDERS[provider]
    api_key = st.text_input(f"{cfg['short']} API key", type="password", key=f"key_{provider}",
                            help="Used only for this browser session and never stored.")
    st.caption(f"Create a key at {cfg['key_page']}. Delete it when you are done.")
    with st.expander("Advanced: model name"):
        model = st.text_input("Model name", value=cfg["model"], key=f"model_{provider}",
                              placeholder="Type a current model name" if not cfg["model"] else "",
                              help="Providers add and remove models without notice. If one says it does not know the name, "
                                   "pick another from its list and type it here.").strip()
        if provider == "openai":
            st.caption(f"Current names: {cfg['models_page']}")
    ready = bool(api_key) and bool(model)
    st.caption("Ready: every decision is a live call." if ready else "Add a key to run the agent.")
    if cfg["gap"]:
        st.caption(f"Free tiers are rate-limited, so calls are spaced about {cfg['gap']:g} seconds apart.")
    st.divider()
    st.caption("The test results were measured with Google Gemini (gemini-3.5-flash-lite) on its free tier. "
               "Claude and OpenAI are supported but have not been tested.")
    st.caption("Fictional company, synthetic data. AI & GenAI Based Business course project.")

st.title("💳 Merchant Correction Agent")
st.caption("An AI agent that fixes wrong merchant names on corporate-card transactions. Every decision is a live model call, "
           "checked by fixed safety rules before anything changes.")

tab_over, tab_try, tab_eval, tab_impact, tab_roll, tab_how = st.tabs(
    ["Overview", "Try a request", "Evaluation", "Business case", "Rollout & success", "How it works"])

# ---------------------------------------------------------------- overview
with tab_over:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("The problem")
        st.markdown(
            "A company card shows each purchase under a **merchant record**: a name, a category and a website. Card networks send messy text "
            "such as `ECOM*MEHTA BAZAAR MUM`, so records are often wrong. Customers ask for corrections, and today **a person reads each one**. "
            "In Ramp's published write-up, staff could handle only about **1.5% of requests in 2024**, and each fix took hours of support and engineering time.")
    with c2:
        st.subheader("The solution")
        st.markdown(
            "An agent reads the request and the evidence on the transaction, looks up similar merchants, and picks **one of four actions**: "
            "create a merchant, update a record, move the transaction to another merchant, or decline the correction. "
            "Fixed safety rules check every answer. If they fail, the agent retries; if it still fails, a person takes over.")

    w1, w2 = st.columns(2)
    with w1:
        st.markdown("**Who is who**")
        st.markdown(
            "- **The card company** (fictional) issues company cards and software to track spending.\n"
            "- **Its customer** is a company whose staff and finance team flag mistakes.\n"
            "- **Merchants** are the shops, hotels and vendors the cards are used at, kept in a master list.\n"
            "- **Card networks** only carry the messy card text.")
    with w2:
        st.markdown("**How a request reaches the agent**")
        st.markdown(
            "1. A card is used and an automatic matcher links it to a merchant (not built here).\n"
            "2. Someone at the customer sees the wrong merchant and submits a correction with a note.\n"
            "3. The agent reads it with the evidence on the transaction and picks an action; safety rules check it.\n"
            "4. The customer gets the result in plain language.")
    st.caption("A declined correction never blocks the payment. It only refuses the change to the merchant record.")

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Per request, by hand", inr(imp["manual_req"]))
    k2.metric("Per request, agent (all-in)", inr(imp["allin_req"]), f"-{imp['reduction']:.0%}", delta_color="off",
              help="Model, human review, rework of wrong decisions, the run team and the build cost spread over 24 months. Assumptions, editable in the Business case tab.")
    k3.metric("Live test, fully correct", f"{RM['correct']} of {RM['n']}",
              help=f"One live run of the {RM['n']} hard test requests with Gemini on its free tier. "
                   f"Only {RM['wrong_change']} wrong change was applied. Repeat runs differ by a request or two. Run it yourself in the Evaluation tab.")
    k4.metric("Rules-only baseline (no AI)", f"{int(B['full_ok'].sum())} of {N_REQ}",
              help=f"Fully right. {int(B['action_ok'].sum())} of {N_REQ} on the action alone. Computed live from the same requests.")
    st.success(
        f"**Recommendation: run a 12-week pilot, do not switch it on for everyone.** On the Business case assumptions the agent costs about "
        f"{inr(imp['allin_req'])} per request against {inr(imp['manual_req'])} by hand. Against rules for the easy requests and people for the rest, the agent is cheaper only once "
        f"more than {imp['break_even_hard_share']:.0%} of requests need reading. The pilot decides what that share really is. "
        "Plan and gates are in the Rollout & success tab.")
    st.info(
        "**Read this before quoting any number.** The company, merchants and requests are synthetic. The model results come from a free-tier, "
        "small, low-cost model (Gemini flash-lite). Larger paid models from Anthropic or OpenAI are expected to make fewer wrong decisions, "
        "because the misses we saw were errors of judgement (for example, treating two vendors on one payment as one), not of reading. That is an expectation, not a measurement. "
        "The test set is deliberately hard and has few requests, so its score is not a forecast for real traffic. "
        "The How it works tab lists what is real, what is synthetic and what is assumed.")

# ---------------------------------------------------------------- try a request
def show_request(it, rid, custom=False):
    """Show one request, run the agent on it, and display candidates, decision, rules and message."""
    t, r = it["txn"], it["request"]
    left, right = st.columns(2)
    with left, st.container(border=True):
        st.markdown("**The transaction**")
        st.markdown(
            f"Card text: `{t['card_acceptor_name']}`  \n"
            f"₹{t['amount_inr']:,}  ·  {t['date']}  ·  {esc(t['city'])}  \n"
            f"Merchant code: {t['mcc']} ({esc(t['mcc_description'])})  \n"
            f"Receipt: {esc('; '.join(t['receipt_lines'])) or 'none'}  \n"
            "Currently shown as: " + (f"**{esc(by_id.loc[t['currently_mapped_merchant_id'], 'name'])}**"
                                      if t["currently_mapped_merchant_id"] else "no merchant"))
        if it["related_memos"]:
            st.markdown("Memos: " + esc(" | ".join(it["related_memos"])))
    with right, st.container(border=True):
        st.markdown(f"**The customer's request** (from {esc(r['submitted_by'])})")
        st.markdown(f"Merchant name: **{esc(r['proposed_name']) or 'none typed'}**  \n"
                    f"Website: {esc(r['proposed_website']) or 'not given'}  ·  Category: {esc(r['proposed_category'])}")
        st.markdown("Note:")
        st.text(r["note"] or "(none)")

    out = None
    uid = hashlib.md5(json.dumps(it, sort_keys=True).encode()).hexdigest()[:8]
    sk = f"live_{rid}_{provider}_{model}_{uid}"
    if not ready:
        st.warning(f"Add a {cfg['short']} API key (and a model name for OpenAI) in the sidebar to run the agent on this request.")
    elif st.button("Run the agent on this request", type="primary", key=f"run_{sk}"):
        try:
            with st.spinner(f"Asking {cfg['short']} ({model})..."):
                st.session_state[sk] = run_agent(it, retriever, "live", None, api_key, model, provider)
        except LiveCallError as e:
            st.error(str(e))
        except Exception as e:  # network, key or model problem we did not anticipate
            st.error(f"The live call failed: {type(e).__name__}: {e}")
    out = st.session_state.get(sk)

    cands = out["candidates"] if out else retriever.candidates(
        t["card_acceptor_name"], r["proposed_name"], t["currently_mapped_merchant_id"], evidence_text(it))
    with st.container(border=True):
        st.markdown("**Step 1. Candidate merchants found**")
        st.dataframe(pd.DataFrame([{"ID": c["id"], "Merchant": c["name"], "Category": c["category"], "City": c["city"],
                                    "Protected": "yes" if c["established"] else "", "Found by": c["via"]} for c in cands]),
                     hide_index=True, width="stretch")
        st.caption("Three searches run together: card-text similarity, name matching, and merchant names mentioned in the receipt, memos or note. "
                   "Finding a name does not say what it means: 'not Pillai Dhaba' finds Pillai Dhaba too.")

    if out is not None:
        final = out["final"]
        d1, d2 = st.columns([1.2, 1])
        with d1:
            st.markdown("**Step 2. The agent's decision**")
            if out["status"] == "escalated":
                st.error("Handed to a person: the agent could not produce an answer that passed the safety rules.")
            else:
                st.badge(ACTION_TEXT.get(final.get("action"), str(final.get("action"))), color=ACTION_COLOR.get(final.get("action"), "gray"))
                tid = final.get("target_merchant_id")
                if tid and tid in by_id.index:
                    st.markdown(f"Target: **{esc(by_id.loc[tid, 'name'])}** ({tid})")
                if final.get("fields"):
                    st.markdown("Fields: " + ", ".join(f"{k} = **{esc(v)}**" for k, v in final["fields"].items() if v))
                st.markdown("Reason:")
                st.text(final.get("reason", ""))
            st.caption(f"Attempts: {len(out['attempts'])}  ·  live call to {PROVIDERS[out['provider']]['short']} ({out['model']})  ·  {out['seconds']} s")
        with d2:
            st.markdown("**Step 3. Safety rules on the final answer**")
            for c in out["attempts"][-1]["checks"]:
                st.markdown((OK if c["passed"] else NO) + esc(c["rule"]))
                if not c["passed"]:
                    st.caption(c["detail"])
            if len(out["attempts"]) > 1:
                first_bad = [v["rule"] for v in out["attempts"][0]["violations"]]
                st.caption("The first answer was sent back for: " + "; ".join(first_bad))
        st.markdown("**Step 4. Message to the customer**")
        st.success(out["user_message"])

        if not custom:
            with st.expander("Compare with the expected answer"):
                k = key_all[rid]
                st.markdown(f"Situation: **{CASE_LABELS.get(k['scenario'], k['scenario'])}**  ·  expected action: **{ACTION_TEXT[k['action']]}**")
                if k.get("target"):
                    st.markdown(f"Expected target: {esc(by_id.loc[k['target'], 'name'])} ({k['target']})")
                if k.get("fields"):
                    st.markdown("Expected fields: " + ", ".join(f"{a} = {esc(b)}" for a, b in k["fields"].items()))
                _, f_ok = score(out["final"], k) if out["status"] != "escalated" else (False, False)
                st.markdown("Agent matched the expected answer: " + ("**yes**" if f_ok else "**no**"))
                b_dec = run_baseline(it, retriever)["final"]
                st.markdown(f"The rules-only baseline chose **{b_dec.get('action')}**: " + ("correct" if score(b_dec, k)[1] else "wrong"))

    with st.expander("See the safety rules catch a bad answer"):
        st.caption("Write a decision yourself for this request and see which rules catch it. This needs no API key. A failed rule sends the agent back for another "
                   "attempt, and after three failed attempts the request goes to a person.")
        base_dec = (out["final"] if out is not None and out["status"] != "escalated" else {}) or {}
        with st.form(f"tester_{rid}"):
            f1, f2 = st.columns(2)
            act = f1.selectbox("Action", ACTIONS, format_func=lambda a: ACTION_TEXT[a],
                               index=ACTIONS.index(base_dec["action"]) if base_dec.get("action") in ACTIONS else 0)
            tgt_opts = ["(none)"] + [c["id"] for c in cands] + ["M0000 (not a real merchant)"]
            cur = base_dec.get("target_merchant_id")
            tgt = f2.selectbox("Target merchant", tgt_opts, index=tgt_opts.index(cur) if cur in tgt_opts else 0,
                               format_func=lambda x: x if x in ("(none)", "M0000 (not a real merchant)") else f"{x} · {by_id.loc[x, 'name']}")
            g1, g2, g3 = st.columns(3)
            nm = g1.text_input("New name", value=(base_dec.get("fields") or {}).get("name", ""))
            ws = g2.text_input("Website", value=(base_dec.get("fields") or {}).get("website", ""))
            ct_opts = ["(none)"] + CATEGORIES + ["Crypto Trading"]
            cat0 = (base_dec.get("fields") or {}).get("category")
            cat = g3.selectbox("Category", ct_opts, index=ct_opts.index(cat0) if cat0 in ct_opts else 0)
            rs = st.text_input("Reason", value="Test reason")
            um = st.text_input("Message to customer", value="Test message")
            go = st.form_submit_button("Check these rules", type="primary")
        if go:
            target = None if tgt == "(none)" else ("M0000" if tgt.startswith("M0000") else tgt)
            dec = {"action": act, "target_merchant_id": target,
                   "fields": {k_: v for k_, v in (("name", nm), ("website", ws), ("category", "" if cat == "(none)" else cat)) if v},
                   "reason": rs, "user_message": um}
            res = guardrails.check(dec, cands, it)
            for c in res:
                st.markdown((OK if c["passed"] else NO) + esc(c["rule"]) + ("" if c["passed"] else f" , {esc(c['detail'])}"))
            if guardrails.violations(res):
                st.error("Blocked. The agent would be sent back to try again.")
            else:
                st.success("All rules pass. This decision would be applied.")


with tab_try:
    src = st.radio("What do you want to try?", ["A prepared request", "Type your own request"], horizontal=True)
    if src == "A prepared request":
        fam_by_id = {r_: k_["scenario"] for r_, k_ in key.items()}
        extra_ids = [it_["request"]["request_id"] for it_ in extra_items]
        FILTERS = [f"All {N_REQ}"] + [f"{CASE_LABELS[f_]} ({sum(1 for v_ in fam_by_id.values() if v_ == f_)})" for f_ in FAMILIES] \
            + [f"Extra checks ({len(extra_ids)})"]
        st.session_state.setdefault("fam_filter", FILTERS[0])
        st.selectbox("Show", FILTERS, key="fam_filter", help="The prepared requests are grouped by the kind of language problem that decides the answer.")
        fam_order = {f_: n_ for n_, f_ in enumerate(FAMILIES)}
        all_ids = sorted((it_["request"]["request_id"] for it_ in items), key=lambda i_: (fam_order[fam_by_id[i_]], i_))
        test_no = {i_: n_ for n_, i_ in enumerate(all_ids, 1)}
        sel = FILTERS.index(st.session_state["fam_filter"])
        if sel == 0:
            ids = all_ids
        elif sel == len(FILTERS) - 1:
            ids = extra_ids
        else:
            ids = [i_ for i_ in all_ids if fam_by_id[i_] == list(FAMILIES)[sel - 1]]

        def label(rid_):
            it_ = item_by_id[rid_]
            typed_ = it_["request"]["proposed_name"] or "no name typed"
            no_ = f"{test_no[rid_]:02d}" if rid_ in test_no else rid_.replace("EXTRA-", "X")
            return f"{no_}  ·  {rid_}  ·  {CASE_LABELS[key_all[rid_]['scenario']]}  ·  asks for “{typed_}”  ·  card text {it_['txn']['card_acceptor_name']}"

        st.session_state.setdefault("req_pick", FEATURED[0][1])
        if st.session_state["req_pick"] not in ids:
            st.session_state["req_pick"] = ids[0]

        def pick(r_):
            st.session_state["fam_filter"] = FILTERS[0]
            st.session_state["req_pick"] = r_

        st.caption("Start with one of these, or choose any request below.")
        for col_, (txt_, r_) in zip(st.columns(len(FEATURED)), FEATURED):
            col_.button(f"{txt_} ({r_})", on_click=pick, args=(r_,), width="stretch")
        rid = st.selectbox("Prepared requests", ids, format_func=label, key="req_pick")
        show_request(item_by_id[rid], rid)
    else:
        st.caption("Describe a transaction and what the customer is asking for. The search and the safety rules run on whatever you enter, "
                   "and the live model makes the decision.")
        merchant_ids = ["(none)"] + list(merchants["id"])
        with st.form("own_request"):
            st.markdown("**The transaction**")
            c1_, c2_, c3_ = st.columns(3)
            card_text = c1_.text_input("Card text on the statement", value="POS DEEPAK SWEETS 2291")
            mcc_pick = c2_.selectbox("Merchant category code", [c for c, _ in MCC_OPTIONS], format_func=lambda c: f"{c} · {dict(MCC_OPTIONS)[c]}")
            c3_a, c3_b = c3_.columns(2)
            city = c3_a.text_input("City", value="Pune")
            amount = c3_b.number_input("Amount (₹)", min_value=1, value=840, step=10)
            d1_, d2_ = st.columns(2)
            receipts_txt = d1_.text_area("Receipt lines (one per line)", value="Mithai box x2\nGST 5%", height=90)
            memos_txt = d2_.text_area("Memos on related transactions (one per line, optional)", value="", height=90)
            mapped = st.selectbox("Currently shown as", merchant_ids, format_func=lambda x: x if x == "(none)" else f"{x} · {by_id.loc[x, 'name']}")
            st.markdown("**The customer's request**")
            e1_, e2_, e3_ = st.columns(3)
            nm_ = e1_.text_input("Merchant name they typed", value="Deepak Sweets")
            ws_ = e2_.text_input("Website (optional)", value="")
            ct_ = e3_.selectbox("Category they chose", CATEGORIES, index=CATEGORIES.index("Meals & Restaurants"))
            note_ = st.text_area("Their note", value="Card shows a code, this is a sweet shop we buy from every month.", height=80)
            go_ = st.form_submit_button("Use this request", type="primary")
        if go_:
            st.session_state["custom_item"] = make_item(card_text, mcc_pick, city, amount, receipts_txt,
                                                        None if mapped == "(none)" else mapped, nm_, ws_, ct_, note_, memos_txt)
        if st.session_state.get("custom_item"):
            show_request(st.session_state["custom_item"], "CUSTOM", custom=True)
        else:
            st.info("Fill in the form and press the button. The example is a business that is not in the merchant list.")

# ---------------------------------------------------------------- evaluation
with tab_eval:
    st.subheader("How well does it work?")
    st.markdown(
        f"**The test:** {N_REQ} correction requests in ten kinds of situation where the deciding evidence is free text (a note, a memo or a receipt line) "
        "and the structured fields are vague or misleading. A no-AI baseline is expected to do badly on these by construction. "
        "Declining a correction never blocks the payment; it only refuses the change.")

    st.markdown("**Run it live**")
    if not ready:
        st.info("Add a key in the sidebar to run the live evaluation.")
    else:
        live_opts = [f"Quick check: one request from each of the {len(QUICK_IDS)} situations", f"All {N_REQ} requests",
                     f"Extra checks: {len(extra_items)} more requests"]
        scope = st.radio("Which requests", live_opts, horizontal=True, key="live_scope")
        run_items = ([it_ for it_ in items if it_["request"]["request_id"] in set(QUICK_IDS)] if scope == live_opts[0]
                     else items if scope == live_opts[1] else extra_items)
        lo_m, hi_m = len(run_items) * (cfg["gap"] + 0.5) / 60, len(run_items) * (cfg["gap"] + 4) / 60
        st.caption(f"{len(run_items)} requests with {cfg['short']} ({model}): about {max(1, round(lo_m))} to {max(2, round(hi_m))} minutes. Keep this tab open.")
        if st.button("Run live evaluation", type="primary", key="live_eval_btn"):
            bar = st.progress(0.0, text="Starting...")

            def _progress(done, total, rid_):
                bar.progress(done / total, text=f"Request {done + 1 if rid_ else done} of {total} {('(' + rid_ + ')') if rid_ else ''}")

            try:
                res_ = evaluate(retriever, merchants, run_items, key_all, {}, mode="live", api_key=api_key,
                                provider=provider, model=model, progress=_progress)
                res_["label"] = f"{cfg['short']} · {model} · {scope.split(':')[0].lower()}"
                st.session_state["live_eval"] = res_
            except LiveCallError as e:
                st.error(str(e))
            except Exception as e:
                st.error(f"The live run failed: {type(e).__name__}: {e}")
            bar.empty()

    le = st.session_state.get("live_eval")
    if le:
        A, lm, lb = le["agent"], le["metrics"], le["baseline_metrics"]
        st.markdown(f"**Last live run:** {le['label']}")
        if le["stopped"]:
            st.warning(f"{le['stopped']}  \nResults cover the {lm['n']} requests that ran; the other {le['not_run']} were not run and are not counted as wrong.")
        l1, l2, l3, l4, l5 = st.columns(5)
        l1.metric("Fully correct", f"{lm['full_acc']:.1%}", help=f"{int(A['full_ok'].sum())} of {lm['n']} requests.")
        l2.metric("Rules-only baseline", f"{lb['full_acc']:.1%}", help="Same requests, no AI.")
        l3.metric("No wrong change applied", f"{lm['no_wrong_change']:.1%}",
                  help="Correct answers, plus requests wrongly declined or handed to a person. Only a wrong change that was applied counts against it.")
        l4.metric("Protected records edited", lm["protected_edits_accepted"], help="Should be 0.")
        l5.metric("Retried / handed over", f"{lm['retried']} / {lm['escalated']}")
        oc = pd.DataFrame({"Live model": A["outcome"].value_counts().reindex(OUTCOMES, fill_value=0),
                           "Rules-only baseline": le["baseline"]["outcome"].value_counts().reindex(OUTCOMES, fill_value=0)})
        oc.index.name = "What the answer did"
        st.table(oc)
        order = {c_: n_ for n_, c_ in enumerate(list(FAMILIES) + ["extra_check"])}
        sit = A.groupby("case type")["full_ok"].agg(["sum", "count"]).join(le["baseline"].groupby("case type")["full_ok"].sum().rename("base"))
        sit = sit.reset_index().assign(o=lambda d: d["case type"].map(order)).sort_values("o")
        st.dataframe(pd.DataFrame({"Situation": sit["case type"].map(CASE_LABELS), "Requests": sit["count"],
                                   "Live model correct": sit["sum"].astype(int), "Baseline correct": sit["base"].astype(int)}),
                     hide_index=True, width="stretch")
        st.caption(f"Average {A['seconds'].mean():.1f} s per request, including the pause the app adds for free tiers.  ·  "
                   f"With {lm['n']} requests the 95% confidence floor on accuracy is about {wilson_low(int(A['full_ok'].sum()), lm['n']):.0%}. "
                   "Answers can differ between runs, so treat one run as a signal.")
        miss = A[~A["full_ok"]].copy()
        if len(miss):
            miss["Situation"] = miss["case type"].map(CASE_LABELS)
            miss["Answer"] = miss.apply(lambda r_: f"{r_['agent']}" + (f" → {by_id.loc[r_['target'], 'name']}" if isinstance(r_["target"], str) and r_["target"] in by_id.index else "")
                                        + (f" ({r_['fields']})" if r_["fields"] else ""), axis=1)
            st.markdown("Requests it got wrong:")
            st.dataframe(miss[["request_id", "Situation", "expected", "Answer", "outcome", "reason"]], hide_index=True, width="stretch")

    st.markdown("**Test results**")
    st.dataframe(pd.DataFrame([
        {"Test": f"{RM['n']} hard requests", "Fully correct": f"{RM['correct']} of {RM['n']}", "Wrong change applied": RM["wrong_change"],
         "Wrongly declined (safe)": RM["wrongly_declined"], "Handed to a person": RM["handed_over"], "Missed": RM["missed"]},
        {"Test": f"{RE['n']} extra checks", "Fully correct": f"{RE['correct']} of {RE['n']}", "Wrong change applied": RE["wrong_change"],
         "Wrongly declined (safe)": RE["wrongly_declined"], "Handed to a person": RE["handed_over"], "Missed": RE["missed"]},
        {"Test": f"{N_REQ} hard requests, rules only (no AI)", "Fully correct": f"{int(B['full_ok'].sum())} of {N_REQ}", "Wrong change applied": bm["unsafe"],
         "Wrongly declined (safe)": bm["safe_declined"], "Handed to a person": 0, "Missed": "most of them"},
    ]), hide_index=True, width="stretch")
    st.caption(f"Live results: {RESULTS['model']}, one run of each test. {RM['retried']} of the {RM['n']} answers were blocked by a safety rule on the first try and corrected on the retry "
               "(3 of 5 in the extra checks). Repeat runs differ by a request or two, so treat these as a signal.")

    st.markdown("**The rules-only baseline on all requests, and why rules fail**")
    ct = B.groupby("case type").agg(Requests=("full_ok", "size"), Right=("full_ok", "sum"), Action=("action_ok", "sum")).reset_index()
    ct["o"] = ct["case type"].map({c_: n_ for n_, c_ in enumerate(FAMILIES)})
    ct = ct.sort_values("o")
    st.table(pd.DataFrame({"Situation": ct["case type"].map(CASE_LABELS), "Requests": ct["Requests"],
                           "Baseline fully right": ct["Right"], "Baseline right action": ct["Action"],
                           "Why a rules-only system fails here": ct["case type"].map(lambda c_: FAMILIES[c_][1])}).set_index("Situation"))
    st.caption(f"The baseline never hands a request to a person, so a real rules system that escalated the hard cases would look better than "
               f"{int(B['full_ok'].sum())} of {N_REQ}. It applies a wrong change on {bm['unsafe']} of {N_REQ} requests and declines {bm['safe_declined']} wrongly.")

    with st.expander("How much should you trust these numbers?"):
        st.markdown(
            "- **The test is ours.** Claude wrote the synthetic requests and the answer key. A few key entries were adjusted after the first live runs, "
            "when the key asked for something the model's instructions did not.\n"
            "- **The rules were refined after test failures.** The safety rules and the instructions were improved after reviewing which requests failed, so a rerun of the same "
            f"{N_REQ} is a check, not a clean test. The {len(extra_items)} extra checks were written afterwards to see whether the rules generalise; they have the same author.\n"
            "- **The baseline is built to lose here.** The requests were chosen because rules cannot settle them, and some were reworded when the baseline got them right by accident. "
            "It is a reference point with no escalation, not a measure of rules on everyday traffic.\n"
            "- **Runs differ.** Repeat live runs differ by a request or two, and a request can flip between right and wrong with identical settings.\n"
            "- **Small and hand-built.** Four requests per situation is a sample of the idea, not of real traffic. What would make it real is a few hundred human-labelled corrections.\n"
            "- **One small model.** All results use Gemini flash-lite on its free tier. Stronger paid models are expected to do better but have not been run.")

    with st.expander("See every request"):
        show = B[["request_id", "case type", "expected", "agent"]].copy()
        show["case type"] = show["case type"].map(CASE_LABELS)
        st.dataframe(show.rename(columns={"request_id": "Request", "case type": "Situation", "expected": "Expected", "agent": "Baseline chose"}),
                     hide_index=True, width="stretch")

# ---------------------------------------------------------------- business case
with tab_impact:
    st.subheader("What is it worth?")
    st.caption("Every input is an assumption you can change. The table at the bottom says where each default comes from.")
    FIELDS = [
        ("requests_per_month", "Correction requests per month", 500.0, "%.0f", "Assumed for a mid-sized card company."),
        ("manual_minutes", "Minutes to fix one request by hand", 5.0, "%.0f", "Open the receipt, read the memo and the request, decide, update the record. Ramp reports hours of support and engineering time per fix; 20 minutes is our assumption for the routine case, deliberately lower, so the saving is understated."),
        ("hourly_cost", "Cost of one staff hour (₹)", 25.0, "%.0f", "About ₹68,000 a month fully loaded for a senior support executive (salary up to ₹6.5 lakh a year on AmbitionBox, plus about 25% overhead), over 160 hours. A senior person handles these because a wrong change costs the customer money. Our assumption."),
        ("ai_cost", "Model + retrieval cost per request (₹)", 0.5, "%.1f", "Deliberately generous: the model call alone is a fraction of a rupee at published prices."),
        ("review_share", "Share still reviewed by a person (%)", 1.0, "%.1f", "Our assumption."),
        ("review_minutes", "Minutes per review", 1.0, "%.0f", "Our assumption: a quick check of the agent's answer, not a full redo."),
        ("rework_share", "Share of agent decisions redone by hand (%)", 1.0, "%.1f", "Ramp reports under 10% repeat corrections; 8% is our pick."),
        ("current_coverage", "Share staff can handle today (%)", 0.5, "%.1f", "Ramp reported 1.5% in 2024."),
        ("fte_hours", "Working hours per person per month", 5.0, "%.0f", "40 hours a week for 4 weeks. Used to convert hours into full-time staff."),
        ("build_cost", "One-time build cost (₹)", 100000.0, "%.0f", "A team of four for three months at about ₹3 lakh per person-month. Our assumption."),
        ("run_cost", "Run and maintain cost per month (₹)", 25000.0, "%.0f", "Part-time owner team and tools for monitoring, evaluation and prompt updates. Our assumption."),
        ("amortise_months", "Months to spread the build cost over", 1.0, "%.0f", "Our assumption."),
        ("rules_run_cost", "Run cost of a rules-only matcher per month (₹)", 10000.0, "%.0f", "Used in the rules comparison. Part-time upkeep of matching rules and code tables. Our assumption."),
    ]
    PCT = {"review_share", "rework_share", "current_coverage"}

    def reset_inputs():
        for k_, *_ in FIELDS:
            st.session_state[f"imp_{k_}"] = float(DEFAULTS[k_] * (100 if k_ in PCT else 1))

    for k_, *_ in FIELDS:
        st.session_state.setdefault(f"imp_{k_}", float(DEFAULTS[k_] * (100 if k_ in PCT else 1)))
    with st.expander("Assumptions (change any)"):
        cols = st.columns(3)
        for i, (k_, lab, step, fmt, hlp) in enumerate(FIELDS):
            cols[i % 3].number_input(lab, min_value=0.0, step=step, format=fmt, key=f"imp_{k_}", help=hlp)
        st.button("Reset to defaults", on_click=reset_inputs)

    P = {k_: st.session_state[f"imp_{k_}"] / (100 if k_ in PCT else 1) for k_, *_ in FIELDS}
    R = compute(P)
    N = P["requests_per_month"]
    i1, i2, i3, i4 = st.columns(4)
    i1.metric("By hand, per request", inr(R["manual_req"]))
    i2.metric("With the agent, all-in", inr(R["allin_req"]), f"-{R['reduction']:.0%}", delta_color="off",
              help=f"Marginal cost per request, before run and build costs: {inr(R['ai_req'])}.")
    i3.metric("Monthly cost, all by hand", inr(R["manual_total"]))
    i4.metric("Monthly cost, with the agent", inr(R["programme_total"]), f"-{inr(R['net_vs_hand'])}", delta_color="off")

    st.markdown("**Three ways to handle the volume (per month)**")
    st.table(pd.DataFrame([
        ["Do nothing: staff handle what they can", inr(R["spend_today"]), f"{R['handled_today']:,.0f} ({P['current_coverage']:.1%})", f"{R['fte_today']:.1f} people", inr(R["manual_req"])],
        ["Hire to answer everything by hand", inr(R["manual_total"]), f"{N:,.0f} (100%)", f"{R['fte_manual']:.0f} people", inr(R["manual_req"])],
        ["Agent, with human review and rework", inr(R["programme_total"]), f"{N:,.0f} (100%)", f"{R['fte_ai']:.1f} people, plus the run team", inr(R["allin_req"])],
    ], columns=["Option", "Monthly cost", "Requests answered", "Staff time", "Cost per request answered"]).set_index("Option"))
    st.caption("A decline with a clear reason counts as answered. The agent row's staff time is review and rework only; the run team is in its cost.")

    st.markdown("**Why an AI, and why one agent?**")
    st.markdown(
        f"A rules-only matcher is cheap and fixes easy requests, but on the {N_REQ} hard requests it gets {int(B['full_ok'].sum())} fully right and applies a wrong change on {bm['unsafe']}. "
        "The ten situations are ten different kinds of language problem: negation, rumour, Hindi, namesakes, takeovers, hidden sellers, receipts that decide the category, "
        "pressure, planted instructions and thin evidence. Rules would need a separate fix for each, and the wording changes every time. "
        "One agent that reads the evidence covers all of them with one prompt and one set of safety rules, and that is the case for it.")
    vr = vs_rules(P)
    st.table(pd.DataFrame({
        "Share of requests that need reading": vr["Share of requests that need an AI"].map(lambda h_: f"{h_:.0%}"),
        "Rules + people": vr["Rules + people"].map(inr), "AI agent for all": vr["AI agent for all"].map(inr),
        "Cheapest": vr["Cheapest"]}).set_index("Share of requests that need reading"))
    st.metric("Agent is cheaper than 'rules + people' above", f"{R['break_even_hard_share']:.0%}",
              help="Share of requests that need reading. 'Rules + people' is generous to the rules: they answer every easy request correctly, cost only their upkeep, and never send a hard request the wrong way.")
    st.caption("On cost, the agent wins only when enough requests are hard; below that, rules for the easy requests and people for the rest is cheaper. "
               f"On quality the agent wins on the hard ones: on the {N_REQ} hard test requests the rules-only baseline gets {int(B['full_ok'].sum())} fully right and applies a wrong change on {bm['unsafe']}, "
               f"the live agent got {RM['correct']} right with {RM['wrong_change']} wrong change. The share of hard requests in real traffic is unknown. "
               "The pilot's shadow phase must measure it by sorting 300+ real requests into 'a name match would have solved it' and 'someone had to read it'.")

    st.markdown("**Gross benefit vs incremental cost of the agent (per month)**")
    rows = [["Gross benefit: cost of answering every request by hand", inr(R["gross_benefit"])]]
    for name, per_req in R["ai_parts"].items():
        rows.append([f"Less: {name.lower()}", f"-{inr(per_req * N)}"])
    rows.append(["Net benefit against answering everything by hand", inr(R["net_vs_hand"])])
    st.table(pd.DataFrame(rows, columns=["Line", "Per month"]).set_index("Line"))

    b1, b2, b3 = st.columns(3)
    b1.metric("Stays cheaper than by hand until rework reaches", f"{R['break_even_rework']:.0%}",
              help="The share of agent decisions that would have to be redone by hand before its all-in cost per request equals the by-hand cost.")
    b2.metric("Worth building above (requests a month)", f"{R['break_even_volume']:,.0f}",
              help="Below this volume the per-request saving does not cover the fixed run and build cost.")
    b3.metric("Value needed per extra request answered", inr(R["value_threshold"]),
              help="Extra cash against today's spend, divided by the requests that go from unanswered to answered.")

    ch1, ch2 = st.columns([1.2, 1])
    with ch1:
        st.markdown("**By hand vs the parts of the agent's cost, per request**")
        pp = R["ai_parts"]
        st.bar_chart(pd.DataFrame({"₹ per request": {
            "By hand (total)": R["manual_req"], "Rework": pp["Rework of wrong decisions"], "Run team": pp["Run + maintain team"],
            "Review": pp["Human review"], "Build": pp["Build (spread over period)"], "Model": pp["Model + retrieval"]}}),
            horizontal=True, x_label="Cost per request (₹)", y_label="", sort=False)
        per_pt = R["manual_req"] * 0.01
        st.caption(f"Most of the agent's cost is the fixed run team and build ({inr(R['fixed_req'])} of {inr(R['allin_req'])} per request), so volume matters more than model price. "
                   f"Each percentage point of wrong decisions costs about {inr(per_pt)} per request. A stronger paid model is expected to make fewer wrong decisions; that is an expectation, not a measurement.")
    with ch2:
        st.markdown("**Staff time per month**")
        st.dataframe(pd.DataFrame({
            "Today": [f"{R['hours_today']:,.0f} hours", f"{R['fte_today']:.1f} people"],
            "All by hand": [f"{R['hours_manual']:,.0f} hours", f"{R['fte_manual']:.1f} people"],
            "With the agent": [f"{R['hours_ai']:,.0f} hours", f"{R['fte_ai']:.1f} people"],
        }, index=["Hours", "Full-time staff"]), width="stretch")

    st.warning(
        f"**Be careful with the saving.** The {inr(R['net_vs_hand'])} a month compares the agent with a world where staff fix every request by hand. "
        f"Nobody does that: today staff answer only {P['current_coverage']:.1%} of requests, so real spend is about {inr(R['spend_today'])}. "
        f"Answering everything with the agent costs {inr(R['programme_total'])} all-in, **{inr(R['extra_vs_today'])} more cash than today** for **{R['coverage_multiple']:.0f}x the coverage**. "
        f"It pays off if answering one extra correction is worth more than about {inr(R['value_threshold'])} to the company. "
        f"The honest case is: nearly every customer answered at about {R['reduction']:.0%} less per request than doing it by hand.")

    st.markdown("**How sensitive is the cost reduction?** (all-in, by review share and rework share)")
    st.dataframe(sensitivity(P).map(lambda v: f"{v:.0%}"), width="stretch")
    with st.expander("Where each default comes from"):
        D = DEFAULTS
        st.table(pd.DataFrame([
            ["Share staff handle today", f"{D['current_coverage']:.1%}", "Ramp write-up, 2024 (3% in 2023)"],
            ["Requests per month", f"{D['requests_per_month']:,.0f}", "Assumption: a mid-sized card company, not taken from Ramp"],
            ["Minutes per manual fix", f"{D['manual_minutes']:.0f}", "Assumption: routine case for a senior support executive. Ramp reports hours of support and engineering time per fix, so 20 minutes is deliberately lower"],
            ["Cost of a staff hour", inr(D["hourly_cost"]), "Assumption: about ₹68,000 a month fully loaded over 160 hours. Salary up to ₹6.5 lakh a year for a senior customer support executive (AmbitionBox, self-reported), plus about 25% overhead. A senior person handles these because a wrong change costs the customer money"],
            ["Model + retrieval per request", inr(D["ai_cost"]), "Assumption, deliberately high; a call to a small model costs a fraction of a rupee"],
            ["Review share and minutes", f"{D['review_share']:.0%}, {D['review_minutes']:.0f} min", "Assumption"],
            ["Rework share", f"{D['rework_share']:.0%}", f"Assumption, set under the under-10% repeat corrections Ramp reports. In the live test {RM['n'] - RM['correct']} of {RM['n']} hard requests were not fully correct ({(RM['n'] - RM['correct']) / RM['n']:.1%}); real traffic is probably easier"],
            ["Build cost", inr(D["build_cost"]), "Assumption: four people for three months at about ₹3 lakh per person-month"],
            ["Run and maintain", f"{inr(D['run_cost'])} a month", "Assumption: part-time owner team plus tools"],
            ["Build spread over", f"{D['amortise_months']:.0f} months", "Assumption"],
            ["Rules-only matcher upkeep", f"{inr(D['rules_run_cost'])} a month", "Assumption: part-time upkeep of matching rules and code tables"],
        ], columns=["Input", "Default", "Source"]).set_index("Input"))

# ---------------------------------------------------------------- rollout and success
with tab_roll:
    st.subheader("Framing the problem (TOSCAR)")
    st.table(pd.DataFrame([
        ["T  Trouble", "Is the problem real? What is the precise pain? Why now?",
         "Correction requests pile up because every one needs a person. Staff handled about 1.5% of requests in 2024 (Ramp), and each fix took hours of support and engineering time. "
         "The pain is wrong merchant records and unanswered customers. Why now: volume grows with every card issued, and models can now read messy card text, receipts and memos."],
        ["O  Owner", "Whose problem is it? Who is accountable?",
         "The Head of Card Operations at the (fictional) card company. Customers feel the pain; Finance and Compliance care about record accuracy."],
        ["S  Success criteria", "What measurable evidence would show success?", "See the table below."],
        ["C  Constraints", "What is in and out of scope? Budget, time, data and policy limits?",
         "In: four actions on existing merchant records. Out: refunds, chargebacks and disputes. The agent never edits protected merchants. "
         "Receipts hold customer data, so prompts carry only the fields needed. Assumed budget: ₹36 lakh to build, ₹4 lakh a month to run. The demo uses synthetic data only."],
        ["A  Actors", "Who is affected and what do they want?",
         "Customers: a fast, correct fix. Operations staff: fewer repetitive cases and a clear queue of the hard ones. Merchants: shared records must not be corrupted. "
         "Compliance: an audit trail. Engineers: something they can monitor."],
        ["R  Reference", "What comparable solutions or past attempts exist?",
         "Ramp's merchant-correction agent (ZenML LLMOps Database); this design follows it. Before the agent, Ramp's staff handled requests by hand."],
    ], columns=["Letter", "Question from class", "Answer for this project"]).set_index("Letter"))

    st.subheader("Success criteria")
    st.table(pd.DataFrame([
        ["Requests answered", f"{DEFAULTS['current_coverage']:.1%} (Ramp, 2024)", "95% or more", "Measured in the pilot", "Answered requests divided by requests received, weekly"],
        ["Resolved correctly", "No baseline", "85% or more (our target)",
         f"{RM['correct']} of {RM['n']} in one live run (Gemini free tier). A hard test set, not a forecast",
         "Agreement with a human reviewer on at least 300 real requests"],
        ["Wrong changes applied", "No baseline", "As close to zero as possible; every one reviewed",
         f"{RM['wrong_change']} of {RM['n']} in the live test, 0 of {RE['n']} in the extra checks ('No wrong change applied' in the Evaluation tab)", "Audit log and sampled review of accepted changes"],
        ["Edits to protected merchants", "No baseline", "Zero", "0 accepted; enforced in code", "Audit log of every attempted edit"],
        ["Time per request", "About 20 minutes by hand (our assumption); Ramp reports hours", "Under 10 seconds (Ramp reports this)", "A few seconds per decision on the free tier; not formally timed",
         "Median and 95th-percentile response time in the pilot"],
        ["Repeat corrections", "No baseline", "Under 10% (Ramp reports this)", "Not measurable on synthetic data; the business case assumes 8%",
         "Share of transactions needing a second correction within 30 days"],
        ["All-in cost per request", inr(imp["manual_req"]), "₹100 or less (our target)", f"{inr(imp['allin_req'])} on the model's assumptions", "Pilot cost divided by requests answered"],
    ], columns=["Measure", "Today", "Target", "In this demo", "How the pilot would measure it"]).set_index("Measure"))

    st.subheader("Pilot plan with go/no-go gates")
    st.caption("Our proposal. Running in shadow mode before full rollout is how Ramp rolled out its agent; its evaluation began with manual review of select responses.")
    st.table(pd.DataFrame([
        ["1. Shadow", "Weeks 1 to 4", "The agent decides on live requests but nothing is applied. Staff work as usual and results are compared.",
         "85% or more agreement on 300+ requests; no protected-merchant edit would have been accepted; 95th-percentile response under 10 seconds"],
        ["2. Assisted", "Weeks 5 to 8", "The agent proposes and a person approves with one click.", "85% or more approved unchanged; repeat corrections under 10%"],
        ["3. Auto-apply, low risk", "Weeks 9 to 12", "Creates and moves to unprotected merchants apply automatically. Updates and declines are still reviewed.",
         "All-in cost per request at or under ₹100; no rise in customer complaints; zero protected-merchant edits"],
    ], columns=["Phase", "When", "What happens", "Gate to move on"]).set_index("Phase"))
    st.warning("**Stop rule:** any change to a protected merchant, or repeat corrections at 10% or more for two weeks in a row, sends the pilot back one phase.")

    st.subheader("Where this sits in the AI project lifecycle")
    st.markdown("In class, an AI problem has to be **closed-ended**. Here, 'fix wrong merchant data' became 'choose one of four actions, from a fixed candidate list, "
                "using fixed categories'. That conversion is the main piece of product thinking in this project.")
    st.table(pd.DataFrame([
        ["1. Ideation", "AI product manager (about 80%)", "Problem made closed-ended; TOSCAR framing; model and prompt chosen; protected list and allowed categories defined.",
         "Real stakeholders agree scope and success criteria."],
        ["2. Building", "Researchers", "Three-search retrieval, decision prompt, safety rules, no-AI baseline, live evaluation on 40 synthetic requests that all need reading.",
         "Evaluation on real, human-labelled requests; prompt iterations."],
        ["3. Productionization", "Engineers (the PM has no role)", "Rules in code; retry, then hand-over to a person.",
         "Deployment, monitoring, audit log, a feedback loop back to stage 2, and Responsible AI checks on live traffic."],
    ], columns=["Stage", "Who leads (from class)", "Done in this project", "Still needed for a real launch"]).set_index("Stage"))

    st.subheader("Risks and what limits them")
    st.table(pd.DataFrame([
        ["A wrong merchant change spreads to other users", "Protected merchants cannot be edited (rule in code); a new name must be on the card text or receipt; handed-over cases go to a person", "Rules: yes. Review queue: not built"],
        ["Instructions hidden in a customer note or receipt", "The prompt treats that text as information, not orders; the rules still check the answer", "Yes, five test cases"],
        ["A customer's say-so overrides the evidence", "The prompt says it counts only if the transaction fits it; a reassign to another city needs the receipt to name the merchant", "Yes, in the live test"],
        ["An invented website in a new record", "A website must come from the request or the evidence", "Rule: yes"],
        ["Over-declining honest customers", f"Track the decline rate and sample declined cases", f"{RM['wrongly_declined']} of {RM['n']} wrongly declined in the live test; sampling not built"],
        ["A weak model", "The model is swappable; a stronger paid one is expected to make fewer wrong decisions", "Tested with Gemini only"],
        ["Overstated accuracy", "Synthetic, same-author data and a hard test set, so results are labelled as signals; real labelled data is needed", "Stated in the app"],
        ["Customer data in prompts", "Send only the fields needed; review data handling before real use", "Not built"],
    ], columns=["Risk", "How it is limited", "In this demo"]).set_index("Risk"))

# ---------------------------------------------------------------- how it works
with tab_how:
    st.subheader("The pipeline")
    st.graphviz_chart("""
    digraph G { rankdir=LR; node [shape=box, style="rounded,filled", fillcolor="#eef2f7", fontname="Helvetica"];
      req [label="Customer request\\n+ transaction evidence"];
      ret [label="1. Find candidates\\ncard-text similarity\\n+ name match\\n+ names in the text"];
      dec [label="2. Decide (live model)\\ncreate / update /\\nreassign / decline"];
      gr  [label="3. Safety rules", fillcolor="#fde9d9"];
      ok  [label="4. Apply + message\\nthe customer", fillcolor="#e1f2e1"];
      hum [label="Person reviews", fillcolor="#f7e1e1"];
      req -> ret -> dec -> gr; gr -> ok [label="pass"]; gr -> dec [label="fail: retry (max 3)"]; gr -> hum [label="still failing"]; }
    """)
    st.markdown(
        "1. **Find candidates.** Three searches run in parallel: card-text similarity against the card texts each merchant already has, fuzzy name matching against what the customer typed, "
        "and merchant names mentioned in the receipt, memos or note. The merchant currently shown is always added.\n"
        "2. **Decide.** A live model call sees the evidence and the candidates and returns one of four actions with a reason and a customer message.\n"
        "3. **Safety rules.** Plain code checks the answer (table below). A failed rule sends the model back with the rule that broke.\n"
        "4. **Retry or hand over.** After three attempts a person takes over.")
    st.table(pd.DataFrame([
        ["Action is one of the four allowed; a reason is given", "Malformed or empty answers"],
        ["Target is in the candidate list", "Invented merchants"],
        ["Established merchant records are not edited", "Damage to records shared by many customers"],
        ["An update changes at least one value on the record", "Empty updates and updates that restate what the record already says"],
        ["Category is from the allowed 12; website looks like a domain", "Made-up categories and malformed websites"],
        ["New merchant has a name and category, is not a near-duplicate, and does not reuse another merchant's website", "Duplicate or clashing records"],
        ["A new or changed name is on the card text or the receipt", "A name backed only by a note or memo, such as a rename announced for later"],
        ["A merchant in another city is named in full on the receipt or a memo", "Reassigning to a namesake in the wrong city on a guess"],
        ["A website comes from the request or the evidence", "Invented websites"],
        ["A message for the customer is given on a decline", "Silent declines"],
    ], columns=["Rule", "What it stops"]).set_index("Rule"))
    with st.expander("The prompt the model receives, word for word"):
        st.code(decide.SYSTEM, language="text")
    st.markdown("The model **judges the evidence**. Code does everything that must be exact. This split is the main answer to *'what if the AI is wrong?'*")

    st.subheader("Technique choices")
    st.table(pd.DataFrame([
        ["Prompt engineering", "Yes", "One fixed prompt with the evidence, the allowed actions and a strict JSON answer; free text is fenced as untrusted data"],
        ["Retrieval (RAG-style)", "Yes, three searches", "The model should choose among real merchants, so the search puts them in front of it"],
        ["Agent loop with tools", "Small", "Decide, check, retry. No free-roaming tool use, because the set of actions is closed"],
        ["Fine-tuning", "No", "Not needed for four actions with clear evidence; revisit if real data shows systematic errors"],
        ["Rules in code", "Yes", "Anything that must be exact, such as protected merchants and allowed values, is not left to the model"],
    ], columns=["Technique", "Used?", "Why"]).set_index("Technique"))

    st.subheader("Models")
    st.markdown(
        "The app calls a model live for every decision. **Google Gemini (gemini-3.5-flash-lite, free tier)** produced every result shown. "
        "**Anthropic Claude** and **OpenAI** are available in the sidebar with your own paid key, but have not been evaluated. "
        "Larger paid models are expected to make fewer wrong decisions, because the misses we saw were errors of judgement (for example, treating two vendors on one payment as one), "
        "not errors of reading. To test that, enter a paid key and run the same 40 in the Evaluation tab.")

    st.subheader("What is real, synthetic or assumed")
    st.table(pd.DataFrame([
        ["Ramp's agent design and figures (1.5% coverage, under 10 seconds, under 10% repeat corrections)", "Real, published", "ZenML LLMOps Database write-up of Ramp's agent"],
        ["The card company, merchants, customers, transactions and receipts", "Synthetic", f"Generated; {len(merchants)} fictional merchants ({int(merchants['established'].sum())} protected)"],
        [f"The {N_REQ} test requests and the answer key", "Synthetic, written by hand", "Ten situations; a few key entries adjusted after the first live runs"],
        ["Model results", "Measured, live", "Gemini free tier; Test results in the Evaluation tab"],
        ["Safety rules and the instructions to the model", "Refined after reviewing test failures", "Checked on five extra requests written afterwards"],
        ["Money figures in the Business case (volume, hours, cost, build, run, rework)", "Assumptions you can change", "Business case tab"],
        ["Free-text note box, Hindi and Hinglish evidence, the third search, planted instructions in receipts", "Our additions beyond Ramp", "This project"],
    ], columns=["Item", "Status", "Where it comes from"]).set_index("Item"))
    st.caption("No real people or cards appear anywhere. Real receipts and memos would be personal data and need a data-handling review. "
               "The design follows the public write-up of Ramp's agent; it uses none of Ramp's data or code.")
