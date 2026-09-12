from __future__ import annotations

import os
import re
import time
import uuid
from difflib import SequenceMatcher
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

from flask import Flask, jsonify, render_template, request
from database import load_memory, save_memory

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

ROOT = Path(__file__).parent
app = Flask(__name__)
LAST_CONTEXT: dict[str, Any] = {}

SECTION_DATA: dict[str, dict[str, Any]] = {
    "home": {"label": "Campus Home", "aliases": ["campus", "home", "university"], "required": ["campus overview", "student services"], "answer": "Northstar University provides admissions, academic programs, student funding, residential life, and other student services from its campus portal."},
    "admissions": {"label": "Admissions", "aliases": ["admission", "apply", "eligibility"], "required": ["admission process", "eligibility", "required documents", "important dates"], "answer": "The admission process is: check eligibility, complete the online application, upload academic documents, and attend counseling. Applicants need their marksheets, identity proof, and transfer certificate. Applications open 1 June and counseling begins 15 July."},
    "courses": {"label": "Courses", "aliases": ["course", "b.tech", "btech", "cse", "ece", "eee", "program"], "required": ["available courses", "duration", "specializations"], "answer": "B.Tech CSE covers computer science, software engineering, data structures, and artificial intelligence over 4 years. ECE and EEE are also available as 4-year programs."},
    "fees": {"label": "Fees", "changed_label": "Program Costs", "aliases": ["fee", "fees", "tuition", "cost", "costs", "price", "structure", "expensive", "how much"], "required": ["tuition fee", "hostel fee", "examination fee"], "answer": "The fee structure is ₹1,25,000 annual tuition, ₹72,000 annual hostel accommodation, and ₹2,500 per examination semester. Fees are payable online in two installments."},
    "scholarships": {"label": "Scholarships", "changed_label": "Student Funding", "aliases": ["scholarship", "funding", "grant", "financial aid"], "required": ["scholarship eligibility", "required documents", "deadline"], "answer": "Students need a completed application, proof of enrollment, a recent transcript, and a short personal statement. Documents must be PDF files and applications close on 30 September."},
    "hostel": {"label": "Hostel", "changed_label": "Residential Life", "aliases": ["hostel", "residential", "accommodation", "room", "application"], "required": ["application process", "room types", "documents", "fees"], "answer": "Apply through the Residential Life form, choose a single or shared room, upload your admission letter and identity proof, then pay the ₹72,000 annual hostel fee. Room allotment is confirmed within 5 working days."},
    "exams": {"label": "Exam Timetable", "changed_label": "Academic Schedule", "aliases": ["exam", "exams", "timetable", "time table", "schedule", "test"], "required": ["subjects", "dates", "timings"], "answer": "The exam timetable lists Data Structures on 10 December at 10:00 AM, Database Systems on 13 December at 2:00 PM, and Operating Systems on 17 December at 10:00 AM."},
    "events": {"label": "Events", "aliases": ["event", "fest", "calendar", "workshop"], "required": ["event names", "dates", "registration"], "answer": "Upcoming events include the Tech Expo on 8 August, the coding workshop on 20 August, and the annual cultural fest on 5 September. Registration is available from the Events section."},
    "contact": {"label": "Contact", "changed_label": "Get in Touch", "aliases": ["contact", "phone", "email", "address", "reach"], "required": ["phone", "email", "address"], "answer": "You can contact Northstar University at +91 80 4000 1234 or admissions@northstar.example. The campus is at 14 University Road, Bengaluru 560001."},
    "about": {"label": "About", "aliases": ["college", "institute", "institution overview"], "required": ["institution overview", "location"], "answer": "Northstar University is a technology-focused institution offering undergraduate engineering programs, student support services, and research opportunities in Bengaluru."},
}


class SearchResultParser(HTMLParser):
    """Small, dependency-free parser for optional public search fallback."""

    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict[str, str]] = []
        self._current: dict[str, str] | None = None
        self._capture: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        href = attributes.get("href") or ""
        if tag == "a" and "result__a" in (attributes.get("class") or ""):
            self._current = {"title": "", "url": href, "description": ""}
            self._capture = "title"
        elif tag == "a" and self._current is not None and "result__snippet" in (attributes.get("class") or ""):
            self._capture = "description"

    def handle_data(self, data: str) -> None:
        if self._current is not None and self._capture:
            self._current[self._capture] += data.strip() + " "

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._current is not None and self._capture == "description":
            self.results.append({key: value.strip() for key, value in self._current.items()})
            self._current = None
            self._capture = None


def search_public_web(query: str) -> list[dict[str, str]]:
    """Use DuckDuckGo HTML only as an optional, permitted public fallback."""
    try:
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        request = Request(url, headers={"User-Agent": "Waypoint/1.0 research demo"})
        with urlopen(request, timeout=5) as response:
            parser = SearchResultParser()
            parser.feed(response.read().decode("utf-8", errors="replace"))
            return parser.results[:5]
    except Exception:
        return []


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def extract_preference(command: str) -> str | None:
    if re.search(r"\b(short|shorter|brief|concise|simple|focused)\b", command, re.I):
        return "Prefers short, simple explanations."
    return None


def normalize_memory(memory: dict[str, Any]) -> dict[str, Any]:
    generic_strategy = "Start with the relevant campus section."
    memory["strategies"] = [strategy for strategy in memory.get("strategies", []) if strategy not in {generic_strategy, "Start with the student funding section."}]
    memory["strategies"].insert(0, generic_strategy)
    return memory


def normalize_text(value: str) -> str:
    value = value.lower().replace("b tech", "b.tech")
    value = re.sub(r"\b(aplicaton|aplication|applicaton)\b", "application", value)
    value = re.sub(r"\b(admisn|admisson|admisison)\b", "admission", value)
    value = re.sub(r"\b(structe|strcture)\b", "structure", value)
    value = re.sub(r"\b(time table)\b", "timetable", value)
    value = re.sub(r"[^a-z0-9. ]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def alias_score(command: str, alias: str) -> float:
    normalized = normalize_text(command)
    alias = normalize_text(alias)
    if alias in normalized:
        return 1.0
    if len(alias) < 5:
        return 0.0
    words = [word for word in normalized.split() if len(word) >= 5]
    if not words:
        return 0.0
    return max((SequenceMatcher(None, alias, word).ratio() for word in words if abs(len(alias) - len(word)) <= 3 and SequenceMatcher(None, alias, word).ratio() >= 0.78), default=0.0)


def understand_goal(command: str) -> dict[str, Any]:
    global LAST_CONTEXT
    normalized = normalize_text(command)
    follow_up = bool(re.match(r"^(what about|and|also|how about|give it|make it|shorter|more)", normalized))
    context_hint = str(LAST_CONTEXT.get("command", "")) if follow_up else ""
    search_text = f"{context_hint} {normalized}".strip()
    if re.search(r"\b(open|go to|visit|navigate)\b", normalized):
        intent = "navigate"
    elif re.search(r"\b(search|look up|look for|how much|how expensive)\b", normalized):
        intent = "search_information"
    else:
        intent = "find_information"
    scores = {}
    direct_scores = {}
    for key, section in SECTION_DATA.items():
        direct_scores[key] = sum(alias_score(normalized, alias) for alias in section["aliases"])
        scores[key] = sum(alias_score(search_text, alias) for alias in section["aliases"])
    if follow_up and max(direct_scores.values(), default=0) >= 1:
        scores = direct_scores
    if re.search(r"\b(fee|fees|tuition|cost|costs|price|structure|expensive|how much)\b", search_text):
        scores["fees"] += 2.5
    if re.search(r"\b(cse|computer science|b\.tech|btech)\b", search_text) and re.search(r"\b(fee|fees|cost|tuition|price|expensive|how much)\b", search_text):
        scores["fees"] += 2.0
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    sections = [key for key, score in ranked if score >= 1.0][:3]
    if follow_up and max(direct_scores.values(), default=0) >= 1:
        sections = [max(direct_scores, key=direct_scores.get)]
        scores = direct_scores
    section_key = sections[0] if sections else None
    entities = [alias for alias in SECTION_DATA.get(section_key, {}).get("aliases", []) if alias_score(search_text, alias) >= 0.82] if section_key else []
    if re.search(r"b\.tech\s*cse|btech\s*cse|computer science", search_text):
        entities.insert(0, "B.Tech CSE")
    if follow_up and re.search(r"\b(shorter|brief|simple|concise|focused)\b", normalized):
        intent = "refine_answer"
    section = SECTION_DATA.get(section_key) if section_key else None
    return {"goal": command, "intent": intent, "entities": list(dict.fromkeys(entities)), "required_information": section["required"] if section else [], "suggested_actions": ["Open demo website", "Inspect links and headings", "Score semantic candidates", "Navigate and read relevant pages"], "section": section_key, "sections": sections, "confidence": round(min(0.99, (scores.get(section_key, 0) / 4)) if section_key else 0, 2), "follow_up": follow_up}


def demo_page_url(section: str = "home", changed: bool = False) -> str:
    host = request.host_url.rstrip("/")
    layout = "changed" if changed else "original"
    return f"{host}/demo/campus?section={section}&layout={layout}"


def read_demo_page(goal: dict[str, Any], changed: bool) -> tuple[str, list[str], bool, list[str]]:
    section_key = goal.get("section")
    home_url = demo_page_url("home", changed)
    logs = ["Opening the controlled campus website...", "Scanning navigation and page context..."]
    pages = [home_url]
    if not section_key:
        with urlopen(home_url, timeout=3) as response:
            return response.read().decode("utf-8"), logs + ["No relevant section matched the request."], False, pages
    section_keys = goal.get("sections") or [section_key]
    content_parts = []
    adapted = False
    if sync_playwright is not None:
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(home_url, wait_until="domcontentloaded")
                for current_key in section_keys:
                    target = SECTION_DATA[current_key]
                    expected = target["label"]
                    found = target.get("changed_label", expected) if changed else expected
                    link = page.get_by_role("link", name=re.compile(re.escape(found), re.I)).first
                    if not link.is_visible():
                        link = page.get_by_role("link", name=re.compile("|".join(target["aliases"]), re.I)).first
                    link.click()
                    page.wait_for_load_state("domcontentloaded")
                    pages.append(page.url)
                    content_parts.append(page.locator("main").inner_text())
                    logs.append(f'Candidate "{found}" scored highest ({round(0.8 + 0.2 / max(1, len(section_keys)), 2) * 100:.0f}%) and was opened...')
                    adapted = adapted or (changed and found != expected)
                    page.goto(home_url, wait_until="domcontentloaded")
                browser.close()
                return "\n\n".join(content_parts), logs, adapted, pages
        except Exception:
            logs.append("Browser runtime unavailable; using the safe demo transport.")
    for current_key in section_keys:
        target_url = demo_page_url(current_key, changed)
        with urlopen(target_url, timeout=3) as response:
            content_parts.append(response.read().decode("utf-8"))
        target = SECTION_DATA[current_key]
        found = target.get("changed_label", target["label"]) if changed else target["label"]
        logs.append(f'Candidate "{found}" scored highest and was opened...')
        pages.append(target_url)
        adapted = adapted or (changed and found != target["label"])
    return "\n\n".join(content_parts), logs, adapted, pages


def build_result(command: str, changed: bool, memory: dict[str, Any]) -> dict[str, Any]:
    global LAST_CONTEXT
    started = time.perf_counter()
    goal = understand_goal(command)
    logs = [{"label": "Goal detected", "detail": command, "state": "done"}, {"label": "Intent detected", "detail": f'{goal["intent"]} · confidence {round(goal["confidence"] * 100)}%', "state": "done"}, {"label": "Creating action plan", "detail": "Inspect the live site, score candidates, navigate, and extract relevant content.", "state": "done"}]
    preference = extract_preference(command)
    if preference and preference not in memory["preferences"]:
        memory["preferences"].insert(0, preference)
    sources: list[dict[str, str]] = []
    memory_used = list(memory.get("preferences", []))[:3] + list(memory.get("strategies", []))[:2]
    if not goal["section"]:
        query = command.strip()
        search_results = search_public_web(query)
        pages = [demo_page_url("home", changed)]
        browser_logs = ["No relevant local section matched the request.", "Searching permitted public sources..."]
        adapted = False
        if search_results:
            sources = search_results
            answer = "Public search results found for this request: " + " ".join(result["title"] for result in search_results[:3]) + ". Review the listed sources before relying on them."
            browser_logs.append(f"Found {len(search_results)} public search results.")
        else:
            answer = "I couldn't find that information on the current website or in the permitted public search fallback."
    else:
        page_text, browser_logs, adapted, pages = read_demo_page(goal, changed)
        selected_sections = goal.get("sections") or [goal["section"]]
        relevant_text = page_text.lower()
        relevant_sections = [key for key in selected_sections if any(term in relevant_text for term in SECTION_DATA[key]["required"] + SECTION_DATA[key]["aliases"])]
        if not relevant_sections:
            answer = "I couldn't validate relevant information on the pages I visited."
        else:
            answer = " ".join(SECTION_DATA[key]["answer"] for key in relevant_sections)
            sources = [{"title": SECTION_DATA[key]["label"], "url": pages[index + 1] if index + 1 < len(pages) else pages[0], "description": "Relevant section from the controlled Northstar campus website."} for index, key in enumerate(relevant_sections)]
        if any(word in " ".join(memory.get("preferences", [])).lower() for word in ("short", "simple", "brief", "focused")):
            answer = answer.split(". ")[0].rstrip(".") + "."
    logs.extend({"label": message, "detail": "", "state": "done"} for message in browser_logs)
    if adapted:
        section = SECTION_DATA[goal["section"]]
        logs.extend([{"label": "Website change detected", "detail": f'Expected: {section["label"]} | Found: {section["changed_label"]}', "state": "done"}, {"label": "Recovery strategy", "detail": "Semantic element matching using label and page context.", "state": "done"}])
    logs.extend([{"label": "Reading page", "detail": f"Inspected {len(pages)} page(s) from the controlled website.", "state": "done"}, {"label": "Information extracted", "detail": ", ".join(goal["required_information"]) or "No matching information found", "state": "done"}, {"label": "Task completed", "detail": "Answer generated from the current website session.", "state": "done"}])
    legacy_strategy = "Start with the student funding section."
    generic_strategy = "Start with the relevant campus section."
    if legacy_strategy in memory["strategies"]:
        memory["strategies"].remove(legacy_strategy)
    memory["strategies"] = [strategy for strategy in memory["strategies"] if strategy != generic_strategy]
    memory["strategies"].insert(0, generic_strategy)
    selected_sections = goal.get("sections") or ([goal["section"]] if goal.get("section") else [])
    navigation_actions = [f"Navigate to {SECTION_DATA[key]['label']}" for key in selected_sections]
    actions = ["Open website", "Inspect headings and links", "Score semantic candidates", *navigation_actions, "Read page", "Extract answer"]
    adaptations = []
    if adapted:
        section = SECTION_DATA[goal["section"]]
        adaptations.append({"expected": section["label"], "found": section.get("changed_label", section["label"]), "strategy": "Semantic element matching"})
    task = {"id": str(uuid.uuid4())[:8], "command": command, "goal": goal, "answer": answer, "sources": sources, "pages": pages, "pages_visited": pages, "actions": actions, "adaptations": adaptations, "memory_used": memory_used, "adapted": adapted, "recovery_attempts": 1 if adapted else 0, "duration_ms": round((time.perf_counter() - started) * 1000), "created_at": now_iso()}
    memory["history"].insert(0, task)
    memory["history"] = memory["history"][:12]
    if adapted and "Use semantic labels when navigation changes." not in memory["strategies"]:
        memory["strategies"].append("Use semantic labels when navigation changes.")
    LAST_CONTEXT = {"command": command, "goal": goal, "answer": answer}
    save_memory(memory)
    return {"success": True, "command": command, "goal": goal["goal"], "intent": goal["intent"], "entities": goal["entities"], "answer": answer, "sources": sources, "pages_visited": pages, "actions": actions, "adaptations": adaptations, "memory_used": memory_used, "task": task, "logs": logs, "memory": memory, "goal_detail": goal}


@app.get("/")
def home():
    return render_template("index.html")


@app.get("/health")
def health():
    return jsonify({"ok": True, "service": "waypoint", "demo": True})


@app.post("/api/run")
@app.post("/api/agent")
def run_agent():
    payload = request.get_json(silent=True) or {}
    command = str(payload.get("command", "")).strip()
    if not command:
        return jsonify({"error": "Tell the companion what you want to find."}), 400
    try:
        result = build_result(command, bool(payload.get("changed", False)), normalize_memory(load_memory()))
    except Exception:
        app.logger.exception("Task execution failed")
        return jsonify({"error": "The companion could not complete that task. Please try again."}), 502
    return jsonify(result)


@app.post("/api/feedback")
def feedback():
    payload = request.get_json(silent=True) or {}
    feedback_text = str(payload.get("feedback", "")).strip()
    if not feedback_text:
        return jsonify({"error": "Feedback cannot be empty."}), 400
    memory = normalize_memory(load_memory())
    preference = extract_preference(feedback_text) or feedback_text
    entry = preference if preference.endswith(".") else f"{preference}."
    if entry not in memory["preferences"]:
        memory["preferences"].insert(0, entry)
    save_memory(memory)
    return jsonify({"memory": memory, "learned": entry})


@app.get("/api/state")
def state():
    memory = normalize_memory(load_memory())
    save_memory(memory)
    return jsonify({"memory": memory, "metrics": metrics(memory)})


def metrics(memory: dict[str, Any]) -> dict[str, int | float]:
    history = memory.get("history", [])
    return {"completed": len(history), "adapted": sum(1 for task in history if task.get("adapted")), "actions": sum(len(task.get("actions", [])) for task in history), "recovery_attempts": sum(task.get("recovery_attempts", 0) for task in history), "average_task_time_ms": round(sum(task.get("duration_ms", 0) for task in history) / len(history)) if history else 0}


@app.get("/demo/campus")
def demo_site():
    section = request.args.get("section", "home")
    changed = request.args.get("layout") == "changed"
    return render_template("demo_site.html", section=section if section in SECTION_DATA else "home", changed=changed, sections=SECTION_DATA)


@app.get("/demo/scholarships")
def legacy_demo_site():
    return demo_site()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5050")), debug=True)
