# SPDX-FileCopyrightText: 2026 That Scottish Guy
# SPDX-License-Identifier: AGPL-3.0-only
"""Resume match: which of a posting's key terms already appear in a person's resume.

Deliberately simple and explainable (no AI, nothing leaves the server): pick the terms that matter in the
posting (known skills plus words it repeats), then check them against the resume's words.
"""
import re

TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9+#./-]*[A-Za-z0-9+#]|[A-Za-z]")

STOP = set("""
a about above across after again against all also although always am an and any are as at be because been before being below
between both but by can could did do does doing down during each either else etc even every few for from further had has have
having he her here hers him his how however i if in including into is it its itself just may me might more most much must my
no nor not of off on once one only or other our out over own per same shall she should so some such than that the their them
then there these they this those through to too under until up upon us use used using very via was we were what when where
which while who whom why will with within without would you your yours
ability able accordance across additional asset assets issue issues applicant applicants applicable applications apply applying appropriate area areas
assist assigned based best candidate candidates carry certain city class closing company complete concerns condition
conditions consideration contract county current customers date day days deliver demonstrated description department
dependent desired details develop diploma directly diverse diversity duties education effective effectively employee
employees employer employment ensure equal equivalent excellent experience experienced extensive familiar following
full function functions general good group hours human identified important including individual information
inclusive interested job jobs keep knowledge knowledgeable level levels like looking maintain make making manage
management manner meet member members must need needs new number office offer offered operate opportunity
organization overview part participate perform performance period permanent person personal plan please policies policy
position positions possess preferred previous principles prior process processes program programs proof provide
provides providing qualifications qualified range ranging read reason receive related relevant report reporting
required requirement requirements responsibilities responsibility responsible result results review role roles salary
school see seek seeking senior service services set several shift skill skills small solutions staff standard standards
status stay strong successful support supports system team teams technical term text time town township type
understanding union unit upon variety various week weekly well work worked working works written year years
accommodation accommodations accessible applicants contact contacted date email flex hourly hours incumbent interview limited online persons
posting recruitment resume rate rates start submit submission status thank website campus classification
""".split())

# Multi-word and tool names worth recognising even if the posting only mentions them once.
LEXICON = [
    "active directory", "help desk", "service desk", "desktop support", "technical support", "end user", "remote support",
    "routing", "switching", "lan", "wan", "wireless", "siem", "ccna", "ccnp", "ccie", "nac", "clearpass", "telephony", "voip", "load balancer",
    "load balancing", "bgp", "ospf", "vlan", "mfa", "endpoint", "intune", "sccm", "wireshark", "monitoring",
    "windows", "linux", "macos", "ubuntu", "azure", "aws", "microsoft 365", "office 365", "exchange", "sharepoint", "teams",
    "powershell", "python", "sql", "javascript", "java", "c#", ".net", "bash", "git", "docker", "kubernetes", "vmware",
    "virtualization", "networking", "tcp/ip", "dns", "dhcp", "vpn", "firewall", "cisco", "fortinet", "palo alto", "wifi",
    "cybersecurity", "security", "backup", "itil", "servicenow", "jira", "ticketing", "incident management", "change management",
    "project management", "gis", "arcgis", "scada", "erp", "sap", "oracle", "epic", "power bi", "excel", "database", "api",
    "customer service", "communication", "documentation", "troubleshooting", "scheduling", "budgeting", "payroll",
    "collective agreement", "wsib", "first aid", "cpr", "health and safety", "forklift", "licence", "license",
]


def stem(w):
    w = w.lower()
    for suf in ("ing", "ed", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            return w[: -len(suf)]
    return w


def words(text):
    return [t.lower().strip("./-") for t in TOKEN.findall(text)]


def key_terms(desc, limit=30, skip=()):
    """Ordered list of (display term) that matter in a posting. `skip`: words to ignore, such as the employer's own name."""
    skip = {stem(w) for w in skip}
    low = desc.lower()
    found = []
    for term in LEXICON:
        if re.search(r"(?<![\w])" + re.escape(term) + r"(?:s|es)?(?![\w])", low):
            found.append(term)
    counts = {}
    for w in words(desc):
        if len(w) < 3 or w in STOP or w.isdigit() or stem(w) in skip:
            continue
        counts[w] = counts.get(w, 0) + 1
    covered = {stem(x) for t in found for x in t.split()}
    extras = [w for w, c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
              if c >= 2 and stem(w) not in covered]
    seen, out = set(), []
    for t in found + extras:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out[:limit]


def compare(desc, resume, skip=()):
    """-> {"score": 0-100, "matched": [...], "missing": [...]}"""
    terms = key_terms(desc, skip=skip)
    have_words = {stem(w) for w in words(resume)}
    have_text = resume.lower()
    matched, missing = [], []
    for t in terms:
        if " " in t or not t.isalpha():
            ok = re.search(r"(?<![\w])" + re.escape(t) + r"(?![\w])", have_text) is not None
        else:
            ok = stem(t) in have_words
        (matched if ok else missing).append(t)
    score = round(100 * len(matched) / len(terms)) if terms else 0
    return {"score": score, "matched": matched, "missing": missing[:15], "terms": len(terms)}
