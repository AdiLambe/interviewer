#!/usr/bin/env python3
"""
INTERVIEWER - spoken mock interviews for 32 job roles, in ONE file.
NO AI, NO API key, NO account, NO limits. Works offline (voice recognition in the browser or
Termux may use the internet, the interviewer itself never does).

The interviewer SPEAKS a question, LISTENS to your answer, judges it by the key concepts you
covered, then builds the next question FROM your answer: it asks about a concept you missed or
probes one you mentioned for real experience. Difficulty climbs beginner > intermediate >
advanced > expert, or drops if you struggle. About 15-20 minutes, a project/behavioural question
near the end, then a scorecard with strengths, gaps and a study plan, saved to a text file.
It remembers which questions you already heard, so repeat interviews stay fresh.

ROLES  (python3 interviewer.py --list)
  Testing and QA : Manual, Playwright, Selenium, API testing, Appium mobile, Performance, SDET
  DevOps & Cloud : DevOps, AIOps / MLOps / SRE
  Backend        : Java, Python, Go, Ruby on Rails, Perl, Rust
  Frontend       : HTML CSS JavaScript, React, Angular and Vue
  Databases      : Oracle and PL/SQL, SQL developer, DBA (MySQL, PostgreSQL, NoSQL)
  Middleware     : Kafka, MQ, Tomcat, WebLogic, MuleSoft
  Product & Biz  : Product Manager, Sales, Digital Marketing, Business Analyst, Scrum / Project
  SAP            : ABAP, FICO, MM, SD, S/4HANA and general
  Missing a role? Add it with a plain text file (see ADD YOUR OWN ROLE below).

RUN
  python3 interviewer.py --web                 LOCALHOST: opens http://localhost:8000 in your
                                               browser with mic + voice (Chrome or Edge). Best
                                               way to share: send this file, friend runs it.
  python3 interviewer.py                       in the terminal (voice if available, else typing)
  python3 interviewer.py --role java --minutes 18
  python3 interviewer.py --keyboard            type, or use your keyboard's mic key; he speaks
  python3 interviewer.py --text                no sound at all
  python3 interviewer.py --list                show all roles
  python3 interviewer.py --reset-history       forget which questions you already heard
  python3 interviewer.py --web --port 9000 --no-browser

DURING THE INTERVIEW  say or press:  repeat | hint | skip | stop
  Tip: use the real technical terms in your answers (the code matches concepts, it does not
  truly understand sentences).

VOICE IN THE TERMINAL
  Termux (Android):  pkg install python termux-api play-audio
    optional natural voice: MULTIDICT_NO_EXTENSIONS=1 YARL_NO_EXTENSIONS=1 \\
    FROZENLIST_NO_EXTENSIONS=1 AIOHTTP_NO_EXTENSIONS=1 pip install edge-tts
  PC: pip install SpeechRecognition pyttsx3 pyaudio
  Interviewer voice: INTERVIEW_VOICE=en-IN-PrabhatNeural | en-IN-NeerjaNeural | en-US-GuyNeural

ADD YOUR OWN ROLE
  Make a text file (for example my_roles.txt) next to this script named interviewer_extra.txt,
  or run with --bank my_roles.txt. Format, one question per line:
    ## key|Role name|Category|alias one,alias two
    level|topic|question|concept one,synonym;concept two,synonym|short model answer
  level is 0 beginner, 1 intermediate, 2 advanced, 3 expert. A concept is a group of words
  where hearing ANY of them counts. Five or more concepts per question works best.
"""

import os
import re
import sys
import json
import time
import uuid
import shutil
import random
import difflib
import tempfile
import datetime
import threading
import subprocess
import webbrowser
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    import speech_recognition as sr
except Exception:
    sr = None
try:
    import pyttsx3
except Exception:
    pyttsx3 = None

HOME = os.path.expanduser("~")
HERE = os.path.dirname(os.path.abspath(__file__))
EDGE_VOICE = os.environ.get("INTERVIEW_VOICE", "en-IN-PrabhatNeural")
EDGE_RATE = os.environ.get("INTERVIEW_RATE", "+0%")
EDGE_PITCH = os.environ.get("INTERVIEW_PITCH", "+0Hz")
LISTEN_LANG = os.environ.get("INTERVIEW_LANG", "en-IN")     # terminal PC mic language
LEVELS = ["beginner", "intermediate", "advanced", "expert"]


# =====================================================================
#  SMALL HELPERS
# =====================================================================
def norm(t):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", t.lower())).strip()


def has_kw(ans_n, ans_ns, kw):
    """Keyword match that survives speech-to-text quirks (S/4HANA, S4 HANA, gr/ir...)."""
    k = norm(kw)
    ks = k.replace(" ", "")
    if not k:
        return False
    if len(ks) <= 3:       # short tokens must match as whole words ("po", "mm", "gr")
        return re.search(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])", ans_n) is not None
    return k in ans_n or ks in ans_ns


def parse_json(t):
    t = re.sub(r"^```(?:json)?|```$", "", t.strip(), flags=re.M)
    a, b = t.find("{"), t.rfind("}")
    if a < 0 or b <= a:
        return None
    try:
        return json.loads(t[a:b + 1])
    except Exception:
        return None


def clean_speech(t):
    t = re.sub(r"```\w*", "", t)
    t = re.sub(r"[*`#]+", "", t)
    t = re.sub(r"^\s*[-\u2022]\s+", "", t, flags=re.M)
    return re.sub(r"\s*\n+\s*", " ", t).strip()



# =====================================================================
#  VOICE  (ears and mouth)
# =====================================================================
class Voice:
    def __init__(self, keyboard=False, text_only=False):
        self.text_only = text_only
        self.mic = None
        self.tts = None
        self._warned = False
        self.mic_fails = 0
        if not text_only:
            if not keyboard and shutil.which("termux-speech-to-text"):
                self.mic = "termux"
            elif not keyboard and sr:
                try:
                    sr.Microphone()
                    self.rec = sr.Recognizer()
                    self.rec.pause_threshold = 2.0      # allow pauses inside a long answer
                    self.mic = "pc"
                except Exception:
                    self.mic = None
            if pyttsx3 and not shutil.which("termux-tts-speak"):
                try:
                    self.tts = pyttsx3.init()
                    self.tts.setProperty("rate", 165)
                except Exception:
                    self.tts = None

    def describe(self):
        ear = {"termux": "Termux mic", "pc": "PC mic", None: "keyboard (use your keyboard's mic key to dictate)"}[self.mic]
        if self.text_only:
            return "text only"
        mouth = "neural voice" if self._edge_ready() else \
            ("phone voice" if shutil.which("termux-tts-speak") or self.tts else "screen only")
        return f"hearing: {ear} | speaking: {mouth}"

    @staticmethod
    def _edge_ready():
        return bool(shutil.which("edge-tts") and (shutil.which("play-audio") or shutil.which("mpv")))

    def _edge(self, text):
        path = os.path.join(tempfile.gettempdir(), "sap_interview_voice.mp3")
        try:
            if os.path.exists(path):
                os.remove(path)
            r = subprocess.run(["edge-tts", "--voice", EDGE_VOICE, f"--rate={EDGE_RATE}",
                                f"--pitch={EDGE_PITCH}", f"--text={text}", "--write-media", path],
                               capture_output=True, text=True, timeout=60)
            if r.returncode != 0 or not os.path.exists(path):
                raise RuntimeError((r.stderr or "")[-150:])
            player = shutil.which("play-audio")
            cmd = [player, path] if player else ["mpv", "--no-video", "--really-quiet", path]
            subprocess.run(cmd, timeout=240)
            return True
        except Exception as e:
            if not self._warned:
                print("(neural voice failed, using the phone voice:", str(e).strip()[:120], ")")
                self._warned = True
            return False

    def say(self, text):
        text = clean_speech(text)
        print("\nINTERVIEWER:", text)
        if self.text_only or not text:
            return
        try:
            if self._edge_ready() and self._edge(text):
                pass
            elif shutil.which("termux-tts-speak"):
                for chunk in re.findall(r".{1,300}(?:\s|$)", text):
                    subprocess.run(["termux-tts-speak", "-r", "1.0", chunk.strip()])
            elif self.tts:
                self.tts.say(text)
                self.tts.runAndWait()
            else:
                return
            if self.mic:
                time.sleep(1.0)     # let the speaker go quiet so the mic does not hear it
        except Exception:
            pass

    # ---- listening -------------------------------------------------
    def _termux_once(self):
        try:
            r = subprocess.run(["termux-speech-to-text"], capture_output=True, text=True, timeout=90)
        except Exception:
            self.mic_fails += 1
            return ""
        out = r.stdout.strip()
        if out.startswith(("{", "[")) or r.returncode != 0 or (out and not any(c.isalnum() for c in out)):
            self.mic_fails += 1
            return ""
        return out

    def listen(self, single=False):
        """Returns the candidate's answer as text ('' if nothing heard)."""
        if self.mic == "termux":
            parts = []
            for i in range(1 if single else 4):          # keep listening for a longer answer
                if i == 0:
                    print("(listening... speak now)")
                else:
                    print("(keep talking, or stay silent / say 'done' to finish)")
                seg = self._termux_once()
                if self.mic_fails >= 3 and not parts:
                    print("\n(The Termux microphone is not working on this phone. Switching to the "
                          "keyboard: tap your keyboard's mic key to dictate your answer.)")
                    self.mic = None
                    return self.listen(single)
                if not seg or norm(seg) in ("done", "over", "that is all", "finished"):
                    break
                print("  you:", seg)
                parts.append(seg)
            return " ".join(parts)
        if self.mic == "pc":
            with sr.Microphone() as m:
                self.rec.adjust_for_ambient_noise(m, duration=0.6)
                print("(listening... speak now)")
                try:
                    audio = self.rec.listen(m, timeout=20, phrase_time_limit=100)
                    text = self.rec.recognize_google(audio, language=LISTEN_LANG)
                    print("  you:", text)
                    return text
                except Exception:
                    return ""
        try:
            return input("\nYOU: ").strip()
        except (EOFError, KeyboardInterrupt):
            return "stop"



# =====================================================================
#  QUESTION BANK  (works with no key, no internet)
# =====================================================================
def Q(level, topic, question, groups, ideal):
    return {"lvl": level, "topic": topic, "q": question, "groups": groups, "ideal": ideal}


MODULES = {
    "abap": {"name": "SAP ABAP", "aliases": ["abap", "programming", "developer", "development"], "questions": [
        Q(0, "Data dictionary", "What is the difference between a transparent table, a pool table and a cluster table?",
          [["transparent"], ["one to one", "1 1", "database table", "same structure"], ["pool", "pooled"], ["cluster", "clustered"]],
          "A transparent table maps one to one to a database table. Pool and cluster tables are logical tables stored together in a table pool or cluster in the database, for small or related data. They are mostly obsolete on HANA."),
        Q(0, "Internal tables", "What is an internal table, and what are its types?",
          [["standard"], ["sorted"], ["hashed"], ["work area", "workarea", "header line"]],
          "An internal table is a runtime data object that holds many rows. Types are standard, sorted and hashed. Standard uses linear access, sorted keeps rows ordered by key and allows binary search, hashed gives constant time access through a unique key."),
        Q(0, "Reports", "What is the difference between a classical report and an interactive report?",
          [["classical", "classic"], ["interactive", "drill down", "at line selection", "hide"], ["alv"], ["selection screen", "parameters", "select options"]],
          "A classical report shows a single list. An interactive report lets the user drill down from the basic list to secondary lists using events like AT LINE-SELECTION. ALV is the standard way to show grid output."),
        Q(1, "Integration technologies", "What is the difference between a BAPI, an RFC function module and an IDoc?",
          [["bapi", "business api", "business object"], ["rfc", "remote function", "remote enabled"], ["idoc", "intermediate document", "asynchronous"], ["synchronous"]],
          "An RFC is a remote-enabled function module called across systems. A BAPI is a standardised RFC-enabled method of a business object. An IDoc is a data container used for asynchronous message exchange."),
        Q(1, "Enhancements", "Explain user exits, customer exits, BAdIs and enhancement spots. How are they different?",
          [["user exit", "include"], ["customer exit", "function exit", "cmod"], ["badi", "business add in"], ["enhancement spot", "enhancement framework", "implicit", "explicit"], ["multiple", "modification free", "se19"]],
          "User exits are include based and need an access key. Customer exits are function module exits managed through CMOD and SMOD. BAdIs are object oriented, can have multiple implementations and are managed in SE18 and SE19. The enhancement framework with spots and implicit or explicit options is the newer, modification free approach."),
        Q(1, "Performance tuning", "How do you improve the performance of an ABAP program that reads a lot of data from the database?",
          [["specific fields", "avoid select star", "only required fields"], ["for all entries", "join", "inner join"], ["index", "secondary index", "where clause"], ["buffer", "buffering"], ["st05", "sql trace", "sat", "runtime analysis", "code inspector"], ["cds", "amdp", "code pushdown", "hana"]],
          "Select only the needed fields with a precise WHERE clause, use joins or FOR ALL ENTRIES carefully, make sure indexes are used, use buffering where suitable, and measure with ST05, SAT and the code inspector. On HANA, push logic down with CDS views and AMDP."),
        Q(2, "Code pushdown", "What is code pushdown on HANA? Explain CDS views and AMDP.",
          [["code pushdown", "push down", "database layer", "code to data"], ["cds", "core data services"], ["amdp", "abap managed database procedure"], ["performance", "in memory", "faster"], ["open sql", "select"]],
          "Code pushdown moves data intensive logic from the application server to the database. CDS views define semantic data models in the database. AMDP lets you write SQLScript procedures inside ABAP classes. Both reduce data transfer and improve speed."),
        Q(2, "Troubleshooting", "A background job is failing with a short dump. Walk me through how you would investigate.",
          [["st22", "short dump", "dump analysis"], ["sm37", "job log", "background job"], ["sm21", "system log"], ["debug", "debugger", "breakpoint", "jdbg"], ["variant", "authorization", "memory", "root cause"]],
          "Check the job log in SM37, open the dump in ST22 to see the exact error and line, check the system log in SM21, reproduce it with the same variant and user, debug if needed, then fix the root cause such as authorisation, memory or bad data."),
        Q(3, "RAP", "Explain the ABAP RESTful application programming model. What are behavior definitions and draft handling, and how do they relate to Fiori?",
          [["rap", "restful application programming"], ["behavior definition", "behaviour definition", "bdef"], ["cds", "root entity", "data model"], ["draft"], ["odata", "fiori elements", "service binding", "service definition"], ["managed", "unmanaged"]],
          "RAP is the modern model for building OData services and Fiori apps. You define CDS data models, behavior definitions for create, update, delete and validations, in managed or unmanaged implementation, optional draft handling, then expose them through a service definition and binding for Fiori elements."),
        Q(3, "Locks and updates", "How do you handle lock concurrency and update tasks in ABAP? Explain enqueue locks, update function modules and the difference between V1 and V2 updates.",
          [["enqueue", "lock object", "sm12"], ["update function", "update task", "in update task", "sm13"], ["v1", "v2"], ["commit work", "rollback", "luw"], ["dequeue", "release"]],
          "Lock objects create enqueue locks to prevent concurrent changes. Update function modules called in update task run at COMMIT WORK. V1 updates are time critical and run first, V2 are less critical and run later. ROLLBACK WORK discards everything in the LUW."),
        Q(0, "Program types", "What are the different types of ABAP programs, and what is the difference between a function module and a class method?",
          [["executable", "report"], ["module pool", "dialog"], ["function group", "function module"], ["class", "method", "object oriented"], ["include"], ["subroutine", "perform"]],
          "Program types include executable reports, module pools, function groups, class pools and includes. A function module lives in a function group and is called with CALL FUNCTION, and can be remote enabled. A class method belongs to a class and supports object oriented features like inheritance and interfaces."),
        Q(1, "Open SQL", "What is the difference between SELECT SINGLE and SELECT UP TO 1 ROWS, and what is the pitfall of FOR ALL ENTRIES?",
          [["select single", "single"], ["up to 1 rows", "up to one rows", "order by"], ["for all entries"], ["empty table", "driver table", "duplicate", "initial", "not initial"], ["primary key", "full key"]],
          "SELECT SINGLE needs the full primary key and returns any one matching row, while UP TO 1 ROWS with ORDER BY returns the first row in sort order. FOR ALL ENTRIES reads rows matching a driver internal table, but if that table is empty it reads the whole table, and it removes duplicate rows, so always check the driver table is not initial."),
        Q(2, "ALV", "Explain the difference between classic ALV, object oriented ALV and SALV, and how you handle events like double click.",
          [["reuse alv", "function module", "classic"], ["cl gui alv grid", "object oriented", "container", "custom control"], ["salv", "cl salv table", "simple alv"], ["event", "double click", "hotspot", "handler"], ["field catalog", "layout", "fieldcat"]],
          "Classic ALV uses function modules like REUSE_ALV_GRID_DISPLAY, object oriented ALV uses CL_GUI_ALV_GRID in a container, and SALV with CL_SALV_TABLE is the simplest and newest. Events such as double click are handled by registering an event handler method, and the field catalog and layout control the columns."),
        Q(3, "OData services", "How do you build an OData service for a Fiori app using SEGW, and how is that different from a CDS based service?",
          [["segw", "gateway service builder", "service builder"], ["entity type", "entity set", "entity"], ["dpc", "mpc", "data provider", "model provider"], ["get entityset", "create entity", "crud", "read", "update"], ["cds", "annotation", "service definition", "service binding"], ["iwfnd", "activate", "register", "service catalog"]],
          "In SEGW you define entity types and entity sets, generate the model and data provider classes, implement CRUD methods like GET_ENTITYSET in the DPC extension class, then register and activate the service in the gateway. A CDS based service is generated from annotated CDS views with a service definition and binding, with almost no hand written code."),
    ]},
    "fico": {"name": "SAP FICO", "aliases": ["fico", "finance", "financial", "controlling", "accounting"], "questions": [
        Q(0, "Enterprise structure", "What is a company code, and how is it different from a controlling area and a business area?",
          [["company code", "legal entity", "balance sheet"], ["controlling area", "cost accounting", "internal"], ["business area", "segment", "internal reporting"], ["chart of accounts"]],
          "A company code is the smallest legal entity with its own balance sheet. A controlling area is the organisational unit for cost accounting and can cover several company codes. A business area was used for internal reporting and is replaced by segments."),
        Q(0, "Chart of accounts", "What is the chart of accounts, and what is the difference between operating, group and country specific charts?",
          [["chart of accounts"], ["operating", "company code level"], ["group", "consolidation"], ["country", "local", "legal"], ["gl account", "account group"]],
          "The chart of accounts is the list of GL accounts. The operating chart is assigned to company codes for daily posting, the group chart supports consolidation, and a country chart satisfies local legal reporting."),
        Q(0, "Document types", "Explain the difference between parked, held and posted documents.",
          [["parked", "park"], ["held", "hold"], ["posted", "accounting document", "updates gl"], ["workflow", "approval", "release"], ["incomplete", "not update", "no ledger"]],
          "A parked document is saved incomplete or for approval and does not update the ledgers. A held document is saved temporarily by the user. A posted document updates the ledgers and creates an accounting document."),
        Q(1, "MM FI integration", "How does the MM and FI integration work? Explain OBYC, valuation class and automatic account determination.",
          [["obyc", "transaction key", "account determination"], ["valuation class", "material valuation"], ["gr ir", "goods receipt invoice receipt", "bsx", "wrx"], ["movement type"], ["gl account"], ["chart of accounts", "account modification", "valuation grouping"]],
          "Postings from goods movements find GL accounts automatically. The material valuation class, movement type, transaction key like BSX or WRX and chart of accounts together determine the account, configured in OBYC."),
        Q(1, "Month end", "Walk me through the month end closing activities in SAP FI and CO.",
          [["accrual", "provision"], ["depreciation", "afab", "asset"], ["foreign currency valuation", "revaluation", "exchange rate"], ["gr ir", "goods receipt invoice receipt clearing"], ["posting period", "open and close", "ob52"], ["allocation", "settlement", "assessment", "distribution"], ["reconciliation", "trial balance"]],
          "Post accruals and provisions, run depreciation, revalue foreign currency balances, clear GR/IR, do cost allocations and settlements in CO, reconcile, check the trial balance, then close the posting periods."),
        Q(1, "Cost objects", "What are cost centers, profit centers and internal orders, and how are they used differently?",
          [["cost center", "cost centre"], ["profit center", "profit centre", "profitability"], ["internal order", "order"], ["settlement", "settle"], ["controlling area", "cost element"]],
          "A cost center collects costs by department. A profit center measures profitability of an area. An internal order tracks costs of a specific job or event and is settled to cost centers, assets or profitability segments."),
        Q(2, "Asset accounting", "Explain asset accounting: asset classes, depreciation areas, and what happens on acquisition, transfer and retirement.",
          [["asset class"], ["depreciation area", "parallel", "ifrs", "local gaap"], ["acquisition", "f 90", "capitalization", "abzon"], ["retirement", "scrap", "sale", "abavn", "abaon"], ["transfer", "abumn"], ["depreciation run", "afab"], ["aucs", "settlement", "wbs", "aua"]],
          "Asset classes group assets and control account determination and depreciation. Depreciation areas run parallel valuations such as book and tax. Acquisition capitalises the asset, retirement removes it and posts gain or loss, transfers move it between assets, and a periodic depreciation run posts the expense."),
        Q(2, "Universal journal", "What is the Universal Journal in S/4HANA, and how did it change reconciliation between FI and CO?",
          [["universal journal", "acdoca", "single source"], ["new gl", "new general ledger", "parallel ledger", "leading ledger"], ["reconciliation", "no reconciliation", "real time integration"], ["document splitting", "splitting"], ["segment", "profit center", "cost object"], ["compatibility view", "bseg"]],
          "In S/4HANA one table, ACDOCA, holds all FI and CO line items, so there is no separate reconciliation ledger and FI and CO are always in sync. Old tables become compatibility views."),
        Q(3, "Reconciliation issue", "A GL balance does not match the subledger in a live system. How would you investigate and fix it?",
          [["reconciliation account", "recon account", "control account"], ["subledger", "vendor", "customer", "fbl1n", "fbl5n", "fbl3n"], ["direct posting", "manual posting", "blocked"], ["check report", "sap note", "fagll03", "reconciliation report"], ["reversal", "reclass", "adjust", "clearing", "correct"], ["root cause", "configuration", "interface", "custom"]],
          "Compare the reconciliation account balance with the subledger line items, look for direct postings or custom interfaces that bypass the subledger, use standard reconciliation reports and SAP notes, then correct with reversal or adjustment postings and fix the root cause."),
        Q(3, "Global rollout", "How do you design a global rollout with many company codes, currencies and parallel accounting standards like IFRS and local GAAP?",
          [["parallel ledger", "leading ledger", "non leading"], ["currency type", "group currency", "hard currency", "company code currency"], ["document splitting"], ["chart of accounts", "group chart", "alternate chart"], ["fiscal year variant", "posting period variant"], ["template", "global design", "fit gap", "localization", "rollout"], ["consolidation", "intercompany", "group reporting"]],
          "Use a leading ledger for group accounting and additional ledgers for local GAAP, define currency types, a common chart of accounts with country alternates, document splitting, a global template with local fit gap, and plan consolidation and intercompany."),
        Q(0, "Posting keys", "What is a posting key, and what is a document type in FI?",
          [["posting key", "debit", "credit"], ["account type", "customer", "vendor", "asset"], ["document type", "number range"], ["field status"], ["reversal", "reverse"]],
          "A posting key decides whether a line is debit or credit, which account type it can be posted to and which field status applies. A document type classifies business transactions and controls the number range and reversal behaviour."),
        Q(1, "Accounts payable", "Explain the accounts payable process: vendor invoice, payment run and clearing. What is the automatic payment program?",
          [["vendor invoice", "fb60", "miro"], ["f110", "automatic payment program", "payment run", "payment proposal"], ["payment method", "house bank", "bank determination"], ["clearing", "open item"], ["payment terms", "due date", "cash discount"], ["reconciliation account"]],
          "The vendor invoice is posted through FB60 or MIRO and creates an open item. The automatic payment program, F110, selects due open items by payment method and house bank, creates a proposal, runs the payments and clears the items. Payment terms decide due dates and discounts."),
        Q(2, "Foreign currency", "How do you handle foreign currency transactions, exchange rates and revaluation of open items?",
          [["exchange rate", "ob08", "rate type"], ["foreign currency", "transaction currency", "document currency", "local currency"], ["revaluation", "open item valuation", "fagl fc val", "unrealized"], ["realized", "exchange rate difference", "gain", "loss"], ["reversal", "next period"], ["balance sheet", "adjustment"]],
          "Exchange rates are maintained per rate type in OB08. Foreign currency postings are converted at the posting rate. At period end, open items are revalued with the foreign currency valuation run, which posts unrealised gains or losses and is reversed next period. Realised differences post when the item is cleared."),
        Q(3, "Product costing and CO-PA", "What is the difference between product costing and profitability analysis, and how does CO-PA get its data?",
          [["product costing", "cost estimate", "standard cost", "ck11n", "ck40n"], ["cost component", "costing variant", "costing sheet", "bom", "routing"], ["copa", "co pa", "profitability analysis", "margin"], ["characteristic", "value field", "valuation"], ["billing", "sales order", "real time", "assignment"], ["variance", "production variance", "price variance"]],
          "Product costing calculates what a product costs using the BOM, routing, cost components and a costing variant, and releases a standard cost. Profitability analysis reports margins by characteristics like customer and product, taking revenue from billing and costs from cost of goods sold and variances. In S/4HANA margin analysis is account based and part of the Universal Journal."),
    ]},
    "mm": {"name": "SAP MM", "aliases": ["mm", "materials", "procurement", "purchasing", "material management"], "questions": [
        Q(0, "Procure to pay", "What is the procure to pay cycle in SAP MM? Name the main steps and documents.",
          [["purchase requisition", "pr", "me51n"], ["purchase order", "po", "me21n"], ["goods receipt", "gr", "migo"], ["invoice verification", "miro", "invoice receipt"], ["payment", "f110"], ["rfq", "quotation"]],
          "A purchase requisition becomes an RFQ and quotation, then a purchase order. The goods receipt is posted in MIGO, the vendor invoice in MIRO, and the payment run settles the vendor."),
        Q(0, "Material master", "What is a material master, and what are views and organisational levels in it?",
          [["material master", "mm01"], ["view", "basic data", "purchasing", "mrp", "accounting", "storage"], ["plant", "storage location"], ["material type", "material group", "industry sector"], ["client level", "plant level", "organizational level"]],
          "The material master holds all data of a material in views like basic data, purchasing, MRP and accounting, kept at client, plant or storage location level."),
        Q(0, "Material types", "What are the different material types and what do they control?",
          [["raw material", "roh"], ["finished", "fert"], ["semi finished", "halb"], ["trading goods", "hawa"], ["service", "non valuated", "nlag"], ["price control", "views", "account determination", "quantity update", "value update", "number range"]],
          "Material types like raw material, semi finished, finished, trading goods and services control which views exist, whether quantity and value are updated, the price control, number ranges and account determination."),
        Q(1, "Purchase order types", "Explain the different types of purchase orders and item categories.",
          [["standard"], ["subcontracting", "subcontract"], ["consignment"], ["stock transfer", "sto", "stock transport"], ["third party"], ["service", "limit", "blanket"], ["account assignment"]],
          "Item categories include standard, subcontracting, consignment, stock transfer, third party and service. Account assignment categories decide whether costs go to a cost center, asset or order."),
        Q(1, "MRP", "What is MRP, and what are the MRP types and lot sizing procedures?",
          [["mrp", "material requirements planning"], ["consumption based", "reorder point"], ["pd", "deterministic", "forecast"], ["lot size", "lot sizing", "fixed lot", "exact lot", "eoq"], ["safety stock", "lead time", "planned delivery time"], ["planned order", "purchase requisition", "md04", "stock requirements list"], ["mrp run", "md01", "planning run"]],
          "MRP plans material requirements from demand, stock and open orders. MRP types are deterministic like PD or consumption based like reorder point. Lot sizing decides quantities, and safety stock and lead times drive planned orders and requisitions."),
        Q(1, "Invoice verification", "Explain the three way match in invoice verification and tolerance keys.",
          [["three way", "3 way", "po gr invoice"], ["tolerance", "price variance", "quantity variance"], ["blocked invoice", "mrbr", "release"], ["gr ir", "goods receipt invoice receipt"], ["miro", "logistics invoice"], ["price difference", "moving average", "standard price"]],
          "The invoice is matched against the purchase order and the goods receipt. Tolerance keys define allowed variances. If a tolerance is exceeded the invoice is blocked and released later in MRBR. GR/IR is cleared on invoice posting."),
        Q(2, "Valuation", "Explain valuation: standard price versus moving average price, and what happens with price differences.",
          [["standard price", "s price"], ["moving average", "v price"], ["price difference", "price variance", "ppv"], ["material ledger", "actual costing"], ["revaluation", "mr21", "price change"], ["valuation class", "inventory"]],
          "With standard price, stock is valued at a fixed price and variances go to a price difference account. With moving average, the price adjusts automatically with each receipt and invoice. Material ledger gives actual costing."),
        Q(2, "Physical inventory", "How would you handle a stock difference between physical and system stock? Describe the physical inventory process.",
          [["physical inventory", "mi01", "mi04", "mi07"], ["count", "counting"], ["block", "freeze", "posting block"], ["difference", "posting difference"], ["recount", "review", "approve"], ["cycle counting", "abc"], ["gl account", "inventory difference"]],
          "Create an inventory document with MI01, optionally block the stock, enter the count with MI04, recount if needed, then post the difference with MI07, which books to the inventory difference account. Cycle counting spreads counts over the year."),
        Q(3, "Subcontracting", "Design a subcontracting process in S/4HANA, including component provision, goods receipt and accounting entries.",
          [["subcontracting", "subcontract"], ["component", "provision", "541", "stock at vendor", "bom"], ["goods receipt", "101", "543", "consumption"], ["service", "delivery cost", "gr ir", "wrx", "bsx"], ["invoice", "miro"], ["accounting", "debit", "credit", "valuation"], ["special stock", "o stock", "batch"]],
          "Create a subcontracting PO with the finished material and BOM. Provide components to the vendor with movement 541, they stay as special stock. Goods receipt of the finished product consumes the components with 543 and posts the service fee to GR/IR. The invoice clears GR/IR."),
        Q(3, "Release strategy", "How do you configure a release strategy in purchasing? What are characteristics and classes?",
          [["release strategy"], ["characteristic", "cabn"], ["class", "cl02", "032"], ["release group", "release code", "release indicator"], ["me28", "me29n", "approve"], ["workflow", "approver"], ["value", "classification"]],
          "Define characteristics like PO value, group them in a class of type 032, create a release group, release codes and strategies with prerequisites and indicators, assign the approvers, and release in ME28 or ME29N."),
        Q(0, "Organisational units", "What are the organisational units in MM: plant, storage location, purchasing organisation and purchasing group?",
          [["plant"], ["storage location"], ["purchasing organization", "purchasing org"], ["purchasing group"], ["company code"], ["valuation area"]],
          "A plant is where goods are produced or stored and is assigned to a company code. A storage location holds stock within a plant. The purchasing organisation negotiates with vendors and is assigned to plants or company codes. A purchasing group is the buyer or team."),
        Q(1, "Movement types", "Explain common movement types in MM such as 101, 201, 261, 301, 311 and 551.",
          [["101", "goods receipt"], ["201", "cost center", "consumption"], ["261", "production order", "order consumption"], ["301", "plant to plant", "plant transfer"], ["311", "storage location transfer", "within plant"], ["551", "scrapping", "scrap"], ["movement type"]],
          "101 is goods receipt for a purchase order, 201 is issue to a cost center, 261 is issue to a production order, 301 is a plant to plant transfer, 311 is a transfer between storage locations and 551 is scrapping. The movement type controls the stock update and the accounting entries."),
        Q(2, "Sourcing", "What are source list, info record, quota arrangement and outline agreements in purchasing?",
          [["source list", "me01"], ["info record", "me11"], ["quota arrangement", "quota"], ["outline agreement", "contract", "scheduling agreement"], ["source determination", "automatic source", "fixed source"], ["price", "condition", "vendor", "validity"]],
          "An info record stores a vendor and material price and terms. A source list defines allowed or fixed sources for a material in a plant. A quota arrangement splits requirements between vendors by percentage. Outline agreements, contracts and scheduling agreements, fix prices and quantities over time. Together they drive automatic source determination."),
        Q(3, "Batch management", "How do you use batch management and split valuation, and what is batch determination?",
          [["batch management", "batch", "batch managed"], ["batch determination", "strategy type", "search procedure"], ["class", "characteristic", "classification", "023"], ["split valuation", "valuation type", "valuation category"], ["expiry", "shelf life", "sled"], ["traceability", "where used", "recall"], ["serial number", "serial"]],
          "Batch management tracks lots of a material with their own characteristics like expiry. Batch determination selects batches automatically using strategy types and search procedures with a batch class. Split valuation values the same material differently by valuation type, for example by origin or quality. Together they give traceability and accurate stock value."),
    ]},
    "sd": {"name": "SAP SD", "aliases": ["sd", "sales", "distribution", "order to cash"], "questions": [
        Q(0, "Order to cash", "Explain the order to cash cycle in SAP SD.",
          [["inquiry", "quotation"], ["sales order", "va01"], ["delivery", "vl01n"], ["picking", "goods issue", "pgi"], ["billing", "vf01", "invoice"], ["accounting document", "payment", "incoming payment", "fi posting"]],
          "Inquiry and quotation lead to a sales order in VA01, then delivery with picking and post goods issue, then billing in VF01 which creates the accounting document, and finally the customer payment."),
        Q(0, "Enterprise structure", "Explain the SD enterprise structure: sales organisation, distribution channel, division and sales area.",
          [["sales organization", "sales org"], ["distribution channel"], ["division"], ["sales area", "combination"], ["shipping point", "plant", "company code"], ["sales office", "sales group"]],
          "A sales area is a combination of sales organisation, distribution channel and division. The sales organisation is assigned to a company code, and plants and shipping points handle delivery."),
        Q(0, "Document types", "What are document types and item categories in sales, and what do they control?",
          [["document type", "order type", "sales document type"], ["item category", "tan", "norm"], ["schedule line category", "schedule line"], ["copy control", "vtaa", "vtfl", "vtla"], ["number range", "order reason"]],
          "The sales document type controls the number range, the allowed follow-on documents and the process. The item category controls item behaviour like pricing and billing relevance, and schedule line categories control delivery and availability."),
        Q(1, "Pricing", "How does pricing work in SD? Explain condition types, access sequences and the pricing procedure.",
          [["condition type", "pr00"], ["access sequence", "condition table"], ["pricing procedure", "v 08", "calculation schema"], ["condition record", "vk11"], ["condition technique"], ["header", "item", "manual", "statistical", "subtotal"]],
          "The condition technique finds prices: condition types are the price elements, each has an access sequence of condition tables, records are maintained in VK11, and the pricing procedure lists the condition types in order with subtotals and requirements."),
        Q(1, "Copy control", "What is copy control, and what happens when you create a delivery or billing document with reference?",
          [["copy control", "vtaa", "vtla", "vtfl"], ["reference", "source", "target"], ["data transfer", "routine", "requirement"], ["item category", "schedule line", "header"], ["delivery", "billing", "sales order"], ["billing type", "delivery type"]],
          "Copy control defines which source documents can create which target documents and how data, routines and requirements are applied at header, item and schedule line level."),
        Q(1, "Availability check", "Explain availability check and ATP, and the delivery process of picking, packing and goods issue.",
          [["availability check", "atp", "available to promise"], ["checking group", "checking rule", "scope of check"], ["requirement", "mrp", "requirement class"], ["picking", "transfer order"], ["packing", "handling unit"], ["goods issue", "pgi", "601"], ["delivery", "vl01n"]],
          "Availability check compares requirements with stock and receipts using checking group and checking rule. The delivery is then picked, packed and goods issue posts movement 601, reducing stock and creating accounting entries."),
        Q(2, "Credit management", "Explain credit management in SD. How is a credit check triggered, and how are blocked orders released?",
          [["credit check", "credit limit", "credit control area"], ["fd32", "credit master", "risk category", "fscm", "ucm"], ["blocked", "credit block", "vkm1", "vkm3", "vkm4", "release"], ["automatic", "static", "dynamic", "simple"], ["open order", "open delivery", "open billing", "open item"], ["document type", "check"]],
          "A credit check, simple or automatic, runs at order, delivery or goods issue based on the credit control area and the customer credit master. Exceeding the limit blocks the document, which a credit controller releases in VKM1."),
        Q(2, "Revenue account determination", "What is revenue account determination in SD, and how does it connect to FI?",
          [["account determination", "revenue account", "vkoa"], ["condition technique", "access sequence", "kofi00"], ["account key", "erl", "erf", "erb"], ["chart of accounts", "sales org", "account assignment group"], ["billing", "vf01", "fi document"], ["gl account"]],
          "At billing, the system uses the condition technique with the chart of accounts, sales organisation, customer and material account assignment groups and the account key to find the revenue GL account, configured in VKOA."),
        Q(3, "Intercompany sales", "Explain intercompany sales and intercompany billing and the accounting impact.",
          [["intercompany", "inter company"], ["ordering company", "supplying company", "delivering plant", "company code"], ["transfer price", "pi01", "ic01", "internal price"], ["ic billing", "internal billing", "billing type"], ["accounting", "revenue", "cost", "debit", "credit"], ["stock transport", "sto", "purchase order"], ["elimination", "reconciliation", "consolidation"]],
          "The ordering company code sells to the customer while another company code delivers. The supplying company bills the ordering company at a transfer price, creating intercompany revenue and payable that are eliminated on consolidation."),
        Q(3, "Returns and credit memos", "How do you handle returns, credit memos and debit memos, including accounting and stock impact?",
          [["return", "returns order", "return delivery"], ["credit memo", "credit memo request"], ["debit memo", "debit memo request"], ["stock", "goods receipt", "return delivery", "restock"], ["accounting", "revenue reversal", "fi", "credit", "debit"], ["billing block", "approval", "reason"], ["reference", "copy control"]],
          "A returns order with a return delivery brings stock back and a credit memo reverses revenue. Credit and debit memo requests adjust prices or quantities, usually with a billing block for approval, with copy control from the original documents."),
        Q(0, "Master data", "What is the master data in SD? Name the customer master and material master sales data.",
          [["customer master", "xd01", "vd01", "general data", "company code data", "sales area data"], ["partner function", "sold to", "ship to", "bill to", "payer"], ["account group"], ["material master", "sales view", "sales org"], ["pricing", "condition record"], ["shipping", "billing", "output"]],
          "The customer master has general data, company code data and sales area data, with partner functions like sold to, ship to, bill to and payer. The material master has sales organisation and sales general or plant views. Pricing records and output records are also SD master data."),
        Q(1, "Partner functions", "What are partner functions and how are they used in a sales document?",
          [["partner function", "partner determination"], ["sold to", "ship to", "bill to", "payer"], ["partner procedure", "account group"], ["header", "item", "customer master", "document"], ["customer hierarchy", "contact person", "sales employee"], ["default", "determined", "change"]],
          "Partner functions are the roles a business partner plays, like sold to, ship to, bill to and payer. They are defined in a partner procedure per account group and copied from the customer master into the sales document, where they can be changed at header or item level."),
        Q(2, "Output determination", "Explain output determination in SD, for example order confirmation or invoice printing, and what is different in S/4HANA.",
          [["output determination", "output type", "nace", "condition technique"], ["access sequence", "condition record"], ["output procedure"], ["processing routine", "print", "email", "edi", "form", "adobe form", "smartform"], ["bre", "business rule", "output management", "bor"], ["partner", "medium", "requirement"]],
          "Classic output determination uses the condition technique: output types, access sequences, condition records and an output procedure, configured in NACE, with processing routines for print, email or EDI. S/4HANA output management uses the Business Rule Framework and adobe forms."),
        Q(3, "Third party and MTO", "How do third party sales and make to order scenarios work, and what changes in procurement and billing?",
          [["third party", "drop shipment", "tas"], ["purchase requisition", "purchase order", "vendor"], ["goods receipt", "invoice receipt", "miro"], ["billing", "invoice", "customer", "vf01"], ["make to order", "mto", "planning strategy", "requirement type"], ["sales order stock", "special stock", "individual"], ["no delivery", "ship directly", "delivery"]],
          "In third party sales the sales order automatically creates a purchase requisition and PO to the vendor, who ships directly to the customer. There is no delivery from your plant, and billing is based on the vendor invoice. In make to order, production is triggered by the sales order and the stock is kept as sales order stock."),
    ]},
    "s4": {"name": "SAP S/4HANA and general SAP", "aliases": ["s4", "s 4", "hana", "fiori", "basis", "general", "sap", "btp", "architecture"], "questions": [
        Q(0, "ECC vs S/4HANA", "What is the difference between SAP ECC and SAP S/4HANA?",
          [["ecc", "erp central component"], ["s 4hana", "s4hana", "s4"], ["hana", "in memory", "database"], ["fiori", "user interface"], ["simplification", "universal journal", "business partner", "material ledger", "data model"], ["cloud", "on premise", "private cloud", "public cloud"]],
          "ECC runs on any database, S/4HANA only on HANA. S/4HANA has a simplified data model with Universal Journal, Business Partner and a Fiori user experience."),
        Q(0, "HANA basics", "What is SAP HANA, and what makes it different from a traditional database?",
          [["in memory", "ram"], ["column store", "columnar", "column"], ["compression"], ["parallel", "multi core"], ["real time", "olap", "oltp", "speed", "faster"], ["pushdown", "no aggregates"]],
          "HANA keeps data in memory, stores it in columns with high compression, processes in parallel, and handles transactions and analytics together in real time."),
        Q(0, "Fiori", "What is SAP Fiori, and what are launchpad, tiles and OData services?",
          [["launchpad", "flp"], ["tile", "catalog", "group", "space", "page"], ["odata", "gateway", "service"], ["fiori elements", "ui5", "sapui5", "freestyle"], ["role", "authorization", "pfcg"], ["responsive", "mobile", "apps"]],
          "Fiori is SAP's role based, responsive user experience. The launchpad shows tiles for apps assigned through roles and catalogs, and the apps get data from OData services."),
        Q(1, "Business Partner", "What is the Business Partner concept in S/4HANA, and how does it replace customer and vendor master?",
          [["business partner", "bp", "bupa"], ["cvi", "customer vendor integration", "synchronization"], ["role", "fi customer", "fi vendor"], ["customer", "vendor", "supplier"], ["single", "central", "one master"], ["migration", "conversion", "mass"]],
          "Business Partner is the single master for customers and vendors in S/4HANA. Customer Vendor Integration synchronises it with the old records, and BP roles carry the customer or vendor data."),
        Q(1, "Migration approaches", "Explain the S/4HANA conversion approaches: brownfield, greenfield and bluefield.",
          [["brownfield", "system conversion"], ["greenfield", "new implementation"], ["bluefield", "selective data transition", "selective"], ["sum", "software update manager", "dmo"], ["readiness check", "simplification item", "maintenance planner", "custom code"], ["migration cockpit", "data migration", "lsmw", "cutover"]],
          "Brownfield converts the existing system with SUM and DMO. Greenfield is a fresh install with data migration. Bluefield is a selective transition that keeps some history and processes. Readiness checks and the simplification list guide the choice."),
        Q(1, "Basis tasks", "What are typical SAP Basis tasks like transports, user administration and monitoring?",
          [["transport", "stms", "se09", "se10"], ["user", "su01", "pfcg", "role", "authorization"], ["monitor", "sm50", "sm66", "st03", "st22", "sm21"], ["client", "scc4", "sccl"], ["background", "sm36", "sm37"], ["patch", "kernel", "support package", "upgrade"], ["landscape", "dev", "qas", "prd"]],
          "Transport management through STMS, user and role administration in SU01 and PFCG, monitoring with SM50, ST22, SM21, background jobs in SM36 and SM37, client administration, and patching the kernel and support packages across the landscape."),
        Q(2, "CDS and VDM", "Explain CDS views and the virtual data model in S/4HANA. How do they support Fiori and analytics?",
          [["cds", "core data services"], ["vdm", "virtual data model", "basic view", "composite", "consumption"], ["annotation"], ["odata", "fiori", "service"], ["analytics", "embedded analytics", "query"], ["code pushdown", "hana", "performance"], ["authorization", "dcl", "access control"]],
          "CDS views define the data model in the database. The virtual data model layers them as basic, composite and consumption views. Annotations expose them as OData for Fiori and as queries for embedded analytics, with access control through DCL."),
        Q(2, "Embedded analytics", "What is embedded analytics, and how is it different from SAP BW and SAP Analytics Cloud?",
          [["embedded analytics", "embedded"], ["bw", "business warehouse", "data warehouse"], ["analytics cloud", "sac"], ["cds", "real time", "operational reporting", "live"], ["historical", "consolidated", "multiple source", "non sap", "etl"], ["planning", "dashboard", "story"]],
          "Embedded analytics runs real time operational reports directly on S/4HANA CDS views. BW is a data warehouse for consolidated historical data from many sources. SAP Analytics Cloud is for dashboards, stories and planning."),
        Q(3, "Migration planning", "How would you plan an S/4HANA migration for a company with heavy custom code and many interfaces?",
          [["readiness check", "simplification item", "maintenance planner", "sum"], ["custom code", "atc", "abap test cockpit", "clean core", "remediation"], ["interface", "integration", "cpi", "integration suite", "idoc", "odata", "rfc"], ["testing", "unit", "uat", "regression", "integration test", "performance test"], ["cutover", "downtime", "dry run", "go live", "hypercare", "fallback", "rollback"], ["data", "archiving", "cleanup", "volume"], ["change management", "training", "stakeholder", "scope"]],
          "Start with readiness checks and the simplification list, analyse custom code with ATC and clean up unused code, inventory interfaces and plan their adaptation, clean and archive data, plan testing cycles, rehearse cutover with dry runs, and prepare hypercare and a fallback plan."),
        Q(3, "Clean core", "What does clean core mean, and what are the extensibility options: in-app, side-by-side and key user?",
          [["clean core", "upgrade safe"], ["in app", "key user", "developer extensibility", "custom field", "custom logic", "abap cloud"], ["side by side", "btp", "business technology platform", "cap"], ["released api", "released", "cloud api", "wrapper", "badi"], ["modification", "z object", "custom code"], ["fiori", "adaptation", "key user tool"]],
          "Clean core means keeping the standard system unmodified so upgrades stay easy. Extend through in-app key user and developer extensibility using released APIs, or build side by side on SAP BTP, and avoid modifications."),
        Q(0, "System landscape", "What is the SAP system landscape, and what are clients and the development, quality and production systems?",
          [["client"], ["development", "dev"], ["quality", "qas", "test"], ["production", "prd", "prod"], ["transport", "stms", "change"], ["landscape", "three system", "three tier"], ["sandbox"]],
          "A typical landscape has development, quality and production systems linked by the transport system. Each system has clients, which are independent business units with their own data. Changes are made in development, tested in quality and then moved to production by transports."),
        Q(1, "Modules and integration", "What are the main SAP modules and how do they integrate with each other?",
          [["fi", "finance", "financial accounting"], ["co", "controlling"], ["mm", "materials management"], ["sd", "sales and distribution"], ["pp", "production planning"], ["hr", "hcm", "successfactors", "human capital"], ["integration", "real time", "automatic posting", "account determination", "organizational structure"]],
          "The main modules are FI, CO, MM, SD, PP and HR. They share one database and integrate in real time. For example a goods issue in SD reduces stock in MM and posts to FI automatically through account determination."),
        Q(2, "BTP and integration", "Explain SAP BTP and the Integration Suite. When would you use CPI instead of IDocs or RFC directly?",
          [["btp", "business technology platform"], ["integration suite", "cpi", "cloud platform integration"], ["idoc", "rfc", "odata", "soap", "rest", "interface"], ["cloud", "on premise", "hybrid", "cloud connector", "connector"], ["api management", "api", "event mesh", "event"], ["monitoring", "error handling", "mapping", "transformation", "message"]],
          "SAP BTP is the platform for extensions and integration, and the Integration Suite includes CPI. Use CPI when connecting cloud and non SAP systems, or when you need mapping, transformation, monitoring and error handling. Point to point IDocs or RFC suit stable SAP to SAP links inside one landscape."),
        Q(3, "Authorisations", "How do you handle authorisations in S/4HANA and design roles for segregation of duties?",
          [["pfcg", "role", "profile generator"], ["authorization object", "su21", "field value"], ["su24", "su22", "default values", "suggestion"], ["segregation of duties", "sod", "grc", "conflict", "risk"], ["fiori", "catalog", "launchpad", "tile", "space", "business role"], ["su53", "st01", "trace", "missing authorization"], ["derived role", "composite role", "master role", "org level"]],
          "Roles are built in PFCG from authorisation objects with default values from SU24, with master and derived roles for organisational levels and composite roles for jobs. For Fiori you also assign catalogs and spaces. Segregation of duties is checked with GRC risk rules, and missing authorisations are found with SU53 and ST01 traces."),
    ]},
}

BEHAVIOURAL = [
    Q(1, "Behavioural", "Tell me about a difficult problem you solved at work: what was the problem, how did you find the cause, and what was the result?",
      [["problem", "issue", "incident", "ticket"], ["root cause", "analysis", "debug", "investigat"], ["fix", "solution", "resolved", "solved", "workaround"], ["test", "validate", "uat"], ["client", "user", "business", "stakeholder"], ["result", "outcome", "learned", "improved", "reduced"]],
      "A strong answer states the problem, how you traced the root cause, the fix you applied, how you tested it, and the business result."),
    Q(1, "Behavioural", "How do you handle a tight deadline when the client keeps changing requirements?",
      [["priorit", "scope"], ["communicat", "discuss", "expectation", "update"], ["change request", "approval", "document", "sign off"], ["risk", "impact", "estimate"], ["team", "escalate", "manager", "colleague"], ["test", "quality"]],
      "A strong answer prioritises scope, communicates the impact early, uses a change request with approval, estimates the effect on time and risk, involves the team or manager, and does not compromise on testing."),
]
for _q in BEHAVIOURAL:
    _q["behav"] = True

MISS_T = ["You did not mention {c}. How does it fit in here?", "What role does {c} play in this?",
          "Where does {c} come in?"]
PROBE_T = ["You mentioned {c}. Have you used it in real work? Give me an example.",
           "Explain {c} in more detail, with an example from your work.",
           "What problems have you faced with {c} in practice?"]
CUES = ["project", "client", "implemented", "implement", "used", "worked", "issue", "built", "fixed",
        "configured", "developed", "team", "requirement"]
HIST_FILE = os.path.join(HOME, ".interviewer_history.json")


def load_hist(key):
    try:
        with open(HIST_FILE) as f:
            return list(json.load(f).get(key, []))
    except Exception:
        return []


def save_hist(key, items):
    try:
        try:
            with open(HIST_FILE) as f:
                d = json.load(f)
        except Exception:
            d = {}
        d[key] = items[-200:]
        with open(HIST_FILE, "w") as f:
            json.dump(d, f)
    except Exception:
        pass


class Bank:
    def __init__(self, key, start_level=0):
        self.key = key
        self.qs = MODULES[key]["questions"]
        self.asked = set()
        self.level = start_level
        self.streak = 0
        self.hist = load_hist(key)
        done = len({q["q"] for q in self.qs} & set(self.hist))
        if done >= 0.9 * len(self.qs):          # seen nearly everything: start a fresh cycle
            self.hist = []

    def pick(self):
        """Nearest level first; questions you have not heard in earlier sessions come first."""
        seen = set(self.hist)
        order = sorted(range(4), key=lambda l: (abs(l - self.level), l))
        for need_fresh in (True, False):
            for lvl in order:
                pool = [i for i, q in enumerate(self.qs) if q["lvl"] == lvl and i not in self.asked
                        and (not need_fresh or q["q"] not in seen)]
                if pool:
                    i = random.choice(pool)
                    self.asked.add(i)
                    self.hist.append(self.qs[i]["q"])
                    save_hist(self.key, self.hist)
                    return self.qs[i]
        return None

    @staticmethod
    def evaluate(q, answer):
        n = norm(answer)
        ns = n.replace(" ", "")
        hit, miss = [], []
        for g in q["groups"]:
            (hit if any(has_kw(n, ns, k) for k in g) else miss).append(g[0])
        need = 3 if q.get("behav") else max(2, round(len(q["groups"]) * 0.7))
        score = min(10, round(10 * len(hit) / need))
        if len(n.split()) < 4:
            score = min(score, 1)
        return score, hit, miss

    def adjust(self, score):
        """Returns a short spoken remark when the difficulty changes."""
        if score >= 7:
            self.streak += 1
            if self.streak >= 2 and self.level < 3:
                self.level += 1
                self.streak = 0
                return "You are doing well, so let me raise the difficulty."
        elif score <= 3:
            self.streak = 0
            if self.level > 0:
                self.level -= 1
                return "Let me step back to something a little more basic."
        else:
            self.streak = 0
        return ""


def feedback_for(score, hit, miss, ideal):
    if score >= 7:
        return "Good answer. You covered " + ", ".join(hit[:3]) + "."
    if score >= 4:
        return ("Partly right. You mentioned " + (", ".join(hit[:2]) or "a few points") +
                ". You missed " + ", ".join(miss[:3]) + ".")
    return "That was incomplete. Key points to remember: " + ", ".join(miss[:3]) + "."


def first_sentences(text, n=2):
    return " ".join(re.split(r"(?<=[.!?])\s+", text)[:n])


def eval_followup(answer, fu, ideal):
    """Judge a follow-up the code generated from the candidate's own answer."""
    n = norm(answer)
    ns = n.replace(" ", "")
    words = len(n.split())
    if fu["kind"] == "miss":
        has = any(has_kw(n, ns, k) for k in fu["terms"])
        if has and words >= 10:
            return 8, "Good. That fills the gap."
        if has:
            return 5, "Right direction, but I wanted more detail."
        return 2, "Not quite. Here is the short model answer. " + first_sentences(ideal)
    cues = sum(1 for c in CUES if has_kw(n, ns, c))
    if words >= 25 and cues >= 2:
        return 8, "Good. That sounds like real project experience."
    if words >= 12:
        return 6, "Okay. Next time add what you personally did and the result."
    return 3, "Try to give a concrete project example with details."




# =====================================================================
#  ALL OTHER ROLES  (compact text format, parsed at start-up)
# =====================================================================
CAT_ORDER = ["Testing and QA", "DevOps and Cloud", "Backend", "Frontend", "Databases and Data",
             "Middleware and Integration", "Product and Business", "SAP"]
CUES += ["customer", "campaign", "revenue", "deal", "users", "metric", "stakeholder", "launched"]

SAP_ALIASES = {
    "abap": ["abap", "sap abap", "abap developer", "abap programming"],
    "fico": ["fico", "sap fico", "sap finance", "sap fi", "sap co", "sap controlling"],
    "mm": ["mm", "sap mm", "mm module", "sap materials", "sap procurement"],
    "sd": ["sd", "sap sd", "sd module", "sap sales"],
    "s4": ["s4", "s 4", "s4hana", "s 4 hana", "sap s4", "hana", "fiori", "sap basis", "sap btp",
           "sap general", "sap"],
}
for _k, _al in SAP_ALIASES.items():
    MODULES[_k]["aliases"] = _al
    MODULES[_k]["cat"] = "SAP"


def parse_bank(text):
    """## key|Name|Category|aliases   then   level|topic|question|group;group|ideal answer"""
    roles, cur = {}, None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#!"):
            continue
        try:
            if line.startswith("## "):
                key, name, cat, aliases = [x.strip() for x in line[3:].split("|", 3)]
                cur = roles[key] = {"name": name, "cat": cat, "questions": [],
                                    "aliases": [a.strip() for a in aliases.split(",") if a.strip()]}
            elif cur is not None and line[0].isdigit():
                lvl, topic, q, groups, ideal = line.split("|", 4)
                gl = [[w.strip() for w in g.split(",") if w.strip()] for g in groups.split(";")]
                cur["questions"].append(Q(min(3, max(0, int(lvl))), topic.strip(), q.strip(),
                                          [g for g in gl if g], ideal.strip()))
        except ValueError:
            print("(skipped a badly formatted line:", line[:60], ")")
    return roles


def load_bank_file(path):
    try:
        with open(path, encoding="utf-8") as f:
            extra = parse_bank(f.read())
        for k, r in extra.items():
            if r["questions"]:
                MODULES[k] = r
        return len(extra)
    except OSError as e:
        print("(could not read", path, ":", e, ")")
        return 0


for _t, _q, _g, _i in [
    ("Teamwork", "Tell me about a time you disagreed with a teammate or manager. How did you handle it?",
     [["listen", "understand", "perspective"], ["facts", "data", "evidence"], ["compromise", "agree", "aligned", "common ground"],
      ["communicate", "discuss", "talk", "escalate"], ["result", "outcome", "resolved"], ["learned", "lesson", "improved"]],
     "A strong answer shows listening to the other view, using facts, finding a compromise, communicating respectfully, and the result and what you learned."),
    ("Learning", "How do you keep your skills up to date, and how do you learn a new tool or technology quickly?",
     [["documentation", "docs", "official"], ["practice", "hands on", "small project", "build"], ["course", "tutorial", "video"],
      ["community", "blog", "mentor", "colleague", "forum"], ["apply", "real work", "project"], ["plan", "regular", "time", "schedule"]],
     "A strong answer mixes official documentation, hands on practice, courses, community and mentors, applying it in real work and a regular learning habit."),
    ("Strengths", "What are your strengths, and what is one weakness you are working on?",
     [["strength", "good at", "example"], ["weakness", "honest", "improve"], ["working on", "plan", "course", "practice"],
      ["feedback", "mentor", "review"], ["result", "progress", "better"]],
     "A strong answer names real strengths with an example, an honest weakness, and concrete steps and progress on it."),
]:
    BEHAVIOURAL.append(Q(1, "Behavioural", _q, _g, _i))
    BEHAVIOURAL[-1]["behav"] = True

BANK_TEXT = r'''## manual|Manual Testing / QA|Testing and QA|manual testing,manual tester,qa,quality assurance,software tester,test engineer,tester,qa engineer
0|Testing basics|What is the difference between verification and validation, and between QA and QC?|verification,verify,building the product right;validation,validate,building the right product;qa,quality assurance,process;qc,quality control,product|Verification checks we build the product right, validation checks we build the right product. QA is process oriented and prevents defects, QC is product oriented and finds them.
0|Test cases|What makes a good test case, and how is it different from a test scenario and a test plan?|test case,steps,expected result,precondition;scenario,high level;test plan,scope,strategy;traceability,requirement,rtm;clear,repeatable,atomic|A scenario is a high level idea to test, a test case has steps, data and an expected result, and a test plan covers scope, approach and schedule. A good test case is clear, atomic, traceable and repeatable.
1|Test design|Explain boundary value analysis, equivalence partitioning and decision tables with an example.|boundary value,boundary,edge;equivalence partitioning,equivalence class,partition;decision table,combination,condition;example,age,range;state transition,pairwise|Equivalence partitioning tests one value per group of similar inputs. Boundary value analysis tests the edges, like 17, 18 and 19 for an age limit of 18. Decision tables list condition combinations with expected outcomes.
1|Defect lifecycle|Describe the defect life cycle, and explain severity versus priority with examples.|new,open,assigned;fixed,retest,verified,closed;reopen,rejected,deferred,duplicate;severity,impact;priority,urgency,business;crash,typo,logo,example|A defect goes from new to assigned, fixed, retested and closed, or is reopened, rejected or deferred. Severity is technical impact, priority is urgency. A crash on a rare page is high severity, low priority. A wrong logo on the home page is the opposite.
2|Test types|Explain smoke, sanity, regression, exploratory and UAT testing, and when you use each.|smoke,build verification,bvt;sanity,narrow,after a fix;regression,existing functionality,automate;exploratory,unscripted,charter;uat,user acceptance,business users;retest,confirmation|Smoke checks the build is stable enough to test. Sanity is a narrow check after a small change. Regression protects existing functionality and suits automation. Exploratory is unscripted, charter based testing. UAT is done by business users before release.
2|Vague requirements|The requirements are vague and the release is in two days. What do you do as a tester?|clarify,ask,product owner,analyst;risk based,priority,critical flow;exploratory,assumption;document,notes,traceability;communicate,stakeholder,raise risk|Clarify with the product owner or analyst, note assumptions, test critical flows first using risk based testing, use exploratory testing for gaps, document coverage, and tell stakeholders about the risks early.
3|Test strategy|How would you build a test strategy for a new product covering risk, automation, environments and exit criteria?|risk,risk based,prioritise;scope,in scope,out of scope;automation,pyramid,regression suite;environment,test data,staging;entry criteria,exit criteria,definition of done;metrics,coverage,defect leakage,defect density|A test strategy defines scope, risks, test types and levels, the automation approach using the test pyramid, environments and data, entry and exit criteria, tools, roles and quality metrics.
3|Production leak|A critical defect leaked to production. How do you handle it and stop it happening again?|reproduce,logs,evidence;severity,impact,hotfix,rollback;communicate,stakeholder,customer;root cause,rca,why it escaped;regression test,automation,checklist,add test;process,review,shift left|Reproduce and assess impact, help decide hotfix or rollback, communicate to stakeholders, run a root cause analysis on why it escaped, then add regression tests and improve the process, for example earlier reviews.
## playwright|Playwright Automation|Testing and QA|playwright,playwrite,playright,playwright automation,playwright testing
0|Basics|What is Playwright, and how is it different from Selenium?|playwright,microsoft;browsers,chromium,firefox,webkit;auto wait,auto waiting,actionability;selenium,webdriver;languages,typescript,javascript,python,java;parallel,built in|Playwright is a Microsoft end to end testing framework for Chromium, Firefox and WebKit. Unlike Selenium it talks to browsers directly, has built in auto waiting, parallel execution, tracing and a test runner, and supports TypeScript, JavaScript, Python, Java and .NET.
0|Locators|Which locators does Playwright recommend, and why prefer them over XPath?|getbyrole,role;getbytext,text,label;getbytestid,test id;css,xpath;resilient,user facing,accessibility,stable|Playwright recommends user facing locators like getByRole, getByLabel, getByText and getByTestId because they mirror what users see and are more stable than CSS or XPath tied to the DOM structure.
1|Auto waiting|How does auto waiting work in Playwright, and when would you still need an explicit wait?|actionability,visible,enabled,stable;auto wait,auto waiting,retry;expect,web first assertion,tobevisible;waitforresponse,waitforurl,waitfor;hard wait,waitfortimeout,sleep;network,navigation|Before an action Playwright waits for the element to be attached, visible, stable and enabled, and web first assertions with expect retry until they pass. Use explicit waits like waitForResponse or waitForURL for network or navigation events, and avoid fixed sleeps.
1|Test structure|How do you structure a Playwright suite? Explain fixtures, the page object model and hooks.|fixture,test extend,custom fixture;page object,pom,class;beforeeach,aftereach,hooks;config,playwright config,projects;test data,env;tags,grep,annotations|Use the built in page, context and browser fixtures, extend them for shared setup, model pages with page objects, use beforeEach and afterEach hooks, and configure projects, retries, timeouts and reporters in playwright.config.
2|Authentication|How do you handle login efficiently across many tests, and run tests in parallel safely?|storage state,storagestate,saved session;global setup,setup project,login once;parallel,workers,fullyparallel;isolation,browser context,independent;test data,api login|Log in once in a setup project, save the session with storageState and reuse it. Each test gets an isolated browser context, tests run in parallel across workers, and they must use independent test data so they do not collide.
2|Network|How do you mock or intercept network calls in Playwright, and why would you?|route,page route,intercept;mock,fulfill,stub;har,routefromhar;abort,block;waitforresponse;flaky,isolate,third party,speed|Use page.route to intercept requests and fulfill them with mock data, abort unwanted calls, or replay a HAR file. This removes dependence on slow or flaky third parties, tests error states and makes tests fast and deterministic.
3|Flaky tests|Your Playwright suite has flaky tests in CI. How do you find the cause and fix them?|trace,trace viewer;video,screenshot,report;repeat each,rerun,retries;race condition,timing,web first assertion;isolation,shared data,order dependency;environment,workers,resources;locator,selector,strict|Capture traces, screenshots and video on failure and study them in the trace viewer, reproduce with repeat-each, then fix the cause: replace sleeps with web first assertions, remove shared state, stabilise locators and match workers to CI resources. Retries only hide the problem.
3|CI at scale|Describe how you would run Playwright at scale in CI with sharding, reporting and cross browser coverage.|ci,github actions,jenkins,pipeline;docker,container;shard,sharding;report,html report,allure,junit;projects,cross browser,chromium,webkit;artifacts,trace,video;tags,smoke|Run in a pipeline using the official Playwright Docker image, shard the suite across machines, define projects for Chromium, Firefox and WebKit, publish HTML or Allure and JUnit reports, upload traces and videos, and use tags to run smoke on every commit and the full suite nightly.
## selenium|Selenium Automation|Testing and QA|selenium,selenium webdriver,webdriver,selenium java,selenium python,testng,selenium automation
0|Basics|What is Selenium WebDriver, and what are the different locators?|webdriver,selenium,browser driver;id,name,classname;xpath,css selector,css;linktext,partial link text,tagname;chromedriver,geckodriver,driver|Selenium WebDriver automates browsers through browser drivers like chromedriver. Locators are id, name, class name, tag name, link text, partial link text, CSS selector and XPath.
0|Waits|What are implicit, explicit and fluent waits in Selenium, and which should you use?|implicit,global;explicit,webdriverwait,expected conditions;fluent,polling,ignore exception;thread sleep,hard wait,avoid;do not mix,timeout|Implicit wait applies globally to element lookups, explicit wait with WebDriverWait waits for a specific condition, and fluent wait adds polling and ignored exceptions. Prefer explicit waits, avoid Thread.sleep and avoid mixing implicit with explicit.
1|Framework|Explain the Page Object Model and how you structure a Selenium framework with TestNG or pytest.|page object,pom,page class;pagefactory,findby;testng,junit,pytest;base class,driver factory,utilities;data driven,dataprovider,parametrize,excel;reports,extent,allure;config,properties|The Page Object Model keeps locators and actions in page classes. A framework adds a base class and driver factory, data driven tests through TestNG DataProvider or pytest parametrize, config files, utilities and reports such as Extent or Allure.
1|Exceptions|What are StaleElementReference and NoSuchElement exceptions, and how do you handle them?|stale element,staleelementreferenceexception,dom refreshed,relocate;nosuchelement,not found,wrong locator;elementnotinteractable,not visible,scroll,overlay;timeout,explicit wait;iframe,switch to,shadow dom|A stale element means the DOM changed after you found it, so locate it again. NoSuchElement means a wrong locator or the element is not loaded yet, so check the locator and use explicit waits. ElementNotInteractable usually means hidden, covered or inside an iframe.
2|Advanced actions|How do you handle frames, windows, alerts, drag and drop and file uploads in Selenium?|iframe,frame,switchto;window,window handle,getwindowhandles;alert,accept,dismiss;actions,drag and drop,hover,movetoelement;sendkeys,upload,input type file;javascript executor|Switch into frames with switchTo().frame, move between windows with window handles, handle alerts with accept or dismiss, use Actions for hover and drag and drop, upload by sending the file path with sendKeys, and use JavascriptExecutor as a last resort.
2|Grid and parallel|What is Selenium Grid, and how do you run tests in parallel and across browsers?|grid,hub,node;remote webdriver,remotewebdriver,capabilities,options;parallel,threadlocal,thread safe;docker,selenoid,browserstack,saucelabs,cloud;cross browser,chrome,firefox,edge|Selenium Grid sends tests to nodes through a hub using RemoteWebDriver and browser options. For parallel runs make the driver thread safe with ThreadLocal and configure TestNG or pytest-xdist. Grid can run in Docker or on cloud providers like BrowserStack.
3|Flaky tests|Your Selenium tests are flaky and slow in CI. How do you improve reliability and speed?|explicit wait,synchronization;locator,stable,test id;isolation,independent,api setup,test data;parallel,headless,grid;retry,analyzer,flaky;screenshot,logs,video;environment,docker|Replace sleeps with explicit waits, use stable locators, make tests independent with API or database setup instead of UI steps, run headless and in parallel, capture screenshots and logs on failure, stabilise the environment and track flaky tests rather than only retrying.
3|Architecture|How would you design a scalable automation architecture covering UI, API and CI/CD with reporting?|layers,page object,service layer,api;ci cd,jenkins,github actions,pipeline;docker,grid,parallel;reporting,allure,dashboard;test data,environment;bdd,cucumber;code review,standards,maintenance;pyramid,smoke,regression|Use layers: UI page objects, an API service layer, utilities and test data management. Follow the test pyramid, run smoke on each commit and regression nightly in CI/CD using Docker and Grid, publish Allure dashboards, enforce code review and schedule suite maintenance.
## apitest|API Testing and Automation|Testing and QA|api testing,api automation,rest assured,restassured,postman,rest api testing,api tester
0|REST basics|What are the HTTP methods and common status codes, and what is the difference between PUT and PATCH?|get,post,put,patch,delete;200,201,204;400,401,403,404;500,502,503;idempotent,idempotency;replace,partial update|GET reads, POST creates, PUT replaces a whole resource, PATCH changes part of it and DELETE removes it. Common codes are 200, 201, 204, 400, 401, 403, 404 and 500. PUT, GET and DELETE are idempotent.
0|What to check|What do you check when testing a REST API?|status code,response code;response body,json,schema,payload;headers,content type;response time,latency,performance;authentication,authorization,token;negative,invalid input,error message|Check the status code, response body and schema, headers, response time, authentication and authorization, negative cases with invalid input and clear error messages, and that data is stored correctly end to end.
1|Auth|Explain API authentication methods: basic auth, API key, bearer token, OAuth 2.0 and JWT.|basic auth,username password,base64;api key,header;bearer,token,authorization header;oauth,access token,refresh token,scope;jwt,json web token,signature,claims,expiry|Basic auth sends encoded credentials, an API key identifies the client, a bearer token goes in the Authorization header. OAuth 2.0 issues scoped access and refresh tokens, and a JWT is a signed token with claims and an expiry the server can validate without a lookup.
1|Postman|How do you automate API tests in Postman, including environments, variables, tests and Newman?|collection,request,folder;environment,variable,global;tests,pm test,assertion,pm expect;pre request script,chaining,set variable;newman,cli,pipeline;data driven,csv,runner|Organise requests in collections, use environments and variables, write assertions in the Tests tab with pm.test, chain requests by saving values in variables, run data driven with the runner, and run in CI using Newman.
2|Automation code|How do you write API automation in REST Assured or a Python requests framework?|given when then,rest assured,restassured;requests,pytest,python;jsonpath,schema validation,json schema;request spec,response spec,reuse;pojo,serialization,deserialization,model;token,base uri,auth;logging,reports,allure|In REST Assured you use given, when, then with request and response specifications, validate with JsonPath and JSON schema and map bodies with POJOs. In Python use requests with pytest, fixtures for tokens and base URLs, schema validation and Allure reporting.
2|Contract testing|What is contract testing, and how does it differ from end to end API testing? Mention mocking.|contract,consumer,provider,pact;schema,openapi,swagger;mock,stub,wiremock,mockserver;end to end,integration,slow;microservices,independent,deploy;breaking change,version|Contract testing, for example with Pact, verifies that a provider meets what consumers expect without running the whole system, so microservices deploy independently and breaking changes are caught early. Mocks like WireMock isolate services, while end to end tests are slower and cover whole flows.
3|API security|What security tests would you run on an API? Mention the OWASP API risks.|owasp,api security,top 10;broken authorization,bola,idor,object level;authentication,token,jwt,expired;injection,sql injection,validation;rate limiting,throttling,brute force;excessive data,sensitive data,exposure;tls,https,cors|Test OWASP API risks: broken object level authorization (IDOR), weak authentication and token handling, injection through unvalidated input, missing rate limiting, excessive data exposure, bad CORS and no HTTPS, using tools like Burp or OWASP ZAP.
3|Framework design|Design an API automation framework for microservices covering data, environments, CI/CD and reporting.|layers,client,wrapper,service;environment,config,base url;test data,setup,teardown,cleanup,factory;ci cd,pipeline,jenkins,github actions;reporting,allure,junit,dashboard;parallel,independent,idempotent;mock,contract,stub;logging,assertion|Build layered code with API client wrappers and reusable specs, externalise environment config, create and clean test data with factories, keep tests independent so they run in parallel, mock dependencies and add contract tests, run in CI/CD and publish Allure or JUnit reports with request and response logs.
## appium|Mobile Test Automation (Appium)|Testing and QA|appium,mobile automation,mobile testing,android testing,ios testing,mobile tester
0|Basics|What is Appium and how does it work for Android and iOS?|appium,open source,cross platform;webdriver protocol,server,client;uiautomator2,android,espresso;xcuitest,ios;native,hybrid,mobile web;capabilities|Appium is an open source cross platform mobile automation tool using the WebDriver protocol with a server and client libraries. It drives Android through UiAutomator2 or Espresso and iOS through XCUITest, for native, hybrid and mobile web apps, configured through capabilities.
0|Locators|Which locator strategies do you use in Appium, and how do you inspect elements?|accessibility id,content desc;id,resource id;xpath,class name;uiautomator,ios predicate,class chain;appium inspector,uiautomatorviewer,inspect;stable,brittle|Prefer accessibility id and resource id, use UiAutomator selectors on Android and iOS predicate or class chain on iOS, and use XPath only as a last resort because it is slow and brittle. Inspect elements with Appium Inspector.
1|Gestures|How do you handle swipe, scroll, long press and pinch in Appium 2?|w3c actions,pointer,touch actions;swipe,scroll,flick;long press,tap,double tap;pinch,zoom;mobile commands,executescript;coordinates,percent,screen size|Use W3C Actions with pointer inputs for swipe, long press and pinch, or mobile: executeScript commands such as scrollGesture and swipeGesture, calculating coordinates as percentages of the screen size so tests work on different devices.
1|App states|How do you handle permissions, alerts, app install and reset, and deep links in mobile tests?|permission,autograntpermissions,alert;noreset,fullreset,reset,install;deep link,intent,url;package,activity,launch,background;adb,simctl;login,state,test data|Set capabilities like autoGrantPermissions and autoAcceptAlerts, control app state with noReset or fullReset, install and launch by app path or package, open screens through deep links, and use adb or simctl to prepare the device.
2|Framework|How do you design an Appium framework with page objects, parallel runs and reporting?|page object,pom,screen;driver factory,platform,base;parallel,threadlocal,multiple devices,ports;testng,junit,pytest,cucumber;reports,allure,extent;config,capabilities,environment|Use page objects per screen with a driver factory choosing the platform, make drivers thread safe, assign unique ports and devices for parallel runs, drive tests from TestNG, pytest or Cucumber, keep capabilities in config and report with Allure or Extent.
2|Device farms|How do you test across many devices with emulators, real devices and cloud farms?|emulator,simulator,virtual;real device,physical;cloud,browserstack,saucelabs,lambdatest,device farm;matrix,os versions,screen sizes,analytics;cost,speed;parallel|Use emulators and simulators for fast feedback, real devices for performance, sensors and manufacturer quirks, and cloud farms like BrowserStack or Sauce Labs for broad coverage. Build a device matrix from user analytics covering OS versions and screen sizes, and run in parallel.
3|Flaky tests|Your mobile tests are flaky. What causes it and how do you stabilise them?|explicit wait,synchronization,animation;locator,dynamic,stale;device,emulator,network;app state,reset,isolation,clean data;session,timeout,appium server;screenshot,video,logcat,logs;retry|Use explicit waits for animations and slow screens, stable locators, a clean app state and data for every test, healthy devices and network, sensible timeouts and sessions, and diagnose with screenshots, video and logcat rather than blind retries.
3|Strategy|How do you decide what to automate in mobile testing and balance it with manual testing and CI?|pyramid,unit,api,ui;critical flows,regression,smoke,repeatable;manual,exploratory,usability,gestures;roi,cost,maintenance;ci,pipeline,nightly,device farm;risk,analytics|Follow the test pyramid: keep most checks at unit and API level and automate only stable critical flows and regression on the UI. Keep exploratory, usability and gesture heavy testing manual, judge ROI against maintenance cost, run smoke on every build and the full suite nightly on a device farm.
## perf|Performance Testing|Testing and QA|performance testing,performance tester,jmeter,load testing,k6,gatling,loadrunner,stress testing,performance engineer
0|Test types|What are load, stress, spike, soak and scalability testing?|load,expected users;stress,breaking point,beyond;spike,sudden;soak,endurance,memory leak,long duration;scalability,scale;volume|Load testing checks behaviour at expected users. Stress testing pushes beyond limits to find the breaking point. Spike testing applies sudden surges. Soak or endurance testing runs long to find memory leaks. Scalability testing checks how performance changes as resources grow.
0|Metrics|Which metrics do you measure in performance testing, and what do percentiles tell you?|response time,latency;throughput,requests per second,tps,rps;error rate,errors;percentile,p90,p95,p99;concurrent users,virtual users,vusers;cpu,memory,resource utilisation|Key metrics are response time, throughput, error rate, concurrent users and server resource use such as CPU and memory. Percentiles like p95 and p99 show what the slowest users experience, which the average hides.
1|JMeter|Explain the main JMeter components: thread group, samplers, listeners, assertions, timers and config elements.|thread group,threads,ramp up,loop;sampler,http request;listener,results,summary report;assertion,response assertion;timer,think time,constant timer;config element,csv data set,header manager;controller,logic|A thread group defines users, ramp up and loops, samplers send requests, assertions validate responses, timers add think time, config elements like CSV Data Set supply data, controllers add logic and listeners show results, though heavy listeners should be avoided during runs.
1|Workload model|How do you design a realistic workload model for a performance test?|production,analytics,logs,real usage;critical scenarios,business flows,transaction mix;peak,concurrent users,arrival rate,littles law;think time,pacing;test data,unique,parameterize;ramp up,steady state;sla,nfr,targets|Use production analytics or logs to find the critical business flows, their transaction mix and peak load, convert it into arrival rate or concurrent users with think time and pacing, use unique parameterised data, ramp up to a steady state and compare against agreed SLAs.
2|Correlation|What are correlation and parameterization in performance scripts, and how do you handle dynamic values like session ids?|correlation,dynamic value,extract;parameterization,parameterisation,csv,data;regular expression,json extractor,boundary extractor,xpath;session id,token,csrf,viewstate;replay,recording,script fails;variable|Correlation extracts dynamic server values like session IDs or CSRF tokens from a response using regex or JSON extractors and passes them to later requests. Parameterisation replaces hard coded data such as users with values from a CSV so a recorded script replays correctly under load.
2|High load|How do you generate very high load, and what is distributed testing in JMeter, k6 or Gatling?|distributed,controller,agents,remote;multiple machines,generators,cloud;non gui,cli,headless;k6,gatling,locust,as code,scripting;network,bandwidth,generator limits;monitor,generator cpu|Run tests in non GUI mode and distribute load across several load generators, for example a JMeter controller with agents or k6 and Gatling in the cloud, while monitoring the generators so they do not become the bottleneck and making sure bandwidth is enough.
3|Bottlenecks|Response times degrade at 500 users. How do you find the bottleneck?|monitoring,apm,dynatrace,newrelic,grafana,prometheus;cpu,memory,disk,network;database,slow query,index,connection pool,locks;thread pool,garbage collection,gc,heap;profiling,thread dump,code;correlate,timeline,response time vs load;cache,load balancer,scaling|Correlate response time against load with monitoring or APM, then check each tier: CPU, memory, disk and network, database slow queries, indexes, connection pools and locks, application thread pools, garbage collection and heap, and profile the code with thread dumps. Fix the biggest bottleneck first and retest.
3|Performance in CI|How do you include performance testing in an agile CI/CD pipeline and set pass or fail criteria?|ci cd,pipeline,jenkins,gitlab,github actions;shift left,every build,nightly,early;baseline,benchmark,trend,regression;thresholds,sla,pass fail,quality gate;smoke,small load;dashboard,grafana,influxdb;production like,environment|Run small performance smoke tests on every build and larger tests nightly with tools like k6 or JMeter, compare against a baseline, set thresholds on percentiles and error rate as quality gates, show trends on Grafana dashboards and use a production like environment so results are meaningful.
## sdet|Test Automation / SDET|Testing and QA|test automation,automation testing,automation engineer,sdet,cypress,bdd,cucumber,qa automation,automation tester
0|Test pyramid|What is the test automation pyramid, and what should and should not be automated?|pyramid,unit,integration,ui;unit tests,fast,cheap;ui tests,slow,brittle;automate,repeatable,regression,stable,critical;exploratory,one time,usability,changing|The pyramid has many fast unit tests at the base, fewer integration and API tests in the middle and a few UI tests on top. Automate repeatable, stable, critical regression checks. Do not automate exploratory, one off, usability or rapidly changing areas.
0|BDD|What is BDD, and how do Gherkin and Cucumber work?|bdd,behaviour driven,behavior driven;gherkin,given when then,feature file,scenario;cucumber,step definition,glue;collaboration,business,three amigos;scenario outline,examples,data table;living documentation|BDD is behaviour driven development where business and engineers agree behaviour through examples. Gherkin feature files use Given, When, Then scenarios, Cucumber maps each step to code through step definitions, and scenario outlines run one scenario with different data.
1|Framework parts|What components make a good test automation framework?|page object,pom,design pattern;data driven,external data,json,csv;config,environment;reporting,allure,extent,logs;utilities,helpers,driver factory;ci,version control,git;modular,reusable,maintainable;cross browser,parallel|A good framework is modular and reusable with design patterns such as page objects, supports data driven tests, externalised configuration, logging and reports, parallel and cross browser execution, version control and CI integration, and is easy to maintain.
1|Cypress|How is Cypress different from Selenium and Playwright, and what are its limitations?|cypress,runs in browser,same run loop;automatic waiting,retry;time travel,debugging,dashboard;javascript,node;limitations,multi tab,iframe,cross origin,single language;network stubbing,intercept;selenium,playwright|Cypress runs inside the browser alongside the app, with automatic waiting, time travel debugging and easy network stubbing through cy.intercept. It is JavaScript only and historically weaker for multiple tabs and cross origin flows, where Playwright or Selenium are more flexible.
2|Test data|How do you manage test data and environments for automation reliably?|test data,data factory,builder,faker;api,database,seed,setup;isolation,unique,independent,cleanup,teardown;environment,docker,containers;mock,stub,service virtualization;data masking,production data,pii;idempotent|Create data through APIs or database seeding and data factories at test start, keep each test isolated with unique data and clean up afterwards, use containers for repeatable environments, mock unstable dependencies and mask personal data when using production like data.
2|CI/CD|How do you integrate automation in a CI/CD pipeline, and which suites run when?|ci cd,pipeline,jenkins,github actions,gitlab;on commit,pull request,smoke;nightly,full regression,scheduled;parallel,shard,docker;quality gate,fail,block merge;report,notification,slack,dashboard;flaky,quarantine|Run unit and smoke tests on every commit or pull request as quality gates, the full regression nightly or before release, in parallel in containers, publish reports and notifications, and quarantine flaky tests so they do not block the pipeline.
3|Flaky strategy|How do you deal with flaky tests across a large suite and measure the health of your automation?|flaky,intermittent,quarantine;root cause,timing,shared state,environment;metrics,pass rate,flaky rate,execution time;dashboard,trend,history;owner,fix,sla,policy;retry,limit;stability,reliability,coverage|Track flaky and pass rates over time, quarantine flaky tests quickly, assign owners with a fix deadline, find root causes such as timing, shared state and environment, limit retries so they do not hide real bugs, and watch execution time and coverage as health metrics.
3|Shift left|What does shift left mean for quality, and how can an SDET improve quality beyond testing?|shift left,early,requirements;code review,static analysis,sonarqube,linting;unit tests,coverage,tdd;contract,api,integration;observability,monitoring,production;feature flags,canary,test in production;culture,developers own quality,pairing;risk,metrics|Shift left means preventing defects early through requirement reviews, code reviews, static analysis, unit tests with coverage or TDD and contract tests, while also using monitoring, feature flags and canary releases in production, and building a culture where developers share ownership of quality.
## devops|DevOps Engineer|DevOps and Cloud|devops,devops engineer,ci cd,cicd,docker,kubernetes,jenkins,terraform,cloud engineer,aws,release engineer
0|CI/CD|What is CI/CD and what are the stages of a typical pipeline?|continuous integration,ci,merge;continuous delivery,continuous deployment,cd;build,compile;test,unit test;artifact,registry;deploy,staging,production|CI builds and tests every merged change automatically. CD delivers or deploys releases automatically. A pipeline builds, tests, scans, stores an artifact, then deploys to staging and production.
0|Docker|What is the difference between a Docker image and a container, and a container and a VM?|image,template,layers;container,running instance,process;dockerfile,build;vm,virtual machine,hypervisor,guest os;shares kernel,lightweight,isolation|An image is a read only template built from a Dockerfile, a container is a running instance of it. Containers share the host kernel so they are light, while VMs carry a full guest OS on a hypervisor.
1|Kubernetes|Explain pods, deployments, services and ingress in Kubernetes.|pod,smallest unit;deployment,replicaset,rolling update;service,clusterip,nodeport,loadbalancer;ingress,routing,host;configmap,secret;namespace,node|A pod runs containers. A deployment manages replicas and rolling updates. A service gives pods a stable address and load balancing. Ingress routes external HTTP traffic by host and path. ConfigMaps and secrets hold configuration.
1|Git branching|Explain GitFlow versus trunk based development, and how you resolve a merge conflict.|gitflow,develop,release,hotfix;trunk based,short lived,feature flags;pull request,code review;merge conflict,rebase,merge,resolve;main,protected branch|GitFlow uses long lived develop and release branches. Trunk based development merges small changes to main often behind feature flags. Use pull requests with review and resolve conflicts by merging or rebasing and fixing the conflicting hunks.
2|Terraform|What is Infrastructure as Code, and how does Terraform manage state, modules and environments?|infrastructure as code,iac,declarative;terraform,provider,resource;state,tfstate,remote state,lock,backend;plan,apply,drift;modules,reuse;workspaces,tfvars,environments|IaC defines infrastructure in versioned code. Terraform declares resources through providers, tracks them in a state file in a remote locked backend, previews with plan, applies changes, reuses modules and separates environments with variables or workspaces.
2|Deployments|Compare blue green, canary and rolling deployments, and explain how you roll back.|blue green,two environments,switch;canary,small percentage,gradual;rolling,one by one;rollback,previous version,revert,helm rollback;health check,readiness,liveness;database migration|Blue green keeps two environments and switches traffic, canary sends a small share to the new version first, rolling replaces instances gradually. Use health checks to gate steps and roll back by redeploying or switching back, taking care with database migrations.
3|Pipeline security|How do you secure a CI/CD pipeline and the software supply chain (DevSecOps)?|secrets,vault,not in code;sast,static analysis,sonarqube;dependency scan,sca,snyk;image scan,trivy,signing;least privilege,rbac,iam;sbom,supply chain;shift left|Keep secrets in a vault, scan code with SAST, dependencies with SCA and images with tools like Trivy, sign artifacts, produce an SBOM, apply least privilege to runners and cloud roles, and shift these checks left into the pipeline.
3|Incident|Production is down right after a deployment. Walk me through your response.|rollback,revert,mitigate;monitoring,alerts,logs,dashboard;communicate,incident commander,status page,stakeholders;root cause,rca,postmortem,blameless;prevent,canary,runbook,action items|First restore service by rolling back or mitigating, using monitoring and logs to confirm impact, communicate through a status page and an incident lead, then find the root cause and write a blameless postmortem with actions such as canary releases and runbooks.
## aiops|AIOps, MLOps and SRE|DevOps and Cloud|aiops,ai ops,mlops,ml ops,sre,site reliability,site reliability engineer,observability,aiops engineer
0|SRE basics|What is SRE, and what are SLI, SLO, SLA and error budgets?|sre,site reliability;sli,indicator,measure;slo,objective,target;sla,agreement,contract;error budget,allowed failure,release velocity;availability,latency|SRE applies software engineering to operations. An SLI is a measured indicator like latency, an SLO is the target for it, an SLA is the contractual promise, and the error budget is the allowed unreliability that balances reliability against release speed.
0|Observability|What are the pillars of observability, and how is it different from monitoring?|metrics;logs;traces,tracing,distributed tracing;monitoring,known problems,dashboards;observability,unknown unknowns,explore;prometheus,grafana,elk,opentelemetry|Observability rests on metrics, logs and traces. Monitoring watches for known failures with dashboards and alerts, while observability lets you ask new questions about unknown problems from rich telemetry, using tools like Prometheus, Grafana, ELK and OpenTelemetry.
1|What is AIOps|What is AIOps and what problems does it solve for operations teams?|aiops,artificial intelligence for it operations;anomaly detection,baseline;alert noise,correlation,deduplication,event correlation;root cause,rca,topology;prediction,forecast,capacity;automation,remediation,auto healing;machine learning|AIOps applies machine learning to operations data to detect anomalies, cut alert noise by correlating and deduplicating events, find probable root causes, predict capacity problems and trigger automated remediation.
1|Alerting|How do you design good alerts and reduce alert fatigue?|actionable,symptom based,user impact;slo based,burn rate,thresholds;severity,paging,priority;deduplicate,group,suppress;runbook,documentation;tune,review,noisy alerts;on call|Alert on symptoms that affect users and need action, ideally SLO burn rate, with clear severity and linked runbooks, grouped and deduplicated notifications, and regular tuning of noisy alerts so on call engineers are not fatigued.
2|MLOps|What is MLOps, and how do you take a model from training to production?|mlops,machine learning operations;data versioning,dvc,feature store;experiment tracking,mlflow,model registry;pipeline,training,automation,ci cd;deployment,serving,api,batch,canary;monitoring,drift|MLOps applies DevOps to machine learning: version data, code and models, track experiments, automate training and validation pipelines, register models, deploy through serving APIs or batch with canary releases, and monitor accuracy and drift in production.
2|Drift|What are data drift and concept drift, and how do you monitor models in production?|data drift,input distribution,feature;concept drift,relationship,target;metrics,accuracy,precision;statistical test,psi,ks test,kl divergence;retrain,trigger,schedule;alert,dashboard;ground truth,labels|Data drift is a change in input distributions, concept drift is a change in the relationship between inputs and the target. Monitor input statistics with tests like PSI or KS, track model metrics when labels arrive, alert on thresholds and trigger retraining.
3|Auto remediation|How would you build automated incident detection and remediation using ML and runbooks?|anomaly detection,baseline,seasonality;event correlation,topology,cmdb;runbook automation,auto remediation,self healing;safety,approval,human in the loop,blast radius,rollback;false positives,feedback,tune;integration,pagerduty,servicenow,slack;mttr,mttd|Detect anomalies against seasonal baselines, correlate events using service topology, map known incident types to runbook automation, add safety through approvals, limited blast radius and rollback, integrate with PagerDuty or ServiceNow, and measure MTTD, MTTR and false positives.
3|Capacity|How do you do capacity planning and autoscaling with forecasting, and what are the risks?|forecast,trend,seasonality,time series;autoscaling,hpa,scale out;metrics,cpu,queue length,custom metrics;headroom,buffer,peak;cost,finops,over provisioning;load test,validate;cooldown,flapping|Forecast demand from historical time series with seasonality, choose scaling metrics such as CPU or queue length, keep headroom for peaks, validate with load tests, set cooldowns to avoid flapping, and balance reliability against cloud cost.
## java|Java Backend|Backend|java,java developer,spring,spring boot,java backend,j2ee,java engineer,core java
0|OOP|What are the pillars of OOP in Java, and how does an abstract class differ from an interface?|encapsulation;inheritance;polymorphism,overriding,overloading;abstraction;abstract class,state,constructor;interface,multiple inheritance,default method,contract|The pillars are encapsulation, inheritance, polymorphism and abstraction. An abstract class can hold state and constructors and a class extends only one, while a class can implement many interfaces, which define a contract and can have default methods.
0|Collections|Explain List, Set and Map, and how HashMap works internally.|list,arraylist,linkedlist,ordered;set,hashset,unique,treeset;map,key value,hashmap,treemap;hashcode,equals,bucket;collision,linked list,tree;load factor,resize,capacity|List keeps ordered duplicates, Set holds unique elements and Map stores key value pairs. HashMap uses the key's hashCode to choose a bucket and equals to find the entry, handles collisions with lists or trees and resizes at the load factor.
1|JVM memory|Explain JVM memory areas, garbage collection and how you diagnose a memory leak.|heap,young,old,metaspace;stack,thread;garbage collection,gc,g1,mark and sweep;memory leak,static reference,unclosed,listener;heap dump,jmap,visualvm,mat;outofmemoryerror;xmx,tuning|The heap holds objects in young and old generations, each thread has a stack and metaspace holds class data. GC reclaims unreachable objects. For a leak, take a heap dump with jmap and analyse it with MAT or VisualVM to find objects held by static references, caches or listeners.
1|Concurrency|How do you handle concurrency in Java: synchronized, volatile, ExecutorService and ConcurrentHashMap?|synchronized,lock,monitor;volatile,visibility;atomic,atomicinteger,cas;executorservice,thread pool;concurrenthashmap,thread safe;deadlock,race condition;completablefuture,future|synchronized and locks give mutual exclusion, volatile guarantees visibility, atomics use compare and swap, executors manage thread pools, ConcurrentHashMap is a thread safe map and CompletableFuture composes async work. Avoid races and deadlocks with consistent lock ordering.
2|Spring Boot|Explain Spring Boot: dependency injection, auto configuration, bean scopes and common annotations.|dependency injection,di,ioc,inversion of control;autoconfiguration,auto configuration,starter;bean,singleton,prototype,scope;component,service,repository,controller,restcontroller;autowired,constructor injection;application properties,profiles|Spring's IoC container injects dependencies, ideally through constructors. Spring Boot adds starters and auto configuration, beans are singletons by default, stereotype annotations like Service, Repository and RestController register them, and profiles and properties drive configuration.
2|JPA|Explain JPA and Hibernate, the N+1 problem, lazy versus eager loading and transactions.|jpa,hibernate,orm,entity;n 1,n plus 1,join fetch,entity graph,batch;lazy,eager,fetch;transactional,transaction,rollback,propagation;cache,first level,second level|JPA maps entities to tables and Hibernate implements it. N+1 means one query plus one per row for lazy associations, fixed with join fetch, entity graphs or batching. Lazy loads on demand, eager loads upfront, and @Transactional defines transaction boundaries.
3|Microservices|How do you design resilient Java microservices: communication, circuit breakers, idempotency and distributed transactions?|rest,grpc,kafka,messaging,async;circuit breaker,resilience4j,retry,timeout,fallback;idempotent,idempotency key,duplicate;saga,eventual consistency,outbox;api gateway,service discovery;tracing,observability;bulkhead,rate limit|Use REST or gRPC and asynchronous messaging such as Kafka, protect calls with timeouts, retries, circuit breakers and bulkheads using Resilience4j, make operations idempotent, handle distributed transactions with sagas and the outbox pattern, and add tracing and logging.
3|Performance|A Spring Boot service shows high latency and CPU under load. How do you diagnose and fix it?|profiling,jfr,flame graph,async profiler,visualvm;thread dump,blocked;gc,pauses,heap;database,slow query,index,connection pool,hikari;cache,redis,caffeine;n 1,batch;apm,actuator,micrometer,metrics;load test|Profile with JFR or async profiler and take thread dumps, check GC pauses, inspect slow database queries, indexes and the Hikari pool, fix N+1 queries, add caching, watch metrics through Actuator and Micrometer or an APM, and verify the fix with a load test.
## python|Python Backend|Backend|python,python developer,django,flask,fastapi,python backend,python engineer
0|Data types|What is the difference between a list, tuple, set and dictionary in Python, and what is mutability?|list,mutable,ordered;tuple,immutable;set,unique,unordered;dictionary,dict,key value;mutable,immutable,hashable;comprehension|Lists are ordered and mutable, tuples are ordered and immutable, sets hold unique unordered items, and dicts map keys to values. Only immutable, hashable objects can be dict keys or set members.
0|Functions|What are *args and **kwargs, decorators and generators in Python?|args,positional,tuple;kwargs,keyword,dictionary;decorator,wrapper,functools wraps;generator,yield,lazy,memory;iterator,next;closure|*args collects extra positional arguments and **kwargs extra keyword arguments. A decorator wraps a function to add behaviour. A generator uses yield to produce values lazily and saves memory.
1|GIL|What is the GIL, and when do you use threading, multiprocessing or asyncio?|gil,global interpreter lock,one thread;threading,io bound;multiprocessing,cpu bound,processes;asyncio,event loop,async await,coroutine;concurrency,parallelism;celery,workers|The GIL lets only one thread run Python bytecode at a time, so threads help only for I/O bound work. Use multiprocessing for CPU bound tasks, and asyncio with async and await for many concurrent I/O operations.
1|Memory and copies|Explain Python memory management, shallow versus deep copy, and dunder methods.|reference counting,garbage collector,gc,cycles;shallow copy,deep copy,copy module,reference;dunder,init,str,repr,magic method;mutable default argument,pitfall;slots|Python uses reference counting plus a cyclic garbage collector. A shallow copy copies the container but shares inner objects, a deep copy copies everything. Dunder methods such as __init__ and __repr__ customise object behaviour, and mutable default arguments are a classic pitfall.
2|Frameworks|Compare Django, Flask and FastAPI, and explain the Django ORM and middleware.|django,batteries included,admin,orm;flask,micro,lightweight;fastapi,async,pydantic,type hints,openapi;orm,models,migrations,queryset;middleware,request response;select related,prefetch related,n 1;rest framework,drf,serializer|Django is batteries included with ORM, admin, migrations and middleware. Flask is a micro framework. FastAPI is async with Pydantic validation and automatic OpenAPI docs. Use select_related and prefetch_related to avoid N+1 queries in the Django ORM.
2|Testing|How do you test Python code with pytest: fixtures, parametrization, mocking and coverage?|pytest,assert;fixture,setup,teardown,conftest;parametrize,data driven;mock,patch,monkeypatch;coverage,pytest cov;ci,tox;unit,integration|pytest uses plain asserts, fixtures for setup and teardown, parametrize for data driven cases, mock or monkeypatch to isolate dependencies and pytest-cov for coverage, all run in CI.
3|Performance|A Python API is slow. How do you profile and optimise it?|profile,cprofile,py spy,line profiler;bottleneck,hot path;database,query,index,n 1;cache,redis,lru cache;async,workers,gunicorn,uvicorn;algorithm,data structure,complexity;numpy,c extension|Profile with cProfile or py-spy to find hot paths, fix database queries and N+1 problems, add caching with Redis or lru_cache, pick better algorithms and data structures, use async or more workers with Gunicorn or Uvicorn, and move heavy numerics to NumPy.
3|Production service|How do you design a production Python service: packaging, config, logging, dependencies and deployment?|venv,virtualenv,poetry,pip tools,lock file,requirements;configuration,environment variables,twelve factor;logging,structured,json;type hints,mypy,ruff,linting,black;docker,container,gunicorn;ci cd,tests;monitoring,sentry,metrics|Isolate dependencies with venv and a lock file through Poetry or pip-tools, configure through environment variables, use structured logging, enforce type hints and linting with mypy and ruff, containerise with Docker behind Gunicorn, run tests in CI/CD and add monitoring such as Sentry.
## golang|Go (Golang)|Backend|go,golang,go developer,go backend,go engineer,go lang
0|Basics|What are the key features of Go, and how do slices differ from arrays?|compiled,fast,static typing;simple,garbage collected;goroutines,concurrency;array,fixed size;slice,dynamic,length,capacity,backing array;append,copy|Go is a compiled, statically typed, garbage collected language with simple syntax and built in concurrency. Arrays have a fixed size, slices are dynamic views over a backing array with length and capacity, and append may reallocate.
0|Errors|How does error handling work in Go, and what are defer, panic and recover?|error,return value,if err;errors is,errors as,wrap,errorf;defer,cleanup,lifo;panic,recover,unexpected;custom error;no exceptions|Go returns errors as values that you check explicitly and wrap with fmt.Errorf and %w, inspecting with errors.Is and errors.As. defer schedules cleanup in LIFO order, and panic and recover are only for unrecoverable situations.
1|Goroutines|Explain goroutines, channels, the sync package and how Go avoids data races.|goroutine,lightweight,scheduler;channel,buffered,unbuffered;sync,mutex,waitgroup;select,timeout;race detector,data race;context,cancellation;share memory by communicating|Goroutines are lightweight threads managed by the Go scheduler. Channels pass data between them, buffered or unbuffered, select waits on several, and sync.Mutex and WaitGroup coordinate. Detect data races with the race detector and use context for cancellation.
1|Interfaces|How do interfaces work in Go, and what are the empty interface and embedding?|interface,implicit,duck typing,method set;empty interface,any,type assertion,type switch;struct,embedding,composition;pointer receiver,value receiver;nil interface;small interfaces|Interfaces are satisfied implicitly by having the methods, with no implements keyword. The empty interface any holds any value and needs type assertions. Go prefers composition through struct embedding, and pointer versus value receivers affect the method set.
2|Concurrency patterns|Describe worker pools, fan out fan in, and how to prevent goroutine leaks.|worker pool,jobs channel,workers;fan out,fan in;context,cancel,done channel,timeout;goroutine leak,blocked,never exits;errgroup,waitgroup;pipeline;backpressure,buffered channel|A worker pool runs a fixed number of goroutines reading jobs from a channel, fan out distributes work and fan in merges results. Prevent leaks by giving every goroutine an exit path through context cancellation or a done channel, and use errgroup to manage them.
2|Web services|How do you build a production REST or gRPC service in Go: routing, middleware, graceful shutdown and config?|net http,http server,handler,mux,gin,chi,echo;middleware,logging,auth,recover;graceful shutdown,context,signal,shutdown;configuration,environment,viper;grpc,protobuf;timeouts|Use net/http or a router like chi or gin with middleware for logging, auth and panic recovery, set server timeouts, shut down gracefully on signals with Server.Shutdown and a context, load config from the environment, and use gRPC with protobuf for internal services.
3|Performance|How do you profile and optimise a Go service? Mention pprof, escape analysis and allocations.|pprof,cpu profile,heap profile;benchmark,go test bench;allocations,gc pressure,sync pool;escape analysis,heap,stack;trace,go tool trace;preallocate,slice capacity,strings builder;mutex contention|Use pprof for CPU and heap profiles, benchmarks and go tool trace, reduce allocations and GC pressure with preallocated slices, strings.Builder and sync.Pool, understand escape analysis, and look for lock contention.
3|Testing and design|How do you structure and test Go projects: packages, dependency injection, table driven tests and mocks?|table driven,subtests,t run;interface,mock,fake,dependency injection;package,internal,cmd,project layout;go test,coverage;testify,gomock;integration,testcontainers;race,benchmark|Organise by packages with cmd and internal directories, depend on small interfaces so dependencies can be faked, write table driven tests with subtests, measure coverage, run with the race detector, and use testcontainers for integration tests.
## ruby|Ruby on Rails|Backend|ruby,rails,ruby on rails,ror,ruby developer,rails developer
0|Rails basics|What is Ruby on Rails, and what do convention over configuration and MVC mean?|rails,framework,ruby;convention over configuration,conventions;mvc,model,view,controller;dry,dont repeat yourself;generators,scaffold;routes,gem,bundler|Rails is a Ruby web framework following MVC, with convention over configuration so sensible defaults reduce setup, and DRY to avoid repetition. It ships generators, routing, ActiveRecord and gems managed by Bundler.
0|Ruby objects|What is the difference between a block, proc and lambda in Ruby, and what are symbols?|block,yield,do end;proc,object;lambda,strict arguments,return;symbol,immutable,memory,identifier;string,mutable;each,map,enumerable|A block is an anonymous chunk of code passed to a method. A proc is an object wrapping a block with lenient arguments, a lambda is stricter about arguments and returns from itself. Symbols are immutable unique identifiers, lighter than strings.
1|ActiveRecord|Explain ActiveRecord associations, validations, callbacks and the N+1 query problem.|has many,belongs to,has one,many to many;validation,validates,presence,uniqueness;callback,before save,after commit;n 1,includes,eager load,preload,bullet;scope,query;migration;transaction|ActiveRecord maps models to tables with associations like has_many and belongs_to, validations and callbacks. N+1 queries are solved with includes, preload or eager_load, detected with the Bullet gem.
1|Request cycle|Walk through a Rails request cycle, and explain routing, strong parameters and CSRF.|routes,router;controller,action;strong parameters,permit,mass assignment;csrf,authenticity token,forgery;middleware,rack;view,render,json;session,cookie|A request passes through Rack middleware to the router, which dispatches to a controller action. Strong parameters whitelist attributes against mass assignment, CSRF tokens protect forms, and the controller renders a view or JSON.
2|Background jobs|How do you handle background jobs and caching in Rails?|sidekiq,active job,resque,delayed job;redis,queue;retry,idempotent;cache,fragment caching,russian doll;cache store,memcached,redis;expiry,cache key;async,email|Use Active Job with Sidekiq backed by Redis for background work like email, make jobs idempotent with retries, and speed pages with fragment or Russian doll caching in Redis or Memcached with proper cache keys and expiry.
2|Testing|How do you test Rails apps with RSpec or Minitest: factories, mocks and system tests?|rspec,minitest;factory bot,fixtures,factories;mock,stub,double,webmock,vcr;request spec,model spec,controller;system test,capybara,feature;coverage,simplecov;tdd,ci|Use RSpec or Minitest with model, request and system specs, FactoryBot for data, doubles and WebMock or VCR for external calls, Capybara for browser flows, and track coverage in CI.
3|Performance|A Rails app is slow in production. How do you find and fix bottlenecks?|profiling,apm,new relic,scout,skylight,rack mini profiler;slow query,explain,index;n 1,includes;caching,fragment;background job,offload;puma,workers,threads,memory;pagination,pluck;gc,memory bloat|Measure with an APM or rack-mini-profiler, fix slow queries with EXPLAIN and indexes, remove N+1 queries, add caching, move slow work to background jobs, tune Puma workers and threads, paginate and use pluck, and watch memory and GC.
3|Architecture|How do you keep a large Rails codebase maintainable: service objects, engines, API design and security?|service object,interactor,single responsibility;concern,fat model,skinny controller;engine,modular,monolith;api,versioning,serializer;security,brakeman,sql injection,xss;upgrade,dependencies,bundler audit;rubocop|Keep controllers and models thin with service objects and concerns, modularise with engines, version APIs and use serializers, run Brakeman and bundler-audit for security, enforce style with RuboCop and upgrade Rails and gems regularly.
## perl|Perl Developer|Backend|perl,perl developer,pearl,perl scripting,perl programmer
0|Data types|What are scalars, arrays and hashes in Perl, and what do the sigils mean?|scalar,dollar;array,at sign;hash,percent,key value;context,list context,scalar context;reference;my,our,local;strict,warnings|Scalars start with $, arrays with @ and hashes with %. Perl behaves differently in scalar and list context. Use my for lexical variables and always use strict and warnings.
0|Regex|Explain regular expressions in Perl: capture groups, and match versus substitute versus transliterate.|match,m//;substitution,s///;tr,transliterate;capture group,parentheses,dollar one;modifiers,global,case insensitive;greedy,non greedy,lazy;named capture|Perl has built in regex: m// matches, s/// substitutes and tr/// transliterates. Parentheses capture groups into $1 and so on, modifiers like g and i change behaviour, and quantifiers can be greedy or non greedy.
1|References|What are references in Perl, how do you build nested data structures, and what is autovivification?|reference,pointer;nested,hash of arrays,array of hashes;dereference,arrow;autovivification,auto create;data dumper,ref;anonymous;weaken,circular|References point to data and allow nested structures such as hashes of arrays, built with anonymous [] and {} and dereferenced with the arrow. Autovivification creates intermediate structures automatically on access, which can surprise you.
1|File handling|How do you read and write files and handle errors in Perl? What are $_, @ARGV and $@?|open,filehandle,read,write,close;die,or die,eval;default variable,underscore;argv,command line;error,eval error;while,line by line,chomp;three arg open,lexical filehandle|Use three argument open with a lexical filehandle, check failure with or die, and read line by line in a while loop with chomp. $_ is the default variable, @ARGV holds command line arguments and $@ holds the eval error.
2|Modules and OO|Explain Perl modules, CPAN, packages and object oriented Perl with bless.|module,package,use,require;cpan,cpanm;bless,object,constructor,new;isa,inheritance,use parent;moose,moo;exporter,namespace;perldoc,pod|A module is a package in a .pm file loaded with use and installed from CPAN. Objects are references blessed into a package with a constructor named new, inheritance uses use parent or @ISA, and Moose or Moo simplify OO Perl.
2|Log processing|How would you process a large log file in Perl to find errors and summarise counts efficiently?|line by line,stream,while;regex,match;hash,count,aggregate;sort,keys;printf,sprintf,report;one liner,perl ne;memory,slurp|Read line by line in a while loop instead of slurping the file, match with a regex, count into a hash keyed by error type, then sort the keys and print a report with printf. One liners with perl -ne are handy for quick jobs.
3|Testing and quality|How do you test and maintain Perl code with Test::More, Perl::Critic, taint mode and debugging?|test more,prove,tap;perl critic,perltidy,lint;taint mode,untaint,security;debugger,data dumper,carp;strict,warnings;nytprof,profile;cpan,dependencies|Write tests with Test::More run through prove, keep style with Perl::Critic and perltidy, use taint mode for untrusted input, debug with the perl debugger, Data::Dumper and Carp, and profile with Devel::NYTProf.
3|Modernising|How do you improve performance and modernise a legacy Perl application?|profiling,nytprof;algorithm,data structure,hash lookup;references,avoid copies;dbi,prepared statement,bind;psgi,plack,mod perl,fastcgi;modernise,moose,tests,refactor,incremental;cpan,xs|Profile with Devel::NYTProf, use better algorithms and hash lookups, pass references instead of copies, use DBI prepared statements, serve through PSGI or Plack instead of CGI, and modernise incrementally by adding tests first and then refactoring with modern OO and CPAN modules.
## rust|Rust Developer|Backend|rust,rust developer,rustlang,rust backend,rust engineer
0|Ownership|Explain ownership, borrowing and lifetimes in Rust.|ownership,owner,move;borrow,reference,mutable reference;borrow checker,one mutable,many immutable;lifetime,dangling,scope;drop,raii,memory safety;copy,clone|Each value has one owner and is dropped when the owner goes out of scope. You can borrow it by reference, either many immutable or one mutable at a time, and the borrow checker with lifetimes prevents dangling references, giving memory safety without a garbage collector.
0|Errors|What are Option and Result in Rust, and how do you handle errors?|option,some,none,null;result,ok,err;match,pattern matching;question mark,propagate;unwrap,expect,panic;thiserror,anyhow,custom error;enum|Option represents a value that may be absent, Result represents success or failure. Handle them with match, propagate with the ? operator, avoid unwrap in production code, and define error types with thiserror or use anyhow in applications.
1|Traits|Explain traits, generics and trait objects, and static versus dynamic dispatch.|trait,interface,behaviour;generic,monomorphization;trait object,dyn,box dyn,vtable;static dispatch,dynamic dispatch;derive,trait bound;compile time,runtime cost|Traits define shared behaviour. Generics with trait bounds use static dispatch through monomorphization, which is fast but grows code size. Trait objects with dyn use dynamic dispatch through a vtable, allowing different types at runtime with a small cost.
1|Smart pointers|What are Box, Rc, Arc, RefCell and Mutex, and when do you use each?|box,heap,single owner;rc,reference counting,single thread;arc,atomic,thread safe;refcell,interior mutability,runtime borrow;mutex,rwlock,lock;send,sync;weak,cycle|Box puts data on the heap with one owner, Rc shares ownership in a single thread, Arc is the thread safe version, RefCell allows interior mutability checked at runtime, and Mutex or RwLock guard shared state across threads, with Send and Sync marking thread safety.
2|Concurrency|How does Rust make concurrency safe? Explain threads, channels and async with Tokio.|send,sync,fearless concurrency;thread,spawn,join;channel,mpsc,message passing;mutex,arc;async,await,future,tokio;data race,compile time;rayon,parallel|Ownership with the Send and Sync traits prevents data races at compile time. Use threads with channels or Arc<Mutex<T>>, async with futures run by an executor like Tokio for I/O heavy work, or Rayon for data parallelism.
2|Cargo|How do you manage projects with Cargo, including crates, features, workspaces and testing?|cargo,cargo toml,crate;features,optional;workspace,multiple crates;cargo test,unit tests,integration tests,doc tests;clippy,rustfmt,lint;crates io,dependencies,lock file;release,profile|Cargo builds and manages dependencies from crates.io through Cargo.toml and Cargo.lock, supports optional features and workspaces, runs unit, integration and doc tests with cargo test, and keeps quality with clippy and rustfmt.
3|Unsafe and FFI|When and how do you use unsafe Rust, and how do you call C code?|unsafe,raw pointer,dereference;invariants,safe abstraction,wrap;ffi,extern c,bindgen;miri,audit,sanitizer;responsibility,no guarantees;repr c|Unsafe lets you dereference raw pointers, call unsafe functions and FFI, and the programmer must uphold the safety invariants. Keep unsafe blocks small behind safe abstractions, use extern C and bindgen for C interop, and test with Miri.
3|Performance|How do you write and profile high performance Rust? Mention zero cost abstractions and allocations.|zero cost abstraction,iterator,inlining;allocation,clone,heap;profile,flamegraph,perf,criterion,benchmark;release mode,lto,opt level;data layout,cache;simd,rayon,parallel;cow,borrow|Use iterators and generics that compile to tight code, avoid needless clones and heap allocations, benchmark with Criterion, profile with flamegraph or perf, build in release mode with LTO, and think about data layout, cache use and parallelism with Rayon.
## oracle|Oracle Database and PL/SQL|Databases and Data|oracle,oracle dba,pl sql,plsql,oracle database,oracle developer,oracle sql
0|DML and DDL|What is the difference between DELETE, TRUNCATE and DROP, and between UNION and UNION ALL in Oracle?|delete,dml,rollback,where;truncate,ddl,no rollback,fast;drop,remove table;union,remove duplicates,sort;union all,duplicates,faster;commit|DELETE is DML, can use WHERE and can be rolled back. TRUNCATE is DDL, removes all rows quickly and cannot be rolled back. DROP removes the table itself. UNION removes duplicates, UNION ALL keeps them and is faster.
0|Joins|Explain inner, left, right and full outer joins, and what a self join is.|inner join,matching;left join,left outer,all left;right join;full outer join,all rows;self join,same table,hierarchy;cross join;on clause|An inner join returns matching rows, a left join returns all left rows with matches or nulls, a right join the reverse, and a full outer join all rows from both. A self join joins a table to itself, for example employees and managers.
1|PL/SQL|What are procedures, functions, packages and triggers in PL/SQL, and why use packages?|procedure,no return;function,return value;package,specification,body;trigger,before,after,row level;cursor,loop;exception,when others;bulk collect,forall|A procedure performs actions, a function returns a value, a package groups related code in a specification and body with encapsulation and better performance, and a trigger fires automatically on DML. Handle errors in the exception block and use BULK COLLECT and FORALL for speed.
1|Indexes|What types of indexes exist in Oracle, and when is an index not used?|b tree,btree,default;bitmap,low cardinality;function based;composite,multiple columns;unique;function on column,implicit conversion,leading column,low selectivity;full table scan,explain plan|B-tree indexes are the default, bitmap indexes suit low cardinality columns, function based indexes index expressions and composite indexes cover several columns. An index may be ignored when a function is applied to the column, there is an implicit conversion, the leading column is not used or selectivity is low.
2|SQL tuning|How do you tune a slow Oracle SQL query? Mention explain plan, statistics, hints and AWR.|explain plan,execution plan,dbms xplan;statistics,gather stats,optimizer;index,full table scan;hint,use index;awr,ash,addm,statspack;bind variables,hard parse,shared pool;sql tuning advisor,tkprof,sql trace|Read the execution plan with EXPLAIN PLAN or DBMS_XPLAN, keep optimizer statistics current, check index use and join methods, use bind variables to avoid hard parsing, use hints sparingly, and analyse with AWR, ASH, SQL Tuning Advisor or TKPROF.
2|Architecture|Explain the Oracle architecture: SGA, PGA, background processes, redo and undo.|sga,shared pool,buffer cache;pga,private;background process,dbwr,lgwr,smon,pmon;redo,redo log,recovery;undo,rollback,read consistency;control file,datafile,tablespace;instance|The instance has memory (SGA with buffer cache and shared pool, plus a private PGA per session) and background processes like DBWR, LGWR, SMON and PMON. Redo logs record changes for recovery, undo holds old values for rollback and read consistency, and the database is datafiles, control files and redo logs.
3|Backup and recovery|Explain Oracle backup and recovery with RMAN, archivelog mode and Data Guard.|rman,backup,restore;archivelog,archive log mode;point in time recovery,pitr,recover;full,incremental,hot backup;data guard,standby,disaster recovery,failover;flashback;rac,asm|Run in ARCHIVELOG mode and use RMAN for full and incremental hot backups, then restore and recover to a point in time using archived redo. Data Guard keeps a standby for disaster recovery and failover, and flashback undoes logical mistakes quickly.
3|Blocking|Users report hanging sessions. How do you diagnose locks, deadlocks and wait events in Oracle?|v session,blocking session,blocker;v lock,dba blockers;deadlock,ora 00060,trace;wait event,ash,v session wait;row lock,uncommitted,commit;kill session;awr,tuning;application,fix|Query V$SESSION and V$LOCK to find the blocking session and its SQL, usually an uncommitted transaction holding a row lock, check wait events through ASH or AWR, review deadlock traces for ORA-00060, kill the session if needed and fix the application to commit sooner and lock in a consistent order.
## frontend|Frontend (HTML, CSS, JavaScript)|Frontend|frontend,front end,javascript,js,html,css,web developer,ui developer,frontend developer,front end developer
0|CSS|What is the CSS box model, and what is the difference between flexbox and grid?|box model,content,padding,border,margin;box sizing,border box;flexbox,one dimension,row,column;grid,two dimensions,rows and columns;position,relative,absolute,fixed;specificity,cascade;semantic html|The box model is content, padding, border and margin, and box-sizing border-box includes padding and border in the width. Flexbox lays out in one dimension, grid in two. Semantic HTML and understanding specificity and the cascade keep CSS predictable.
0|JavaScript basics|What is the difference between var, let and const, and what are closures and hoisting?|var,function scope;let,const,block scope;hoisting,declaration;closure,inner function,outer variable;temporal dead zone,tdz;strict equality,triple equals;scope|var is function scoped and hoisted, let and const are block scoped with a temporal dead zone, and const cannot be reassigned. A closure is a function that remembers variables from its outer scope even after the outer function has returned.
1|Async JavaScript|Explain the event loop, promises, async await and the microtask queue.|event loop,single thread,call stack;callback queue,task queue,macrotask;microtask,promise,then;async await;settimeout;web api,non blocking;promise all,error handling,try catch|JavaScript is single threaded with an event loop that runs the call stack, then microtasks such as promise callbacks, then macrotasks like setTimeout. async and await are syntax over promises, and Promise.all runs promises in parallel.
1|DOM events|What are event bubbling, capturing and delegation, and how do you improve DOM performance?|bubbling,bubble up;capturing,capture phase;delegation,parent listener,event target;stoppropagation,preventdefault;reflow,repaint,layout;document fragment,batch;debounce,throttle;requestanimationframe|Events capture down and then bubble up the DOM. Event delegation attaches one listener on a parent and uses event.target. Reduce reflow and repaint by batching DOM changes, and use debounce, throttle and requestAnimationFrame for frequent events.
2|Web performance|How do you improve page load performance and Core Web Vitals?|lcp,inp,cls,core web vitals;lazy loading,images,code splitting;minify,bundle,compression,gzip,brotli;cdn,caching,cache headers;critical css,defer,async;image optimisation,webp,srcset;lighthouse,devtools|Improve LCP, INP and CLS by optimising and lazy loading images in modern formats, code splitting and minifying bundles, compressing with gzip or Brotli, using a CDN and cache headers, deferring non critical scripts, inlining critical CSS and measuring with Lighthouse.
2|Security|What are XSS, CSRF and CORS, and how do you protect a frontend?|xss,cross site scripting,escape,sanitize,innerhtml;csrf,token,samesite;cors,origin,preflight;content security policy,csp;httponly,secure cookie,localstorage;https;npm audit,dependency|XSS injects scripts, prevented by escaping output, avoiding innerHTML and using a CSP. CSRF abuses a logged in session, prevented with tokens and SameSite cookies. CORS controls cross origin requests through headers and preflight. Use HttpOnly secure cookies, HTTPS and audit dependencies.
3|Accessibility|How do you build accessible web apps? Mention ARIA, semantic HTML and keyboard navigation.|semantic html,landmarks,headings;aria,roles,labels;keyboard,focus,tab order;screen reader,alt text;contrast,wcag,color;testing,axe,lighthouse;forms,labels|Use semantic HTML first, add ARIA only where needed, ensure full keyboard navigation with visible focus, provide alt text and labels, meet WCAG colour contrast, and test with a screen reader and tools like axe and Lighthouse.
3|Architecture|How do you architect a large frontend: state, components, micro frontends and testing?|component,reusable,design system;state management,redux,context,zustand,store;micro frontends,module federation,independent deploy;testing,unit,jest,testing library,cypress,playwright,e2e;bundler,webpack,vite,tree shaking;typescript,types;ci,lint,performance budget|Build reusable components within a design system, keep state predictable with a store such as Redux or Zustand, consider micro frontends for independent team deployments, use TypeScript, lint and performance budgets, and test with Jest and Testing Library plus end to end tests.
## react|React Developer|Frontend|react,reactjs,react js,react developer,react native,next js,nextjs
0|Basics|What is React, what is JSX, and what is the virtual DOM?|react,library,components;jsx,javascript xml;virtual dom,diffing,reconciliation;component,props,state;declarative;one way data flow|React is a library for building UIs from components. JSX is HTML like syntax inside JavaScript. The virtual DOM is an in memory tree that React diffs to update only what changed in the real DOM. Data flows one way from parent props to children.
0|Props and state|What is the difference between props and state, and class versus functional components?|props,read only,parent;state,local,rerender;functional,hooks;class,lifecycle;usestate,setstate;lifting state up|Props are read only inputs from the parent, state is local data that triggers a re-render when it changes. Functional components with hooks are the modern approach and replace class components and their lifecycle methods. Share state by lifting it up.
1|Hooks|Explain useEffect, useMemo, useCallback and useRef, and the rules of hooks.|useeffect,side effect,dependency array,cleanup;usememo,memoize value;usecallback,memoize function;useref,mutable,dom reference;rules of hooks,top level,only in components;custom hook|useEffect runs side effects after render, controlled by its dependency array and a cleanup function. useMemo and useCallback memoise values and functions, useRef holds a mutable value or DOM node without re-rendering. Hooks must be called at the top level of components or custom hooks.
1|Lists and forms|Why are keys needed in lists, and what are controlled and uncontrolled components?|key,unique,stable,not index;reconciliation,identity;controlled,state,onchange;uncontrolled,ref,default value;form,validation,react hook form;conditional rendering|Keys give list items a stable identity so React reconciles changes correctly, and indexes are a poor key when the list changes. A controlled input keeps its value in state, an uncontrolled input keeps it in the DOM and is read through a ref.
2|State management|When would you use Context, Redux or other state libraries, and how do you avoid prop drilling?|context,provider,prop drilling,rerender;redux,store,reducer,action,dispatch,toolkit;zustand,recoil,mobx;react query,swr,server state,cache;local state,global state;selectors|Use local state by default, Context for low frequency shared values like theme, and Redux Toolkit or Zustand for complex global client state. Server data is better handled by React Query or SWR with caching. Use selectors and split contexts to avoid needless re-renders.
2|Performance|How do you find and fix performance problems in React, such as unnecessary re-renders?|react memo,memo,pure;usememo,usecallback;profiler,react devtools;code splitting,lazy,suspense;virtualization,windowing,react window;state placement,key;debounce|Find hotspots with the React Profiler, prevent needless renders with React.memo, useMemo and useCallback, keep state close to where it is used, split code with lazy and Suspense, and virtualise long lists.
3|Rendering modes|Explain CSR, SSR, SSG and ISR, and when you would use Next.js.|csr,client side rendering,spa;ssr,server side rendering;ssg,static,build time;isr,incremental,revalidate;next js,nextjs,routing,api routes;seo,first load,hydration;server components|CSR renders in the browser, SSR renders per request on the server, SSG pre-renders at build time and ISR revalidates static pages over time. Next.js provides these with file based routing and server components, helping SEO and first load, followed by hydration on the client.
3|Testing and structure|How do you test and structure a large React application?|react testing library,jest,unit;user behaviour,accessibility,getbyrole;cypress,playwright,e2e;msw,mock api;folder structure,feature based;typescript,types;error boundary;storybook,design system|Test behaviour with Jest and React Testing Library, mock APIs with MSW, cover critical flows end to end with Cypress or Playwright, use TypeScript, error boundaries and a feature based folder structure, and document components in Storybook as part of a design system.
## angular|Angular and Vue|Frontend|angular,angularjs,vue,vuejs,vue js,typescript,angular developer,vue developer
0|Basics|What is Angular, and what are components, modules, services and directives?|angular,typescript,framework;component,template,selector;module,ngmodule,standalone;service,injectable,dependency injection;directive,ngif,ngfor,structural;decorator;cli|Angular is a TypeScript framework. Components combine a template and class, services hold shared logic provided through dependency injection, directives like ngIf and ngFor change the DOM, and modules or standalone components organise the app, scaffolded by the Angular CLI.
0|Data binding|Explain data binding in Angular: interpolation, property, event and two way binding.|interpolation,curly braces;property binding,square brackets;event binding,parentheses;two way,ngmodel,banana in a box;one way;template reference;pipes|Interpolation shows values, property binding [prop] sets DOM properties, event binding (event) handles events, and two way binding [(ngModel)] combines them. Pipes transform displayed values.
1|RxJS|What are Observables, Subjects and common RxJS operators, and how do you avoid memory leaks?|observable,stream,subscribe;subject,behaviorsubject,replaysubject;operators,map,switchmap,mergemap,filter,debounce time;unsubscribe,async pipe,takeuntil,memory leak;promise,lazy,cancel;http client|Observables are lazy streams you subscribe to, Subjects multicast values, and operators like map, switchMap and debounceTime transform them. Avoid leaks with the async pipe, takeUntil or unsubscribing on destroy, and use switchMap to cancel stale HTTP requests.
1|Lifecycle|What are Angular lifecycle hooks, and what is change detection?|ngoninit,ngonchanges,ngondestroy;ngafterviewinit,constructor;change detection,zone,dirty check;onpush,immutable,performance;trackby;signals|ngOnInit runs after inputs are set, ngOnChanges on input changes and ngOnDestroy for cleanup. Change detection checks bindings after async events through zone.js, and OnPush with immutable inputs or signals reduces the work.
2|Routing|How do routing, guards, resolvers and lazy loading work in Angular?|router,routes,router outlet,routerlink;guard,canactivate,authentication;resolver,preload data;lazy loading,loadchildren,bundle size;route params,query params;interceptor,http|The router maps URLs to components shown in a router outlet. Guards like canActivate protect routes, resolvers fetch data before activation, and lazy loading loads feature code on demand to cut bundle size. HTTP interceptors add auth headers.
2|Forms|Compare template driven and reactive forms, and how you do validation in Angular.|template driven,ngmodel,simple;reactive,formgroup,formcontrol,formbuilder;validators,required,custom validator,async validator;valuechanges,dynamic;touched,dirty,invalid;testable|Template driven forms use ngModel and suit simple cases, reactive forms build a FormGroup in code and are more scalable and testable. Validation uses built in, custom and async validators and form state like touched, dirty and invalid.
3|Performance|How do you improve Angular app performance?|onpush,change detection;lazy loading,preload;trackby,ngfor;aot,build optimizer,tree shaking;pure pipe,memoize;virtual scroll,cdk;ssr,universal,hydration;bundle,analyzer|Use OnPush change detection, lazy loading, trackBy in ngFor, pure pipes instead of methods in templates, virtual scrolling, AOT and tree shaking, SSR with hydration, and analyse bundle size.
3|Vue and architecture|How do Vue and Angular differ, and how do you structure large apps with state management and testing?|vue,composition api,reactivity,pinia,vuex;angular,opinionated,framework;ngrx,store,state management,signals;testing,jasmine,karma,jest,cypress;nx,monorepo,libraries;standalone,feature modules,lazy;typescript|Vue is progressive and lighter with a reactivity system, the Composition API and Pinia, while Angular is opinionated with built in routing, forms and dependency injection. Large apps use feature modules, state libraries like NgRx, signals or Pinia, monorepos, strict TypeScript and unit plus end to end tests.
## sqldb|SQL and Database Developer|Databases and Data|sql,sql developer,database developer,db developer,db team,rdbms,mysql,postgres,data analyst sql,database
0|Keys|What are primary, foreign and unique keys, and what is normalization?|primary key,unique,not null;foreign key,referential integrity;unique key;normalization,redundancy,1nf,2nf,3nf;denormalization,performance;index|A primary key uniquely identifies a row, a foreign key enforces referential integrity with another table and a unique key prevents duplicates. Normalisation removes redundancy through normal forms, denormalisation trades it for read speed.
0|Joins and grouping|What is the difference between WHERE and HAVING, and between INNER and LEFT JOIN?|where,filter rows,before group;having,after group,aggregate;group by,count,sum,avg;inner join,matching;left join,all left,null;order by|WHERE filters rows before grouping, HAVING filters groups after aggregation. An inner join returns only matching rows, a left join keeps all rows from the left table with nulls where nothing matches.
1|Window functions|Explain window functions like ROW_NUMBER, RANK and LAG, and how to find the second highest salary.|window function,over,partition by;row number,rank,dense rank;lag,lead;order by;second highest,limit offset,subquery,dense rank;cte|Window functions compute across related rows without collapsing them, using OVER with PARTITION BY and ORDER BY. ROW_NUMBER, RANK and DENSE_RANK number rows, LAG and LEAD read neighbours. The second highest salary is DENSE_RANK = 2, or a subquery or LIMIT OFFSET.
1|Transactions|What are ACID properties and isolation levels, and what problems do they prevent?|atomicity,consistency,isolation,durability;isolation level,read committed,repeatable read,serializable;dirty read,phantom read,non repeatable read;commit,rollback;lock,deadlock|ACID means atomicity, consistency, isolation and durability. Isolation levels from read uncommitted to serializable trade performance against anomalies like dirty reads, non repeatable reads and phantom reads.
2|Indexing|How do indexes work, and when do they hurt? Explain clustered, non clustered and covering indexes.|b tree,balanced tree;clustered,physical order,primary key;non clustered,pointer;covering index,include;composite,column order,leftmost;write overhead,slow inserts,updates;selectivity,cardinality;explain,execution plan|Most indexes are B-trees that speed lookups. A clustered index defines physical order, non clustered indexes store pointers, a covering index holds all columns a query needs. Indexes slow writes and use space, composite indexes depend on column order, and EXPLAIN shows whether they are used.
2|Query tuning|A query on a million row table is slow. How do you optimise it?|execution plan,explain;index,missing index;select star,columns needed;join order,subquery,rewrite;statistics,analyze;partitioning,pagination;caching,materialized view;sargable,function on column|Read the execution plan, add or fix indexes, select only needed columns, write sargable conditions without functions on indexed columns, rewrite subqueries as joins, update statistics, consider partitioning or materialised views, and paginate large results.
3|Schema design|How would you design a schema for an e-commerce system, and when would you denormalize or partition?|orders,customers,products,order items;foreign key,normalize;price snapshot,price history;index;partitioning,sharding,by date,archive;denormalize,read heavy,reporting;transaction,inventory,consistency|Model customers, products, orders and order items with foreign keys in third normal form, store price snapshots on order items, index common lookups, protect inventory with transactions, and partition or archive big order tables by date, denormalising only for read heavy reporting.
3|Scaling|How do you scale a relational database: replication, sharding, caching and read replicas, and what are the trade offs?|replication,primary,replica,read replica;sharding,partition key,shard;caching,redis;cap theorem,consistency,availability;replication lag,eventual;connection pooling;vertical,horizontal|Scale reads with replicas and caching and writes with sharding on a partition key, accepting replication lag, harder joins and operational complexity. Use connection pooling, scale vertically first, and understand the CAP trade offs.
## dba|Database Administrator|Databases and Data|dba,database administrator,postgresql,mysql dba,mongodb,nosql,db admin,db administrator,postgres dba
0|DBA role|What does a DBA do, and what is the difference between SQL and NoSQL databases?|backup,recovery;performance,tuning;security,users,access;availability,replication;monitoring,capacity;sql,relational,schema,acid;nosql,flexible,scale,document,key value|A DBA keeps databases available, secure and fast: backups and recovery, tuning, user access, replication, monitoring and capacity planning. SQL databases are relational with schemas and ACID, NoSQL databases like MongoDB or Redis offer flexible models and horizontal scale.
0|Backups|What types of backups exist, and what are RPO and RTO?|full,incremental,differential;logical,physical,dump,pg dump,mysqldump;point in time recovery,binlog,wal;rpo,data loss;rto,downtime,recovery time;test restore,verify;retention|Backups are full, incremental or differential, logical like mysqldump or pg_dump or physical, with point in time recovery from binlogs or WAL. RPO is acceptable data loss, RTO is acceptable downtime, and restores must be tested regularly.
1|Replication|Explain replication and high availability in MySQL or PostgreSQL, including failover.|primary,replica,standby,master slave;streaming replication,binlog,wal;synchronous,asynchronous,lag;failover,promote,patroni,orchestrator,repmgr;read replica;split brain,fencing;monitor|A primary streams changes (binlog or WAL) to replicas, synchronously or asynchronously with some lag. On failure a replica is promoted using tools like Patroni or Orchestrator, with fencing to avoid split brain, and replicas can serve reads.
1|Performance|How do you find slow queries and tune a database server?|slow query log,pg stat statements,performance schema;explain,analyze,plan;index,missing;buffer pool,shared buffers,memory,config;connection pool,max connections,pgbouncer;vacuum,statistics;locks,wait|Enable the slow query log or pg_stat_statements, analyse with EXPLAIN ANALYZE, add indexes, tune memory such as the InnoDB buffer pool or shared_buffers, use connection pooling, keep statistics and vacuum healthy and check lock waits.
2|PostgreSQL internals|Explain MVCC, VACUUM and WAL in PostgreSQL.|mvcc,multiversion,snapshot,readers do not block;vacuum,dead tuples,bloat,autovacuum;wal,write ahead log,durability,recovery;checkpoint;transaction id,wraparound;analyze,statistics|MVCC keeps multiple row versions so readers do not block writers. VACUUM reclaims dead tuples and prevents bloat and transaction id wraparound, and WAL logs changes before they reach data files for durability, recovery and replication.
2|Security|How do you secure a production database?|least privilege,roles,grants;encryption,tls,at rest;audit,logging;network,firewall,private,vpc;patching,updates;password,secrets,rotation;sql injection,parameterized;backup encryption|Use least privilege roles, encrypt in transit and at rest, restrict network access, audit access, patch regularly, rotate secrets, encrypt backups and enforce parameterised queries in applications.
3|NoSQL|Compare MongoDB, Redis and Cassandra, and when would you pick each? Explain sharding and consistency.|mongodb,document,flexible schema,replica set;redis,in memory,cache,key value,ttl;cassandra,wide column,write heavy,partition key,eventual consistency;sharding,shard key;consistency,cap,quorum;use case,tradeoff|MongoDB suits flexible documents with replica sets and sharding on a shard key, Redis is an in memory store for caching, sessions and queues, and Cassandra suits very high write volume with tunable consistency and partition keys. Choose by access pattern and consistency needs under CAP.
3|Disaster recovery|Production data was corrupted by a bad deployment at 2 pm. How do you recover?|stop,contain,freeze writes;point in time recovery,pitr,restore;backup,wal,binlog;restore to new instance,verify,compare;communicate,stakeholders,rto;root cause,prevent,review;delayed replica|Stop further damage, communicate, restore the latest backup to a separate instance and replay logs to just before 2 pm (point in time recovery), verify and selectively copy back or switch over, then find the root cause and prevent it, for example with a delayed replica, approvals and migration testing.
## middleware|Middleware and Messaging|Middleware and Integration|middleware,kafka,rabbitmq,mq,activemq,tomcat,weblogic,websphere,mulesoft,esb,integration,message queue,integration engineer
0|Middleware basics|What is middleware and why is it used in enterprise architecture?|middleware,integration,connect systems;decouple,loose coupling;messaging,api,esb;heterogeneous,protocols,transform;reliable,scalable;kafka,mq,mulesoft,tomcat|Middleware is software between applications that lets heterogeneous systems communicate, handling messaging, transformation, routing and reliability so systems stay loosely coupled. Examples include message brokers, ESBs and application servers.
0|Messaging|What is the difference between a queue and a topic, and between synchronous and asynchronous communication?|queue,point to point,one consumer;topic,publish subscribe,many subscribers;synchronous,wait,request response;asynchronous,decoupled,message;broker,producer,consumer;acknowledgement|A queue delivers each message to one consumer, a topic broadcasts to all subscribers. Synchronous calls wait for a response and couple availability, asynchronous messaging decouples producers from consumers through a broker.
1|Kafka|Explain Kafka topics, partitions, consumer groups and offsets, and how it gives ordering and scalability.|topic,partition;consumer group,parallel;offset,commit;broker,replication,leader;ordering within partition,key;retention,log;zookeeper,kraft;producer,acks|A Kafka topic is split into partitions, each an ordered log replicated across brokers. Consumers in a group share partitions for parallelism and track offsets, ordering is guaranteed only within a partition by message key, and messages are kept for a retention period.
1|Delivery semantics|What are at most once, at least once and exactly once delivery, and how do you handle duplicates?|at most once,may lose;at least once,duplicates,retry;exactly once,transactions,idempotent producer;idempotent consumer,deduplicate,message id;acknowledgement,ack;dead letter queue,dlq,poison message;backoff,retry|At most once may lose messages, at least once may duplicate them, exactly once needs idempotent producers and transactions. Make consumers idempotent using message IDs, and send failing messages to a dead letter queue after retries with backoff.
2|Brokers|Compare RabbitMQ, ActiveMQ, IBM MQ and Kafka. When would you use each?|rabbitmq,exchange,routing,amqp;activemq,jms;ibm mq,enterprise,transactional;kafka,streaming,throughput,replay;queue,broker;use case,tradeoff;ordering,persistence|RabbitMQ and ActiveMQ are traditional brokers with flexible routing and AMQP or JMS, IBM MQ is enterprise grade with strong transactional guarantees, and Kafka is a distributed log for high throughput streaming and replay. Choose by routing needs, throughput, ordering and operational skills.
2|Application servers|How do you deploy and tune Java applications on Tomcat, WebLogic or WebSphere?|tomcat,war,servlet container;weblogic,websphere,jboss,wildfly,java ee;jvm,heap,gc,xmx;thread pool,connection pool,datasource;cluster,load balancer,session replication,sticky;logs,thread dump,monitoring;ssl,deployment|Deploy WAR or EAR files, tune JVM heap and GC, thread pools and JDBC datasource connection pools, cluster behind a load balancer with sticky sessions or session replication, secure with SSL, and troubleshoot with logs and thread dumps.
3|Integration patterns|Describe enterprise integration patterns, API gateways, and when to use MuleSoft or an ESB.|enterprise integration patterns,eip,router,transformer,aggregator,splitter;api gateway,rate limiting,authentication;mulesoft,esb,anypoint,connectors;orchestration,choreography;transformation,mapping;canonical model;saga|Patterns such as content based routing, transformation, splitter and aggregator solve common integration problems. An API gateway handles authentication, rate limiting and routing. An ESB or MuleSoft orchestrates many systems with connectors and mapping, though event based choreography can be lighter.
3|Consumer lag|Messages are piling up in a queue and consumers are lagging. How do you diagnose and fix it?|consumer lag,backlog,queue depth;monitoring,metrics,dashboard;scale consumers,partitions,parallelism;slow consumer,processing time,downstream,database;poison message,dlq,retry loop;batch,prefetch,throughput;backpressure,rate limit|Check queue depth and consumer lag metrics, find why consumers are slow, such as a slow database or downstream service, look for poison messages stuck in retry loops and move them to a DLQ, scale consumers or partitions, tune batching and prefetch, and apply backpressure to producers.
## product|Product Manager|Product and Business|product manager,product management,product owner,pm,product team,product,associate product manager,apm
0|PM role|What does a product manager do, and how is it different from a project manager and a product owner?|vision,strategy,roadmap;customer,problem,user needs;prioritise,backlog;cross functional,engineering,design,stakeholders;project manager,delivery,timeline;product owner,backlog,scrum;metrics,outcomes|A product manager owns the why and what: vision, strategy, customer problems, roadmap and priorities, working across engineering, design and business. A project manager owns delivery of timelines and resources, and a product owner manages the backlog within Scrum.
0|Prioritisation|How do you prioritise features? Explain frameworks like RICE, MoSCoW and Kano.|rice,reach,impact,confidence,effort;moscow,must have,should have,could have;kano,delight,basic;value vs effort;stakeholders,data,strategy;roadmap;opportunity cost|RICE scores reach, impact, confidence and effort, MoSCoW sorts into must, should, could and won't, and Kano separates basic, performance and delight features. I combine frameworks with data, strategy and stakeholder input, and explain the trade offs.
1|Discovery|How do you discover customer problems and validate an idea before building it?|user research,interviews,customer;survey,data,analytics;problem,jobs to be done,pain points;prototype,mvp,experiment,a b test;hypothesis,assumption,validate;competitor,market;persona|Run user interviews and surveys, analyse behavioural data, frame the problem with jobs to be done, form hypotheses, and test with prototypes, an MVP or A/B tests before committing engineering effort, while studying competitors and the market.
1|Metrics|Which metrics do you track for a product? Explain north star, AARRR, retention, churn and conversion.|north star,metric;aarrr,pirate metrics,acquisition,activation,retention,revenue,referral;cohort,retention;churn;conversion,funnel;dau,mau,engagement;ltv,cac,arpu;leading,lagging|A north star metric captures delivered value, AARRR covers acquisition, activation, retention, revenue and referral, and cohort retention, churn, conversion funnels, engagement like DAU and MAU and unit economics such as LTV and CAC show health. Pair leading with lagging indicators.
2|Roadmap and stakeholders|How do you build a roadmap and say no to a senior stakeholder's request?|roadmap,now next later,themes,outcomes;strategy,goals,okr;data,evidence,customer value;trade off,capacity,opportunity cost;communicate,transparent,alternatives;alignment,stakeholders;backlog|Build an outcome based roadmap tied to strategy and OKRs. To say no, explain trade offs and opportunity cost with data, offer alternatives or a later slot, keep communication transparent and align on priorities rather than just refusing.
2|Agile delivery|How do you work with engineering in agile: user stories, acceptance criteria, sprint planning and scope changes?|user story,as a,i want,so that;acceptance criteria,definition of done;sprint planning,backlog refinement,grooming;scope change,tradeoff,descope,change request;mvp,iteration;estimation,story points,capacity;demo,retrospective|Write user stories as a, I want, so that with clear acceptance criteria, refine the backlog with the team, plan sprints within capacity, handle scope changes by trading off or descoping, and use demos and retrospectives to improve.
3|Strategy|How would you define a product strategy and decide whether to build, buy or partner for a new market?|vision,mission,market;competitive advantage,differentiation,moat;target segment,tam,sam,som,market size;build buy partner,tradeoff,cost,time;positioning,pricing,go to market;okr,roadmap;risk|Start from the vision and a target segment with sizing (TAM, SAM, SOM), define differentiation and a moat, positioning, pricing and go to market, then decide build, buy or partner by cost, speed, strategic importance and risk.
3|Metric drop|Daily active users dropped 15 percent last week. How do you investigate and respond?|verify data,instrumentation,bug;segment,platform,region,cohort,new vs returning;timeline,release,change,seasonality;funnel,drop off,retention;external,competitor,outage,marketing;hypothesis,prioritise;fix,experiment,communicate|First verify the data and instrumentation, then segment by platform, region, cohort and user type, compare with releases, outages, seasonality, marketing and competitors, locate the funnel step that dropped, test hypotheses, fix or roll back, and communicate to stakeholders.
## sales|Sales (B2B)|Product and Business|sales,sales executive,b2b sales,business development,bdm,account executive,sales manager,inside sales,sales representative
0|Sales process|What are the stages of the sales process or pipeline?|prospecting,lead generation;qualification,qualify;discovery,needs;demo,presentation,proposal;negotiation;closing,close;follow up,after sales;crm,pipeline|Stages are prospecting, qualifying leads, discovery of needs, a demo or proposal, negotiation, closing, and follow up and account growth, tracked in a CRM pipeline.
0|Qualification|How do you qualify a lead? Explain BANT or MEDDIC.|bant,budget,authority,need,timeline;meddic,metrics,economic buyer,decision criteria,decision process,identify pain,champion;fit,ideal customer profile,icp;qualify,disqualify,time|BANT checks budget, authority, need and timeline, while MEDDIC covers metrics, economic buyer, decision criteria, decision process, identified pain and champion. Qualify against the ideal customer profile and disqualify early to protect time.
1|Discovery call|How do you run a discovery call and uncover a customer's real needs?|open ended questions,ask;pain points,problem,challenge;listen,active listening;impact,cost of problem,business case;stakeholders,decision maker;spin,situation problem implication need;next steps|Prepare, ask open ended questions about situation, problems and implications (SPIN), listen actively, quantify the business impact, identify decision makers, and end by agreeing clear next steps.
1|Objections|How do you handle objections like it is too expensive or we are happy with our current vendor?|listen,acknowledge,empathise;clarify,ask why,root;value,roi,business case;cost of inaction,total cost,compare;proof,case study,reference,trial;reframe|Listen and acknowledge, ask questions to find the real concern, reframe around value and ROI including the cost of inaction, back it with proof such as case studies, references or a pilot, and confirm the objection is resolved.
2|Negotiation|How do you negotiate price without losing the deal or margin?|value,sell value,not price;give get,trade,concession;walk away,batna;discount,approval,margin;multi year,terms,volume;decision maker,urgency;anchor|Sell value first, never give a discount without getting something in return such as volume, a longer term or a faster decision, know your walk away point, anchor early, involve the decision maker and stay within margin and approval limits.
2|Pipeline management|How do you manage your pipeline and forecast accurately?|crm,salesforce,hubspot;stages,probability,weighted;coverage,pipeline coverage;forecast,commit,best case;hygiene,update,next step;conversion rate,velocity,win rate;prioritise,top deals;review|Keep CRM hygiene with updated stages and next steps, track coverage (often three times quota), conversion rates, deal velocity and win rate, forecast with weighted probabilities and commit versus best case, and review the pipeline regularly to focus on top deals.
3|Enterprise deals|How do you win a large, complex deal with multiple stakeholders and a long sales cycle?|stakeholder map,multi threading,champion,economic buyer,blocker;mutual action plan,timeline;business case,roi;poc,pilot,security,legal,procurement;executive sponsor,exec alignment;competition,differentiate;forecast|Map stakeholders and multi thread, build a champion and reach the economic buyer, agree a mutual action plan with milestones, build a ROI business case, run a pilot or POC, manage security, legal and procurement early, bring executive sponsors and differentiate against competitors.
3|Quota recovery|You are 40 percent behind quota with one month left. What do you do?|pipeline,review,deals;prioritise,close,high probability;accelerate,urgency,incentive,discount;prospecting,new leads,referrals;manager,help,executive;upsell,renewal,expansion,existing customers;honest,forecast,transparent|Review the pipeline for deals that can realistically close, prioritise high probability ones and accelerate with urgency and executive help, mine existing customers for upsell and renewals, add quick prospecting and referrals, and forecast honestly with my manager.
## marketing|Digital Marketing|Product and Business|marketing,digital marketing,seo,performance marketing,content marketing,marketing manager,growth marketing,social media marketing,sem
0|Funnel|What is the marketing funnel, and what is the difference between inbound and outbound marketing?|funnel,awareness,consideration,conversion;inbound,content,seo,attract;outbound,ads,cold,interrupt;lead,mql,sql;retention,loyalty;channel|The funnel moves people from awareness to consideration, conversion and loyalty. Inbound marketing attracts people with content and SEO, outbound pushes messages through ads and outreach. Leads progress from MQL to SQL before sales.
0|SEO|What is SEO, and what are on page, off page and technical SEO?|seo,search engine,organic;on page,keywords,title,meta,content,headings;off page,backlinks,authority;technical seo,speed,mobile,crawl,sitemap,schema;keyword research,intent;serp,ranking;search console|SEO improves organic search visibility. On page covers keywords, titles, meta descriptions and content quality, off page covers backlinks and authority, and technical SEO covers speed, mobile friendliness, crawlability, sitemaps and structured data, guided by keyword intent and Search Console.
1|Paid ads|How do you plan and optimise a paid campaign on Google or Meta? Explain CPC, CTR, CPA and ROAS.|cpc,cost per click;ctr,click through rate;cpa,cost per acquisition;roas,return on ad spend;audience,targeting,lookalike;creative,ad copy,a b test;budget,bid,optimise;landing page,conversion rate;quality score|Define goals and audiences, test creatives and copy, set budgets and bids, and optimise using CTR, CPC, conversion rate, CPA and ROAS, improving landing pages and quality score and pausing weak ads.
1|Content strategy|How do you build a content marketing strategy?|audience,persona,buyer journey;goals,kpi;content calendar,pillars,topics;formats,blog,video,email,social;distribution,promotion,seo;measure,traffic,leads,engagement;repurpose|Define the audience and buyer journey, set goals and KPIs, plan pillars and a content calendar across formats, distribute through SEO, email and social, repurpose content, and measure traffic, leads and engagement.
2|Analytics|How do you measure campaign performance and attribution? Mention GA4, UTM and conversion tracking.|ga4,google analytics;utm,parameters,tracking;conversion tracking,events,goals;attribution,first touch,last touch,multi touch;dashboard,looker,report;cac,ltv,roi;funnel analysis,cohort;a b test|Use UTM parameters and GA4 events to track conversions, apply attribution models such as first touch, last touch or multi touch, build dashboards, and judge channels by CAC, LTV and ROI, with A/B tests to validate changes.
2|Email and automation|How do you run email marketing and automation with segmentation and deliverability?|segmentation,personalisation,list;automation,workflow,drip,nurture;open rate,click rate,unsubscribe;deliverability,spam,spf,dkim,dmarc,sender reputation;a b test,subject line;crm,hubspot,mailchimp;compliance,consent,gdpr|Segment lists and personalise, build automated nurture workflows, measure open, click and unsubscribe rates, protect deliverability with SPF, DKIM, DMARC and a clean list, A/B test subject lines, and comply with consent rules such as GDPR.
3|Go to market|How do you create a go to market plan and brand positioning for a new product?|target audience,icp,segment,persona;positioning,value proposition,differentiation,messaging;channels,mix,pricing;launch,timeline,budget;competitor,market research;metrics,kpi,goals;sales alignment,enablement|Research the market and competitors, define the target segment and persona, craft a positioning and value proposition with clear messaging, choose channels and pricing, plan the launch with budget and timeline, align with sales enablement and set KPIs.
3|Budget|You have a limited budget and a pipeline target. How do you allocate spend across channels and prove ROI?|channel mix,allocate,test,scale;cac,payback,roi,roas;attribution,incrementality,holdout;experiment,small budget,double down;funnel,conversion;focus,icp,high intent;cut,underperforming;reporting,dashboard|Start with a small test budget across a few channels, measure CAC, payback and ROAS with sound attribution and incrementality tests, double down on the best performing high intent channels, cut underperformers and report results in a dashboard.
## ba|Business Analyst|Product and Business|business analyst,ba,requirements,bsa,business systems analyst,functional analyst,requirement analyst
0|BA role|What does a business analyst do, and what is the difference between BRD, FRD and SRS?|business analyst,bridge,stakeholders,business and it;requirements,gather,analyse,document;brd,business requirements document;frd,functional requirements;srs,software requirements specification;validate,sign off|A business analyst bridges business and IT by gathering, analysing, documenting and validating requirements. A BRD states business needs, an FRD details functional behaviour, and an SRS specifies software requirements including non functional ones.
0|Requirements|What is the difference between functional and non functional requirements, and how do you gather requirements?|functional,what the system does;non functional,performance,security,usability;interviews,workshops,surveys,observation;documentation,prototype;stakeholders,elicitation;user stories;clarify|Functional requirements describe what the system does, non functional requirements describe qualities like performance, security and usability. Gather them through interviews, workshops, observation, surveys, document analysis and prototypes with stakeholders.
1|User stories|How do you write good user stories and acceptance criteria, and what is INVEST?|user story,as a,i want,so that;acceptance criteria,given when then;invest,independent,negotiable,valuable,estimable,small,testable;epic,split;definition of done;backlog|A user story says as a role, I want an outcome, so that a benefit, with testable acceptance criteria often in Given, When, Then form. Good stories follow INVEST: independent, negotiable, valuable, estimable, small and testable.
1|Modelling|Which diagrams and models do you use: use case, process flow, ERD, wireframes?|use case,actors;process flow,bpmn,flowchart,swimlane;erd,data model;wireframe,mockup,prototype;uml,sequence,activity;as is,to be;visio,lucidchart,figma|Use case diagrams show actors and goals, BPMN or swimlane flows show processes, ERDs show data, wireframes show screens, and UML activity or sequence diagrams show behaviour. As-is and to-be process models clarify the change.
2|Conflicting stakeholders|Two stakeholders have conflicting requirements. How do you resolve it?|clarify,understand,why;prioritise,business value,moscow;facilitate,workshop,meeting;sponsor,escalate,decision;trade off,impact,data;document,agree,sign off;communicate|Understand the reason behind each requirement, bring them together in a workshop, prioritise by business value and impact with MoSCoW, escalate to the sponsor for a decision if needed, and document the agreement and sign off.
2|Analysis techniques|What are gap analysis, SWOT and cost benefit analysis, and when do you use them?|gap analysis,current state,future state,as is to be;swot,strengths,weaknesses,opportunities,threats;cost benefit,roi,payback;root cause,fishbone,five whys;feasibility;business case|Gap analysis compares current and desired state, SWOT assesses strengths, weaknesses, opportunities and threats, and cost benefit analysis compares costs with expected benefits and ROI. Root cause tools like five whys help understand problems, and together they support a business case.
3|Change and UAT|How do you manage requirement changes and support UAT through to go live?|change request,change control,impact analysis,approval;traceability matrix,rtm;uat,test cases,business users,sign off;defects,triage,retest;training,documentation,go live,hypercare;scope creep,baseline|Use a change control process with impact analysis and approval, maintain a requirements traceability matrix, prepare UAT cases with business users, triage defects, get sign off, and support training, go live and hypercare while preventing scope creep.
3|Over budget|A project is over budget and behind schedule and the business wants more features. What do you do as the BA?|rebaseline,scope,prioritise;moscow,mvp,must have;impact analysis,cost,time;stakeholders,sponsor,communicate,transparent;phase,release,defer;trade off,change request;root cause|Analyse the root cause, re-baseline scope, prioritise by value with MoSCoW and an MVP, assess the cost and time impact of any new request through change control, defer lower value features to a later phase, and communicate transparently with the sponsor.
## scrum|Scrum Master and Project Manager|Product and Business|scrum master,project manager,agile,scrum,delivery manager,pmp,agile coach,program manager,kanban
0|Scrum basics|What are the Scrum roles, events and artifacts?|product owner,scrum master,developers,team;sprint,planning,daily scrum,review,retrospective;product backlog,sprint backlog,increment;timebox;transparency,inspection,adaptation;definition of done|Scrum has the Product Owner, Scrum Master and Developers. Events are the Sprint, Sprint Planning, Daily Scrum, Sprint Review and Retrospective, and artifacts are the Product Backlog, Sprint Backlog and Increment, based on transparency, inspection and adaptation.
0|Agile vs waterfall|What is the difference between Agile and Waterfall, and between Scrum and Kanban?|agile,iterative,incremental,feedback,change;waterfall,sequential,phases,fixed;scrum,sprints,roles;kanban,flow,wip limit,board;manifesto,values|Waterfall is sequential with fixed scope, Agile is iterative with frequent feedback and welcomes change. Scrum uses timeboxed sprints and defined roles, Kanban is continuous flow with a visual board and work in progress limits.
1|Estimation|How do you estimate and plan: story points, velocity and burndown charts?|story points,relative,fibonacci;planning poker,estimate;velocity,capacity,average;burndown,burnup,progress;sprint goal,commitment;forecast,release plan|Estimate relatively with story points, for example through planning poker, use average velocity to forecast capacity and release plans, set a sprint goal, and track progress with burndown or burnup charts.
1|Impediments|As Scrum Master, how do you handle blockers, a team missing sprint goals, and conflicts?|impediment,remove blockers,escalate;root cause,retrospective,why;coach,facilitate,servant leader;conflict,listen,mediate;transparency,communicate,stakeholders;capacity,overcommit,scope;improve|A Scrum Master removes impediments and escalates when needed, uses retrospectives to find root causes of missed goals such as overcommitment, coaches rather than directs as a servant leader, mediates conflicts and keeps stakeholders informed.
2|Risk management|How do you manage risks, dependencies and scope creep on a project?|risk register,identify,probability,impact;mitigate,contingency,owner;dependency,critical path;scope creep,change control,backlog,prioritise;monitor,review,raid log;escalate,stakeholders;communicate|Maintain a risk register with probability, impact, owners and mitigation, track dependencies and the critical path, control scope creep through backlog prioritisation and change control, and review risks regularly with stakeholders.
2|Metrics|Which metrics do you use to track delivery and team health?|velocity,throughput,cycle time,lead time;burndown,burnup;defect,escaped defects,quality;predictability,commitment;team health,morale,retrospective,survey;customer satisfaction,value;wip,flow,cumulative flow|Track velocity or throughput, cycle and lead time, defects and escaped defects, predictability against commitments, cumulative flow and WIP, customer satisfaction and team health through retrospectives and surveys. Use them to improve, not to judge individuals.
3|Scaling agile|How do you scale agile across many teams with SAFe or Scrum of Scrums, and manage cross team dependencies?|safe,scaled agile,art,release train;scrum of scrums;pi planning,program increment;dependency,board,alignment;nexus,less;architecture,shared;okr,roadmap;coordinate,communicate|Scale with frameworks such as SAFe with Agile Release Trains and PI planning, or lighter options like Scrum of Scrums, Nexus or LeSS, visualise dependencies on a shared board, align through a common roadmap and OKRs, and keep teams autonomous while coordinating.
3|Delivery crisis|A critical release deadline is at risk, the team is in conflict and stakeholders are pressuring you. How do you handle it?|assess,facts,progress,risks;prioritise,mvp,scope,descope;stakeholders,transparent,expectations,options;team,listen,resolve,support,sustainable pace;remove blockers,escalate,resources;plan,daily,track;retrospective,lessons|Assess the facts, cut scope to an MVP with the product owner, give stakeholders transparent options on scope, time and resources, resolve team conflict by listening and removing blockers, protect a sustainable pace instead of overtime, track daily and run a retrospective afterwards.'''
MODULES.update(parse_bank(BANK_TEXT))
for _extra in (os.path.join(HERE, "interviewer_extra.txt"), os.path.join(HOME, "interviewer_extra.txt")):
    if os.path.exists(_extra):
        load_bank_file(_extra)


# =====================================================================
#  FINDING THE ROLE FROM WHAT YOU TYPE OR SAY
# =====================================================================
def role_score(n, ns, role):
    best = 0
    for alias in [role["name"]] + role["aliases"]:
        a = norm(alias)
        if a and (re.search(r"(?<![a-z0-9])" + re.escape(a) + r"(?![a-z0-9])", n)
                  or ns == a.replace(" ", "")):
            best = max(best, len(a))
    return best


def find_role(text):
    n = norm(text or "")
    if not n:
        return None
    ns = n.replace(" ", "")
    scored = sorted(((role_score(n, ns, r), k) for k, r in MODULES.items()), reverse=True)
    if scored[0][0] > 0:
        return scored[0][1]
    names = {}
    for k, r in MODULES.items():
        for al in [r["name"]] + r["aliases"]:
            names[norm(al)] = k
    close = difflib.get_close_matches(n, list(names), n=1, cutoff=0.72)
    if close:
        return names[close[0]]
    singles = [x for x in names if " " not in x and len(x) > 3]
    for tok in n.split():
        close = difflib.get_close_matches(tok, singles, n=1, cutoff=0.8)   # playwrite -> playwright
        if close:
            return names[close[0]]
    return None


def print_roles():
    print("\nROLES (say or type any of these names)")
    cats = [c for c in CAT_ORDER if any(r.get("cat") == c for r in MODULES.values())]
    cats += sorted({r.get("cat", "Other") for r in MODULES.values()} - set(cats))
    for c in cats:
        names = [f"{r['name']}" for r in MODULES.values() if r.get("cat", "Other") == c]
        print(f"  {c}: " + ", ".join(names))
    print()


# =====================================================================
#  THE INTERVIEW  (offline: your answer decides the next question)
# =====================================================================
class Interview:
    def __init__(self, key, minutes, clock=time.time):
        self.key = key
        self.module = MODULES[key]["name"]
        self.minutes = minutes
        self.clock = clock
        self.t0 = clock()
        self.log = []
        self.cur = None
        self.bank = None
        self.fu_made = 0
        self.max_fu = max(3, int(minutes // 4))
        self.behav_done = False
        self.behav_asked = []

    def elapsed(self):
        return (self.clock() - self.t0) / 60.0

    def start(self):
        self.cur = {"q": "Please introduce yourself and tell me about your experience.",
                    "topic": "Introduction", "level": "beginner", "intro": True}
        return f"Welcome to your {self.module} mock interview. Let us begin. {self.cur['q']}"

    # ---------- one answer in, next question out ----------
    def turn(self, answer, skipped=False):
        """Returns (spoken_text, finished)."""
        cur = self.cur
        if cur.get("followup"):
            return self._turn_followup(answer, skipped)
        if cur.get("intro"):
            yrs = [int(x) for x in re.findall(r"(\d+)\s*\+?\s*(?:years?|yrs?)", answer.lower())]
            y = max(yrs) if yrs else 0
            self.bank = Bank(self.key, 0 if y <= 1 else 1 if y <= 4 else 2)
            self.log.append({"q": cur["q"], "a": answer, "score": None, "level": "beginner",
                             "topic": "Introduction"})
            return self._next("Thank you. Let us start with the technical questions.")
        if skipped:
            score, hit, miss, fb = 0, [], [], "No problem, we will move on."
        else:
            score, hit, miss = Bank.evaluate(cur["_raw"], answer)
            fb = feedback_for(score, hit, miss, cur["_raw"]["ideal"])
        self.log.append({"q": cur["q"], "a": answer if not skipped else "(skipped)", "score": score,
                         "level": cur["level"], "topic": cur["topic"], "ideal": cur["_raw"]["ideal"]})
        remark = "" if cur["_raw"].get("behav") else self.bank.adjust(score)
        fu = None if skipped else self._followup(cur, score, hit, miss)
        if fu:
            self.cur = fu
            return f"{fb} {fu['q']}".strip(), False
        return self._next(f"{fb} {remark}".strip())

    def _followup(self, cur, score, hit, miss):
        raw = cur["_raw"]
        if raw.get("behav") or self.fu_made >= self.max_fu or self.elapsed() >= self.minutes * 0.8:
            return None
        if 4 <= score <= 6 and miss:
            kind, concept = "miss", random.choice(miss[:3])
        elif score >= 7 and hit and random.random() < 0.5:
            kind, concept = "probe", random.choice(hit)
        else:
            return None
        group = next((g for g in raw["groups"] if g[0] == concept), [concept])
        q = random.choice(MISS_T if kind == "miss" else PROBE_T).replace("{c}", concept)
        self.fu_made += 1
        return {"q": q, "topic": cur["topic"], "level": cur["level"], "_raw": raw,
                "followup": {"kind": kind, "concept": concept, "terms": group}}

    def _turn_followup(self, answer, skipped):
        cur = self.cur
        if skipped:
            score, fb = 0, "No problem."
        else:
            score, fb = eval_followup(answer, cur["followup"], cur["_raw"]["ideal"])
        self.log.append({"q": cur["q"], "a": answer if not skipped else "(skipped)", "score": score,
                         "level": cur["level"], "topic": cur["topic"] + " (follow-up)"})
        return self._next(fb)

    def _next(self, prefix=""):
        if self.elapsed() >= self.minutes:
            return prefix + " That is all the time we have.", True
        if not self.behav_done and self.elapsed() >= self.minutes * 0.75:
            self.behav_done = True
            return self._behavioural(prefix, "Now a question about your work experience.")
        q = self.bank.pick()
        if q is None:
            if self.elapsed() < self.minutes * 0.95:        # bank used up early: keep going with these
                out = self._behavioural(prefix, "Let me ask you about your work experience.")
                if out:
                    return out
            return prefix + " That was my last question.", True
        self.cur = {"q": q["q"], "topic": q["topic"], "level": LEVELS[q["lvl"]], "_raw": q}
        return f"{prefix} {q['q']}".strip(), False

    def _behavioural(self, prefix, lead):
        left = [q for q in BEHAVIOURAL if q["q"] not in self.behav_asked]
        if not left:
            return None
        q = random.choice(left)
        self.behav_asked.append(q["q"])
        self.cur = {"q": q["q"], "topic": "Behavioural", "level": "behavioural", "_raw": q}
        return f"{prefix} {lead} {q['q']}".strip(), False

    def hint(self):
        c = self.cur
        if c.get("followup"):
            return "Start with what " + c["followup"]["concept"] + " is, then say where it is used."
        if c.get("_raw"):
            return "Think about " + " and ".join(g[0] for g in c["_raw"]["groups"][:2]) + "."
        return "Take your time and start with the basics."

    # ---------- final report ----------
    def finish(self):
        scored = [x for x in self.log if isinstance(x.get("score"), (int, float))]
        avg = round(sum(x["score"] for x in scored) / len(scored), 1) if scored else 0
        top = [LEVELS.index(x["level"]) for x in scored if x["score"] >= 6 and x["level"] in LEVELS]
        rep = {"overall_score": avg,
               "level_reached": LEVELS[max(top)] if top else "beginner",
               "strengths": sorted({x["topic"] for x in scored if x["score"] >= 7
                                    and "follow-up" not in x["topic"]})[:4],
               "gaps": sorted({x["topic"] for x in scored if x["score"] <= 5
                               and "follow-up" not in x["topic"]})[:4],
               "study_plan": [f"Revise {x['topic']}: {x['ideal']}" for x in scored
                              if x["score"] <= 5 and x.get("ideal")][:4],
               "verdict": ("Interview ready at this level." if avg >= 8 else
                           "Close. Polish the gaps and you will be ready." if avg >= 6 else
                           "Needs more preparation on the fundamentals.")}
        return rep, avg

    def report_text(self, rep, avg):
        L = [f"MOCK INTERVIEW REPORT - {self.module}",
             datetime.datetime.now().strftime("%d %B %Y, %I:%M %p"),
             f"Duration: {self.elapsed():.0f} minutes | Questions answered: {len(self.log)}",
             f"Overall score: {rep.get('overall_score', avg)} / 10 | Level reached: {rep.get('level_reached')}",
             "", "Verdict: " + str(rep.get("verdict", "")), "", "STRENGTHS"]
        L += ["  - " + s for s in rep.get("strengths", [])] or ["  -"]
        L += ["", "GAPS"] + ["  - " + s for s in rep.get("gaps", [])]
        L += ["", "STUDY PLAN"] + ["  - " + s for s in rep.get("study_plan", [])]
        L += ["", "TRANSCRIPT"]
        for i, x in enumerate(self.log, 1):
            L += [f"{i}. [{x['level']} | {x['topic']}] score: {x['score']}", "   Q: " + x["q"],
                  "   A: " + str(x["a"])]
            if x.get("ideal") and isinstance(x.get("score"), (int, float)) and x["score"] <= 5:
                L.append("   Model answer: " + x["ideal"])
        return "\n".join(L)


# =====================================================================
#  SHARED HELPERS FOR THE TERMINAL AND WEB MODES
# =====================================================================
def command(ans):
    a = norm(ans)
    if a in ("repeat", "repeat the question", "repeat that", "say again", "say that again", "once more",
             "come again", "please repeat", "repeat please") or a.startswith("repeat the question"):
        return "repeat"
    if a in ("skip", "skip it", "skip question", "skip this", "skip this question", "next",
             "next question", "pass"):
        return "skip"
    if "hint" in a.split() and len(a.split()) <= 5:
        return "hint"
    if a in ("stop", "end", "finish", "quit", "exit", "stop interview", "end interview",
             "stop the interview", "end the interview", "i am done", "that is all") \
            or a.startswith(("stop the interview", "end the interview")):
        return "stop"
    return None


def save_report(text):
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    paths = []
    for folder in (os.path.join(HOME, "storage", "downloads"), HOME):
        if os.path.isdir(folder):
            p = os.path.join(folder, f"interview_report_{stamp}.txt")
            try:
                with open(p, "w", encoding="utf-8") as f:
                    f.write(text)
                paths.append(p)
            except OSError:
                pass
    return paths


def closing_summary(rep, avg):
    s = (f"Your interview is over. Overall score {rep.get('overall_score', avg)} out of 10. "
         f"Level reached: {rep.get('level_reached')}. {rep.get('verdict', '')} ")
    if rep.get("strengths"):
        s += "You were strong in " + ", ".join(rep["strengths"][:3]) + ". "
    if rep.get("gaps"):
        s += "Work on " + ", ".join(rep["gaps"][:3]) + "."
    return s


def pick_role(voice, arg):
    if arg:
        k = find_role(arg)
        if k:
            return k
        print(f"Role '{arg}' not found.")
        print_roles()
        return None
    print_roles()
    for attempt in range(3):
        voice.say("Which role should I interview you for? For example Playwright automation, Java backend, "
                  "DevOps, product manager, sales, or SAP FICO. The full list is on your screen."
                  if attempt == 0 else
                  "I did not recognise that role. Please say it again, for example Java backend or product manager.")
        k = find_role(voice.listen(single=True))
        if k:
            voice.say(f"Starting a {MODULES[k]['name']} interview.")
            return k
    return None


# =====================================================================
#  LOCALHOST WEB MODE  (the browser is the ears and mouth, Python is the interviewer)
# =====================================================================
SESSIONS = {}

PAGE = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mock Interview</title>
<style>
:root{--bg:#f4f5f8;--card:#fff;--text:#14161c;--muted:#686e7a;--accent:#2f6df6;--line:#dde0e7;--good:#168a52;--bad:#cc3b3b}
@media (prefers-color-scheme:dark){:root{--bg:#0f1115;--card:#181b21;--text:#eceef2;--muted:#9aa0ad;--accent:#6c9bff;--line:#2a2e37;--good:#4cc38a;--bad:#ff7b7b;color-scheme:dark}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;max-width:640px;margin-inline:auto;padding:16px}
h1{font-size:22px;margin:6px 0 2px}
.sub{color:var(--muted);font-size:13px;margin-bottom:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px;margin-bottom:12px}
label{display:block;margin:10px 0 4px;color:var(--muted);font-size:13px}
select,textarea,input[type=range]{width:100%}
select,textarea{padding:10px;border-radius:10px;border:1px solid var(--line);background:var(--bg);color:var(--text);font:inherit}
button{font:inherit;padding:11px 14px;border-radius:10px;border:1px solid var(--line);background:var(--card);color:var(--text);cursor:pointer}
button.p{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:600}
button:disabled{opacity:.5}
.seg{display:flex;gap:8px}.seg button{flex:1}.seg button.on{background:var(--accent);color:#fff;border-color:var(--accent)}
.row{display:flex;gap:8px;margin-top:10px;flex-wrap:wrap}.row button{flex:1;min-width:70px}
.bar{display:flex;gap:10px;align-items:center;font-size:13px;color:var(--muted);margin-bottom:10px;flex-wrap:wrap}
.pill{background:var(--accent);color:#fff;border-radius:99px;padding:2px 10px;font-size:12px}
#q{font-size:18px;line-height:1.45}
#log{max-height:32vh;overflow-y:auto}
.m{margin:6px 0;padding:8px 10px;border-radius:10px;font-size:14px;line-height:1.4}
.m.me{background:var(--bg);text-align:right}.m.bot{border:1px solid var(--line)}
#status{min-height:18px;color:var(--muted);font-size:13px;margin:6px 0}
#mic.on{animation:p 1s infinite}@keyframes p{50%{opacity:.6}}
.score{font-size:42px;font-weight:700}
li{margin:4px 0}
pre{white-space:pre-wrap;font-size:13px;max-height:40vh;overflow:auto}
details{font-size:14px}
</style></head><body>
<h1>Mock Interview</h1>
<div class="sub">Runs on your own computer. No AI, no key. Chrome or Edge gives you voice.</div>

<section id="setup" class="card">
 <label>Which role should I interview you for?</label>
 <select id="role"></select>
 <label>Length</label>
 <div class="seg" id="mins"><button data-m="15">15 min</button><button data-m="18" class="on">18 min</button><button data-m="20">20 min</button></div>
 <details style="margin-top:12px"><summary>Voice and mic settings</summary>
  <label>Interviewer voice</label><select id="voice"></select>
  <label>Interviewer speed</label><input id="rate" type="range" min="0.7" max="1.3" step="0.05" value="1">
  <label>I will answer in</label>
  <select id="lang"><option value="en-IN">English (India)</option><option value="en-US">English (US)</option><option value="en-GB">English (UK)</option><option value="hi-IN">Hindi</option></select>
  <label>Auto send after silence (seconds)</label><input id="silence" type="range" min="3" max="10" step="1" value="6">
  <label><input type="checkbox" id="speakOn" checked> Interviewer speaks</label>
  <label><input type="checkbox" id="auto" checked> Start listening automatically after each question</label>
 </details>
 <div class="row"><button class="p" id="start">Start interview</button></div>
</section>

<section id="room" style="display:none">
 <div class="bar"><span id="clock">00:00</span><span class="pill" id="level"></span><span id="topic"></span></div>
 <div class="card"><div id="q"></div></div>
 <div class="card"><textarea id="ta" rows="4" placeholder="Speak, or type your answer here..."></textarea>
  <div id="status"></div>
  <div class="row"><button class="p" id="mic">Tap to answer</button><button id="send">Send answer</button></div>
  <div class="row"><button id="rep">Repeat</button><button id="hint">Hint</button><button id="skip">Skip</button><button id="end">End</button></div></div>
 <div class="card" id="log"></div>
</section>

<section id="report" style="display:none" class="card"></section>

<script>
var $=function(i){return document.getElementById(i)};
var synth=window.speechSynthesis,SR=window.SpeechRecognition||window.webkitSpeechRecognition;
var sid=null,rec=null,listening=false,speaking=false,busy=false,finished=false,want=false,misses=0,silT=null,mins=18,voices=[],t0=0;

function api(p,b){return fetch(p,{method:b?'POST':'GET',headers:{'Content-Type':'application/json'},body:b?JSON.stringify(b):undefined}).then(function(r){return r.json()}).then(function(d){if(d.error)throw new Error(d.error);return d})}
function status(t){$('status').textContent=t||''}
function fmt(s){var m=Math.floor(s/60),x=s%60;return (m<10?'0':'')+m+':'+(x<10?'0':'')+x}
function log(w,t){var d=document.createElement('div');d.className='m '+w;d.textContent=t;$('log').appendChild(d);$('log').scrollTop=1e6}

api('/api/info').then(function(d){var sel=$('role');d.cats.forEach(function(c){var g=document.createElement('optgroup');g.label=c;d.roles.filter(function(r){return r.cat===c}).forEach(function(r){var o=document.createElement('option');o.value=r.key;o.textContent=r.name;g.appendChild(o)});sel.appendChild(g)})}).catch(function(e){status(e.message)});
document.querySelectorAll('#mins button').forEach(function(b){b.onclick=function(){document.querySelectorAll('#mins button').forEach(function(x){x.classList.remove('on')});b.classList.add('on');mins=parseInt(b.dataset.m)}});

function loadVoices(){if(!synth)return;voices=synth.getVoices();var s=$('voice');s.innerHTML='';voices.forEach(function(v,i){var o=document.createElement('option');o.value=i;o.textContent=v.name+' ('+v.lang+')';s.appendChild(o)});var p=voices.findIndex(function(v){return /^en[-_]IN/i.test(v.lang)});if(p<0)p=voices.findIndex(function(v){return /^en/i.test(v.lang)});if(p>=0)s.value=p}
if(synth){loadVoices();synth.onvoiceschanged=loadVoices}

function speak(text,done){
 if(!synth||!$('speakOn').checked||!text){if(done)setTimeout(done,50);return}
 synth.cancel();var parts=text.match(/[^.!?]+[.!?]*\s*/g)||[text],q=[],cur='';
 parts.forEach(function(p){if((cur+p).length>180&&cur){q.push(cur);cur=p}else cur+=p});if(cur)q.push(cur);
 speaking=true;status('Interviewer speaking...');var i=0;
 (function next(){if(!speaking)return;if(i>=q.length){speaking=false;status('');if(done)done();return}
  var u=new SpeechSynthesisUtterance(q[i++]);var v=voices[$('voice').value];if(v){u.voice=v;u.lang=v.lang}
  u.rate=parseFloat($('rate').value);u.onend=next;u.onerror=next;synth.speak(u)})();
}

function listen(){
 if(!SR){status('This browser has no speech recognition. Use Chrome or Edge, or type your answer.');$('ta').focus();return}
 if(listening||speaking||busy||finished)return;
 rec=new SR();rec.lang=$('lang').value;rec.continuous=true;rec.interimResults=true;var finalText=$('ta').value.trim();
 rec.onstart=function(){listening=true;want=true;$('mic').textContent='Listening... tap when done';$('mic').classList.add('on');status('Listening. Pause for a few seconds, or tap the button, to send.')};
 rec.onresult=function(e){var interim='';for(var i=e.resultIndex;i<e.results.length;i++){var t=e.results[i][0].transcript;if(e.results[i].isFinal)finalText=(finalText+' '+t).trim();else interim+=t}
  $('ta').value=(finalText+' '+interim).trim();misses=0;clearTimeout(silT);silT=setTimeout(finishAnswer,parseFloat($('silence').value)*1000)};
 rec.onerror=function(e){if(e.error==='not-allowed'||e.error==='service-not-allowed'){want=false;status('Microphone blocked. Allow it in the address bar, or type your answer.')}};
 rec.onend=function(){listening=false;$('mic').classList.remove('on');$('mic').textContent='Tap to answer';
  if(!want||busy||finished||speaking)return;
  if($('ta').value.trim()){finishAnswer();return}
  misses++;if(misses>=3){want=false;misses=0;speak('I did not hear anything. Tap the mic when you are ready, or type your answer.');return}
  setTimeout(listen,300)};
 try{rec.start()}catch(e){}
}
function finishAnswer(){clearTimeout(silT);want=false;if(rec){try{rec.stop()}catch(e){}}var t=$('ta').value.trim();if(!t||busy||finished)return;submit(t,'answer')}

function submit(text,action){
 busy=true;status('Thinking...');if(synth)synth.cancel();speaking=false;
 if(action==='answer')log('me',text);if(action==='skip')log('me','(skipped)');
 $('ta').value='';
 api('/api/answer',{sid:sid,text:text,action:action}).then(function(d){busy=false;present(d)}).catch(function(e){busy=false;status('Error: '+e.message)});
}
function present(d){
 if(d.question){$('q').textContent=d.question;$('level').textContent=d.level||'';$('topic').textContent=d.topic||''}
 if(d.spoken)log('bot',d.spoken);
 if(d.finished){finished=true;showReport(d);speak((d.spoken||'')+' '+(d.summary||''));return}
 status('');speak(d.spoken,function(){if($('auto').checked)listen()});
}
function li(items){return '<ul>'+(items&&items.length?items.map(function(x){return '<li>'+x.replace(/[&<>]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;'}[c]})+'</li>'}).join(''):'<li>-</li>')+'</ul>'}
function showReport(d){
 $('room').style.display='none';var r=d.report,el=$('report');el.style.display='block';
 el.innerHTML='<h2 style="margin-top:0">Your result</h2><div class="score">'+r.overall_score+' / 10</div><div class="sub">Level reached: <b>'+r.level_reached+'</b></div><p>'+r.verdict+'</p><h3>Strengths</h3>'+li(r.strengths)+'<h3>Work on</h3>'+li(r.gaps)+'<h3>Study plan</h3>'+li(r.study_plan)+
 '<details><summary>Full transcript and model answers</summary><pre id="rt"></pre></details><div class="row"><button class="p" id="dl">Download report</button><button id="again">New interview</button></div>';
 $('rt').textContent=d.report_text;
 $('dl').onclick=function(){var a=document.createElement('a');a.href=URL.createObjectURL(new Blob([d.report_text],{type:'text/plain'}));a.download='interview_report.txt';a.click()};
 $('again').onclick=function(){location.reload()};
}

$('start').onclick=function(){
 if(synth){synth.speak(new SpeechSynthesisUtterance(' '))}
 $('start').disabled=true;
 api('/api/start',{role:$('role').value,minutes:mins}).then(function(d){sid=d.sid;t0=Date.now();$('setup').style.display='none';$('room').style.display='block';
  setInterval(function(){if(!finished)$('clock').textContent=fmt(Math.floor((Date.now()-t0)/1000))+' / '+fmt(mins*60)},1000);present(d)}).catch(function(e){$('start').disabled=false;alert(e.message)});
};
$('mic').onclick=function(){if(listening){finishAnswer()}else{if(synth)synth.cancel();speaking=false;listen()}};
$('send').onclick=finishAnswer;
$('rep').onclick=function(){submit('','repeat')};
$('hint').onclick=function(){submit('','hint')};
$('skip').onclick=function(){submit('','skip')};
$('end').onclick=function(){if(confirm('End the interview and see your report?'))submit('','stop')};
$('ta').addEventListener('keydown',function(e){if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();finishAnswer()}});
</script></body></html>"""


def web_state(iv):
    c = iv.cur or {}
    return {"question": c.get("q", ""), "level": c.get("level", ""), "topic": c.get("topic", ""),
            "elapsed": round(iv.elapsed(), 2), "minutes": iv.minutes, "n": len(iv.log)}


def web_finish(iv):
    rep, avg = iv.finish()
    text = iv.report_text(rep, avg)
    return {"report": rep, "report_text": text, "summary": closing_summary(rep, avg),
            "saved": save_report(text)}


def api_start(body):
    key = body.get("role")
    if key not in MODULES:
        raise ValueError("Please pick a role first.")
    try:
        minutes = max(5, min(45, int(body.get("minutes") or 18)))
    except (TypeError, ValueError):
        minutes = 18
    iv = Interview(key, minutes)
    spoken = iv.start()
    sid = uuid.uuid4().hex[:12]
    now = time.time()
    for k in [k for k, v in SESSIONS.items() if now - v["t"] > 6 * 3600]:
        SESSIONS.pop(k, None)
    SESSIONS[sid] = {"iv": iv, "t": now}
    return {"sid": sid, "spoken": spoken, **web_state(iv)}


def api_answer(body):
    s = SESSIONS.get(body.get("sid"))
    if not s:
        raise ValueError("This session expired. Please start again.")
    iv = s["iv"]
    s["t"] = time.time()
    text = (body.get("text") or "").strip()
    action = body.get("action") or command(text) or "answer"
    if action == "repeat":
        return {"spoken": iv.cur["q"], "finished": False, **web_state(iv)}
    if action == "hint":
        return {"spoken": iv.hint(), "finished": False, **web_state(iv)}
    if action == "stop":
        out = {"spoken": "Okay, ending the interview here.", "finished": True, **web_state(iv)}
        out.update(web_finish(iv))
        return out
    if action == "answer" and not text:
        raise ValueError("Please say or type your answer first.")
    spoken, fin = iv.turn(text, skipped=(action == "skip"))
    out = {"spoken": spoken, "finished": fin, **web_state(iv)}
    if fin:
        out.update(web_finish(iv))
    return out


class WebHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/":
            return self._send(200, PAGE, "text/html")
        if path == "/api/info":
            cats = [c for c in CAT_ORDER if any(r.get("cat") == c for r in MODULES.values())]
            cats += sorted({r.get("cat", "Other") for r in MODULES.values()} - set(cats))
            roles = [{"key": k, "name": r["name"], "cat": r.get("cat", "Other")} for k, r in MODULES.items()]
            return self._send(200, json.dumps({"roles": roles, "cats": cats}), "application/json")
        self._send(404, "not found", "text/plain")

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
            if path == "/api/start":
                out = api_start(body)
            elif path == "/api/answer":
                out = api_answer(body)
            else:
                return self._send(404, "not found", "text/plain")
            self._send(200, json.dumps(out), "application/json")
        except ValueError as e:
            self._send(400, json.dumps({"error": str(e)}), "application/json")
        except Exception as e:
            print("server error:", e)
            self._send(500, json.dumps({"error": "Something went wrong inside the interviewer."}),
                       "application/json")


def run_web(argv, arg_of):
    try:
        port = int(arg_of("--port", 8000))
    except ValueError:
        port = 8000
    server = None
    for p in range(port, port + 10):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", p), WebHandler)
            port = p
            break
        except OSError:
            continue
    if not server:
        print("Could not find a free port. Try --port 9000")
        return
    url = f"http://localhost:{port}"
    print("=" * 60)
    print(" MOCK INTERVIEW is running (only on this device)")
    print(f" Open this in Chrome or Edge:  {url}")
    print(" Press Ctrl+C here to stop.")
    print("=" * 60)
    if "--no-browser" not in argv:
        try:
            if shutil.which("termux-open-url"):
                subprocess.run(["termux-open-url", url])
            else:
                webbrowser.open(url)
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


# =====================================================================
#  TERMINAL MODE
# =====================================================================
def main():
    argv = sys.argv[1:]

    def arg_of(flag, default=None):
        return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else default

    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return
    if "--reset-history" in argv:
        try:
            os.remove(HIST_FILE)
        except OSError:
            pass
        print("Question history cleared.")
        return
    if arg_of("--bank"):
        print("Loaded", load_bank_file(arg_of("--bank")), "role(s) from", arg_of("--bank"))
    if "--list" in argv:
        print_roles()
        return
    if "--web" in argv:
        run_web(argv, arg_of)
        return

    voice = Voice(keyboard="--keyboard" in argv, text_only="--text" in argv)
    try:
        minutes = max(5, min(45, int(float(arg_of("--minutes", 18)))))
    except ValueError:
        minutes = 18
    print("=" * 60)
    print(" MOCK INTERVIEW  (offline, no AI, no key)")
    print(" voice :", voice.describe())
    print(" say   : repeat | hint | skip | stop      (tip: python3 interviewer.py --web)")
    print("=" * 60)

    key = pick_role(voice, arg_of("--role"))
    if not key:
        print("No role chosen. Try:  python3 interviewer.py --role java    or    --list")
        return
    iv = Interview(key, minutes)
    voice.say(iv.start())

    silent = 0
    while True:
        ans = voice.listen()
        if not ans:
            silent += 1
            if silent >= 3:
                ans, silent = "skip", 0
            else:
                voice.say("I did not hear you. Please answer, or say skip.")
                continue
        silent = 0
        cmd = command(ans)
        if cmd == "stop":
            voice.say("Okay, ending the interview here.")
            break
        if cmd == "repeat":
            voice.say(iv.cur["q"])
            continue
        if cmd == "hint":
            voice.say(iv.hint())
            continue
        spoken, finished = iv.turn(ans, skipped=(cmd == "skip"))
        if spoken:
            voice.say(spoken)
        if finished:
            break

    rep, avg = iv.finish()
    text = iv.report_text(rep, avg)
    paths = save_report(text)
    voice.say(closing_summary(rep, avg))
    print("\n" + text)
    if paths:
        print("\nReport saved to:", *paths, sep="\n  ")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterview stopped.")
